import requests
import time
import urllib3
from akamai.edgegrid import EdgeGridAuth

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# DNS Providers
from core.akamDNS import akam
from core.ctelx import ctel
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

# ---------------- STRUCTURED PARSER (LIKE list.txt) ----------------
def build_structured_entry(record_name, txt_value):
    parts = record_name.split(".")

    record = parts[0]
    zone = ".".join(parts[1:])

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


# ---------------- DNS UPDATE (OLD SCRIPT STYLE + ADD FALLBACK) ----------------
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

        # ---- AKAMAI ----
        if NS == 'akam':
            try:
                # Try MODIFY first
                result = akam(record, value, "mod", zone, rtype, ttl)
                print("Akamai MOD:", result)

                if result != 'Successful':
                    print("Akamai MOD failed → trying ADD")
                    result = akam(record, value, "add", zone, rtype, ttl)
                    print("Akamai ADD:", result)

                if result == 'Successful':
                    success = True

            except Exception as e:
                print("Akamai ERROR → trying ADD")

                try:
                    result = akam(record, value, "add", zone, rtype, ttl)
                    print("Akamai ADD (fallback):", result)

                    if result == 'Successful':
                        success = True

                except Exception as e2:
                    print("Akamai FAILED completely:", e2)

        # ---- CONSTELLIX ----
        elif NS == 'constellix':
            try:
                # Try MODIFY first
                result = ctel(record, value, "mod", zone, rtype, ttl)
                print("Constellix MOD:", result)

                if result != 'Successful':
                    print("Constellix MOD failed → trying ADD")
                    result = ctel(record, value, "add", zone, rtype, ttl)
                    print("Constellix ADD:", result)

                if result == 'Successful':
                    success = True

            except Exception as e:
                print("Constellix ERROR → trying ADD")

                try:
                    result = ctel(record, value, "add", zone, rtype, ttl)
                    print("Constellix ADD (fallback):", result)

                    if result == 'Successful':
                        success = True

                except Exception as e2:
                    print("Constellix FAILED completely:", e2)

    return success

# ---------------- VALIDATE DOMAIN ----------------
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
        print(f"Validation failed for {domain}: {response.text}")
        return False


# ---------------- MAIN PROCESS ----------------
def process_domains(domains):
    total = 0
    dns_success = 0
    validation_success = 0

    for d in domains:
        domain_name = d.get("domainName")

        # TEST MODE
        if TEST_MODE and domain_name not in TEST_DOMAINS:
            continue

        status = d.get("domainStatus")

        if not TEST_MODE:
            if status not in ["REQUEST_ACCEPTED", "VALIDATION_IN_PROGRESS"]:
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

        # ✅ Build structured entry (LIKE list.txt)
        entry = build_structured_entry(record_name, txt_value)

        # ---- STEP 1: DNS UPDATE ----
        updated = updateTXTrecord(entry)

        if not updated:
            print("DNS update failed → skipping validation")
            continue

        dns_success += 1

        # ---- STEP 2: WAIT ----
        print(f"Waiting {DNS_PROPAGATION_WAIT}s...")
        time.sleep(DNS_PROPAGATION_WAIT)

        # ---- STEP 3: VALIDATE ----
        for attempt in range(1, VALIDATION_RETRIES + 1):
            print(f"Validation attempt {attempt}")

            if validate_domain(domain_name):
                validation_success += 1
                break

            print(f"Retrying in {RETRY_DELAY}s...")
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