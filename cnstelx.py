import hashlib
import json
import requests
import configparser
import time
import hmac
import base64

# ---------------- CONFIG ----------------
config = configparser.ConfigParser(strict=False)
config.read_file(open(r'./config/config.cfg'))

access_key = config.get('ctel', 'API_Key')
secret = config.get('ctel', 'Secret_Key')

BASE_URL = "https://api.dns.constellix.com/v1"

# Disable SSL warnings if needed
requests.packages.urllib3.disable_warnings()


# ---------------- AUTH ----------------
def _generate_token():
    curr_time = round(time.time() * 1000)
    raw = bytes(str(curr_time), "utf-8")
    key = bytes(secret, 'utf-8')

    signature = hmac.new(key, raw, hashlib.sha1)
    signature_b64 = base64.b64encode(signature.digest()).decode()

    token = f"{access_key}:{signature_b64}:{curr_time}"
    return token


def _headers():
    return {
        "Content-Type": "application/json",
        "x-cns-security-token": _generate_token()
    }


# ---------------- DOMAIN ID ----------------
def get_domain_id(zone):
    url = f"{BASE_URL}/domains/search?exact={zone}"

    try:
        response = requests.get(url, headers=_headers(), verify=False)
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            return data[0]["id"]

        print(f"[Constellix] Domain NOT found: {zone}")
        return None

    except Exception as e:
        print(f"[Constellix] Domain lookup error: {e}")
        return None


# ---------------- RECORD ID ----------------
def get_record_id(domain_id, rtype, record):
    url = f"{BASE_URL}/domains/{domain_id}/records/{rtype}/search?exact={record}"

    try:
        response = requests.get(url, headers=_headers(), verify=False)
        data = response.json()

        if isinstance(data, list) and len(data) > 0:
            return data[0]["id"]

        return None

    except Exception as e:
        print(f"[Constellix] Record lookup error: {e}")
        return None


# ---------------- PAYLOAD BUILDER ----------------
def build_payload(rtype, record, value, ttl):
    ttl = int(ttl)

    if rtype == "A":
        return {
            "name": record,
            "ttl": ttl,
            "roundRobin": [{"value": value, "disableFlag": False}],
            "gtdLocation": 1
        }

    elif rtype == "CNAME":
        if not value.endswith("."):
            value += "."
        return {
            "name": record,
            "ttl": ttl,
            "host": value
        }

    elif rtype == "TXT":
        return {
            "name": record,
            "ttl": ttl,
            "roundRobin": [{"value": value, "disableFlag": False}]
        }

    else:
        raise ValueError(f"Unsupported record type: {rtype}")


# ---------------- ADD ----------------
def add_record(domain_id, rtype, record, value, ttl):
    url = f"{BASE_URL}/domains/{domain_id}/records/{rtype}"
    payload = build_payload(rtype, record, value, ttl)

    try:
        response = requests.post(url, headers=_headers(), json=payload, verify=False)

        if response.status_code in [200, 201]:
            return "Successful"

        print("[Constellix ADD ERROR]", response.text)
        return "Err"

    except Exception as e:
        print(f"[Constellix ADD Exception] {e}")
        return "Err"


# ---------------- MODIFY ----------------
def modify_record(domain_id, rtype, record_id, record, value, ttl):
    url = f"{BASE_URL}/domains/{domain_id}/records/{rtype}/{record_id}"
    payload = build_payload(rtype, record, value, ttl)

    try:
        response = requests.put(url, headers=_headers(), json=payload, verify=False)

        if response.status_code in [200, 201]:
            return "Successful"

        print("[Constellix MOD ERROR]", response.text)
        return "Err"

    except Exception as e:
        print(f"[Constellix MOD Exception] {e}")
        return "Err"


# ---------------- DELETE ----------------
def delete_record(domain_id, rtype, record_id):
    url = f"{BASE_URL}/domains/{domain_id}/records/{rtype}/{record_id}"

    try:
        response = requests.delete(url, headers=_headers(), verify=False)

        if response.status_code in [200, 201]:
            return "Successful"

        print("[Constellix DEL ERROR]", response.text)
        return "Err"

    except Exception as e:
        print(f"[Constellix DEL Exception] {e}")
        return "Err"


# ---------------- MAIN FUNCTION (COMPATIBLE) ----------------
def ctel(record, value, action, zone, rtype, ttl):
    print(f"[Constellix] Processing: {record}.{zone}")

    domain_id = get_domain_id(zone)

    if not domain_id:
        print("[Constellix] Invalid zone → skipping")
        return "Err"

    record_id = get_record_id(domain_id, rtype, record)

    # ---- ADD ----
    if action == "add":
        return add_record(domain_id, rtype, record, value, ttl)

    # ---- MODIFY ----
    elif action == "mod":
        if record_id:
            return modify_record(domain_id, rtype, record_id, record, value, ttl)
        else:
            print("[Constellix] Record not found → fallback to ADD")
            return add_record(domain_id, rtype, record, value, ttl)

    # ---- DELETE ----
    elif action == "del":
        if record_id:
            return delete_record(domain_id, rtype, record_id)
        else:
            print("[Constellix] Record not found → cannot delete")
            return "Err"

    else:
        print("[Constellix] Invalid action")
        return "Err"