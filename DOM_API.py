import requests
import time
import urllib3
import tldextract
from akamai.edgegrid import EdgeGridAuth

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# DNS Providers
from core.akamDNS import akam
from core.ctelx_v2 import ctel   # ✅ USE NEW FIXED FILE
from getNS import getNS

# ---------------- CONFIG ----------------
EDGERC_PATH = "./.edgerc"
SECTION = "default"

BASE_URL = "https://akab-p63dmw3gdpa5cxgx-oivonvolbsqjgxex.luna.akamaiapis.net"

TTL = "300"

TEST_MODE = True
TEST_DOMAINS = ["quicktest.in"]

DNS_PROPAGATION_WAIT = 60
VALIDATION_RETRIES = 5
RETRY_DELAY = 30

# ---------------------------------------

session = requests.Session()
session.auth = EdgeGridAuth.from_edgerc(EDGERC_PATH, SECTION)

session.headers.update({
    "Accept": "application/json",
    "Content-Type": "application/json"
})

# ---------------- CORRECT PARSER ----------------
def build_structured_entry(record_name, txt_value):
    ext = tldextract.extract(record_name)

    zone = f"{ext.domain}.{ext.suffix}"   # ✅ correct root domain
    record = record_name.replace("." + zone, "")  # everything before zone

    return {
        "record": record,
        "zone": zone,
        "ttl": TTL,
        "rtype": "TXT",
        "value": txt_value,
        "action": "mod"
    }

# ---------------- FETCH DOMAINS ----------------
def get_all_domains():
    url = f"{BASE_URL}/domain-validation/v1/domains"

    params = {
        "paginate": True,
        "page": 1,
        "pageSize": 100
    }

    all_domains = []

    while True:
        response = session.get(url, params=params, verify=False)

        if response.status_code != 200:
            print("Error fetching domains:", response.text)
            return []

        data = response.json()
        all_domains.extend(data.get("domains", []))

        if not data.get("metadata", {}).get("hasNext"):
            break

        params["page"] += 1

    return all_domains

# ---------------- DNS UPDATE ----------------
def updateTXTrecord(entry):
    record = entry["record"]
    zone = entry["zone"]
    ttl = entry["ttl"]
    value = entry["value"]
    rtype = entry["rtype"]

    print(f"\nUpdating: {record}.{zone}")
    print(f"Structured Input → {record},{zone},{ttl},{rtype},{value}")

    providers = getNS(zone, record, rtype, 'add')
    print("Detected Providers:", providers)

    success = False

    for NS in providers:

        if NS == 'akam':
            try:
                result = akam(record, value, "mod", zone, rtype, ttl)
                print("Akamai MOD:", result)

                if result != 'Successful':
                    result = akam(record, value, "add", zone, rtype, ttl)
                    print("Akamai ADD:", result)

                if result == 'Successful':
                    success = True

            except Exception as e:
                print("Akamai Failed:", e)

        elif NS == 'constellix':
            try:
                result = ctel(record, value, "mod", zone, rtype, ttl)
                print("Constellix MOD:", result)

                if result != 'Successful':
                    result = ctel(record, value, "add", zone, rtype, ttl)
                    print("Constellix ADD:", result)

                if result == 'Successful':
                    success = True

            except Exception as e:
                print("Constellix Failed:", e)

    return success

# ---------------- VALIDATE ----------------
def validate_domain(domain):
    url = f"{BASE_URL}/domain-validation/v1/domains/validate-now"

    payload = {
        "domains": [
            {
                "domainName": domain,
                "validationMethod": "DNS_TXT",
                "validationScope": "DOMAIN"
            }
        ]
    }

    response = session.post(url, json=payload, verify=False)

    if response.status_code == 200:
        print(f"Validation triggered for {domain}")
        return True
    else:
        print(f"Validation failed: {response.text}")
        return False

# ---------------- MAIN ----------------
def process_domains(domains):
    total = 0
    dns_success = 0
    validation_success = 0

    for d in domains:
        domain_name = d.get("domainName")

        if TEST_MODE and domain_name not in TEST_DOMAINS:
            continue

        challenge = d.get("validationChallenge", {})
        txt = challenge.get("txtRecord")

        if not txt:
            continue

        total += 1

        record_name = txt.get("name")
        txt_value = txt.get("value")

        print("\n====================================")
        print(f"Domain: {domain_name}")
        print(f"TXT Name: {record_name}")
        print(f"TXT Value: {txt_value}")

        entry = build_structured_entry(record_name, txt_value)

        updated = updateTXTrecord(entry)

        if not updated:
            print("DNS update failed → skipping validation")
            continue

        dns_success += 1

        print(f"Waiting {DNS_PROPAGATION_WAIT}s...")
        time.sleep(DNS_PROPAGATION_WAIT)

        for attempt in range(1, VALIDATION_RETRIES + 1):
            print(f"Validation attempt {attempt}")

            if validate_domain(domain_name):
                validation_success += 1
                break

            time.sleep(RETRY_DELAY)

    print("\n========== FINAL SUMMARY ==========")
    print(f"Total Processed        : {total}")
    print(f"DNS Updates Successful : {dns_success}")
    print(f"Validations Triggered  : {validation_success}")

# ---------------- ENTRY ----------------
if __name__ == "__main__":
    domains = get_all_domains()
    print(f"\nTotal Domains Found: {len(domains)}")
    process_domains(domains)