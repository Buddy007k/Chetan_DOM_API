import requests
import time
from akamai.edgegrid import EdgeGridAuth

# DNS Providers (ONLY THESE TWO)
from core.akamDNS import akam
from core.ctelx import ctel
from getNS import getNS

# ---------------- CONFIG ----------------
EDGERC_PATH = "./.edgerc"
SECTION = "default"

BASE_URL = "https://akab-p63dmw3gdpa5cxgx-oivonvolbsqjgxex.luna.akamaiapis.net"

TTL = 300

#TEST MODE

TEST_MODE = True
TEST_DOMAINS = ["quicktest.in"]  

# DNS propagation + retry config
DNS_PROPAGATION_WAIT = 60   # seconds (can increase to 120 if needed)
VALIDATION_RETRIES = 5
RETRY_DELAY = 30            # seconds

# ---------------------------------------

session = requests.Session()
session.auth = EdgeGridAuth.from_edgerc(EDGERC_PATH, SECTION)

session.headers.update({
    "Accept": "application/json",
    "Content-Type": "application/json"
})

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
    success = False

    for ns in providers:
        if ns == "akam":
            result = akam(record, value, "mod", zone, "TXT", TTL)
            print("Akamai DNS:", result)
            if result == "Successful":
                success = True

        elif ns == "constellix":
            result = ctel(record, value, "mod", zone, "TXT", TTL)
            print("Constellix DNS:", result)
            if result == "Successful":
                success = True

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

        if status not in ["REQUEST_ACCEPTED", "VALIDATION_IN_PROGRESS"]:
            continue

        challenge = d.get("validationChallenge", {})
        txt = challenge.get("txtRecord")

        if not txt:
            continue

        total_pending += 1

        domain_name = d["domainName"]
        record_name = txt.get("name")
        txt_value = txt.get("value")

        print("\n====================================")
        print(f"Domain: {domain_name}")
        print(f"TXT Name: {record_name}")
        print(f"TXT Value: {txt_value}")

        # Extract zone + record
        parts = record_name.split(".", 1)
        if len(parts) < 2:
            print("Invalid record format, skipping...")
            continue

        record = parts[0]
        zone = parts[1]

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
    print(f"Total Pending Domains   : {total_pending}")
    print(f"DNS Updates Successful  : {success_updates}")
    print(f"Validations Triggered   : {success_validations}")


# ---------------- ENTRY ----------------
if __name__ == "__main__":
    domains = get_all_domains()

    print(f"\nTotal Domains Found: {len(domains)}")

    process_domains(domains)