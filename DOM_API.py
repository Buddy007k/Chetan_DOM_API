import requests
import time
import tldextract
from akamai.edgegrid import EdgeGridAuth

# DNS Providers (ONLY THESE TWO)
from core.akamDNS import akam
from core.ctelx import ctel
from getNS import getNS

# ---------------- CONFIG ----------------
EDGERC_PATH = "./.edgerc"
SECTION = "default"

BASE_URL = "https://YOUR_HOST.luna.akamaiapis.net"

TTL = 300

# -------- TEST MODE --------
TEST_MODE = True
TEST_DOMAINS = ["quicktest.in"]

# -------- DNS + RETRY CONFIG --------
DNS_PROPAGATION_WAIT = 60   # seconds
VALIDATION_RETRIES = 5
RETRY_DELAY = 30            # seconds

# ---------------------------------------

session = requests.Session()
session.auth = EdgeGridAuth.from_edgerc(EDGERC_PATH, SECTION)

session.headers.update({
    "Accept": "application/json",
    "Content-Type": "application/json"
})

# ---------------- HELPER: EXTRACT RECORD + ZONE ----------------
def extract_record_and_zone(fqdn):
    ext = tldextract.extract(fqdn)

    zone = f"{ext.domain}.{ext.suffix}"   # correct root domain
    record = fqdn.replace("." + zone, "")  # rest is record

    return record, zone


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
        response = session.get(url, params=params)

        if response.status_code != 200:
            print("Error fetching domains:", response.text)
            return []

        data = response.json()
        all_domains.extend(data.get("domains", []))

        if not data.get("metadata", {}).get("hasNext"):
            break

        params["page"] += 1

    return all_domains


# ---------------- UPDATE TXT RECORD ----------------
def update_txt_record(record, value, zone):
    print(f"\nUpdating DNS for: {record}.{zone}")

    providers = getNS(zone, record, "TXT", "add")
    print("Detected Providers:", providers)

    success = False

    for ns in providers:
        if ns == "akam":
            try:
                result = akam(record, value, "mod", zone, "TXT", TTL)
                print("Akamai DNS:", result)

                if result == "Successful":
                    success = True

            except Exception as e:
                print(f"Akamai FAILED: {e}")

        elif ns == "constellix":
            try:
                result = ctel(record, value, "mod", zone, "TXT", TTL)
                print("Constellix DNS:", result)

                if result == "Successful":
                    success = True

            except Exception as e:
                print(f"Constellix FAILED for {record}.{zone}: {e}")

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

    response = session.post(url, json=payload)

    if response.status_code == 200:
        print(f"Validation triggered for {domain}")
        return True
    else:
        print(f"Validation failed for {domain}: {response.text}")
        return False


# ---------------- MAIN PROCESS ----------------
def process_domains(domains):
    total_pending = 0
    success_updates = 0
    success_validations = 0

    for d in domains:
        domain_name = d.get("domainName")

        # ✅ TEST MODE FILTER
        if TEST_MODE and domain_name not in TEST_DOMAINS:
            continue

        status = d.get("domainStatus")

        # Allow TEST MODE to bypass status
        if not TEST_MODE:
            if status not in ["REQUEST_ACCEPTED", "VALIDATION_IN_PROGRESS"]:
                continue
        else:
            print(f"\nTEST MODE: Processing {domain_name} (ignoring status)")

        challenge = d.get("validationChallenge", {})
        txt = challenge.get("txtRecord")

        if not txt:
            continue

        total_pending += 1

        record_name = txt.get("name")
        txt_value = txt.get("value")

        print("\n====================================")
        print(f"Domain   : {domain_name}")
        print(f"TXT Name : {record_name}")
        print(f"TXT Value: {txt_value}")

        # ✅ Correct extraction
        record, zone = extract_record_and_zone(record_name)

        print(f"Parsed → record: {record}, zone: {zone}")

        # ---- STEP 1: UPDATE DNS ----
        updated = update_txt_record(record, txt_value, zone)

        if not updated:
            print("DNS update failed, skipping validation...")
            continue

        success_updates += 1

        # ---- STEP 2: WAIT FOR DNS PROPAGATION ----
        print(f"Waiting {DNS_PROPAGATION_WAIT}s for DNS propagation...")
        time.sleep(DNS_PROPAGATION_WAIT)

        # ---- STEP 3: VALIDATE WITH RETRY ----
        for attempt in range(1, VALIDATION_RETRIES + 1):
            print(f"Validation attempt {attempt} for {domain_name}")

            if validate_domain(domain_name):
                success_validations += 1
                break

            print(f"Retrying in {RETRY_DELAY}s...")
            time.sleep(RETRY_DELAY)

    print("\n========== FINAL SUMMARY ==========")
    print(f"Total Processed Domains : {total_pending}")
    print(f"DNS Updates Successful  : {success_updates}")
    print(f"Validations Triggered   : {success_validations}")


# ---------------- ENTRY ----------------
if __name__ == "__main__":
    domains = get_all_domains()

    print(f"\nTotal Domains Found: {len(domains)}")

    process_domains(domains)
