import requests
from akamai.edgegrid import EdgeGridAuth

# ---------------- CONFIG ----------------
EDGERC_PATH = "./.edgerc"
SECTION = "default"

BASE_URL = "https://akab-p63dmw3gdpa5cxgx-oivonvolbsqjgxex.luna.akamaiapis.net"  # from .edgerc host

# ---------------------------------------

session = requests.Session()
session.auth = EdgeGridAuth.from_edgerc(EDGERC_PATH, SECTION)

session.headers.update({
    "Accept": "application/json"
})

def get_all_domains():
    url = f"{BASE_URL}/domain-validation/v1/domains"

    params = {
        "paginate": True,
        "page": 1,
        "pageSize": 100   # max recommended
    }

    all_domains = []

    while True:
        response = session.get(url, params=params)

        if response.status_code != 200:
            print("Error:", response.text)
            return []

        data = response.json()

        domains = data.get("domains", [])
        all_domains.extend(domains)

        metadata = data.get("metadata", {})
        if not metadata.get("hasNext"):
            break

        params["page"] += 1

    return all_domains


def extract_pending_validation(domains):
    print("\n==== Pending Domain TXT Records ====\n")

    pending_count = 0

    for d in domains:
        status = d.get("domainStatus")

        # Only pending / in-progress domains
        if status in ["REQUEST_ACCEPTED", "VALIDATION_IN_PROGRESS"]:
            challenge = d.get("validationChallenge", {})
            txt = challenge.get("txtRecord")

            # Only count if TXT exists
            if txt:
                pending_count += 1

                print(f"Domain: {d['domainName']}")
                print(f"Status: {status}")

                print("TXT Record:")
                print(f"  Name  : {txt.get('name')}")
                print(f"  Value : {txt.get('value')}")

                print("-" * 50)

    return pending_count

if __name__ == "__main__":
    domains = get_all_domains()

    print(f"\nTotal Domains Found: {len(domains)}")

    pending_count = extract_pending_validation(domains)

    print(f"\nTotal Pending Validation Domains: {pending_count}")