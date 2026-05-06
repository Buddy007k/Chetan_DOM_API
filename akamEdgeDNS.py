import requests
import json
import configparser
from akamai.edgegrid import EdgeGridAuth


# ---------------- SESSION BUILDER ----------------
def get_session(zone):
    grp2_zone_list = ['gaana.com', 'magicbricks.com']

    config = configparser.ConfigParser(strict=False)
    config.read_file(open(r'./config/config.cfg'))

    if zone in grp2_zone_list:
        client_secret = config.get('akamg2', 'client_secret')
        host = config.get('akamg2', 'host')
        access_token = config.get('akamg2', 'access_token')
        client_token = config.get('akamg2', 'client_token')
    else:
        client_secret = config.get('akam', 'client_secret')
        host = config.get('akam', 'host')
        access_token = config.get('akam', 'access_token')
        client_token = config.get('akam', 'client_token')

    baseurl = "https://" + host

    s = requests.Session()
    s.auth = EdgeGridAuth(
        client_token=client_token,
        client_secret=client_secret,
        access_token=access_token
    )

    return baseurl, s


# ---------------- CORE FUNCTIONS ----------------
def add_record(baseurl, zone, record, rtype, value, ttl, session):
    url = f"{baseurl}/config-dns/v2/zones/{zone}/names/{record}/types/{rtype}"

    payload = {
        "name": record,
        "type": rtype,
        "rdata": [value],
        "ttl": int(ttl)
    }

    response = session.post(url, json=payload)
    print("[Akamai ADD RESPONSE]:", response.text)

    if response.status_code in [200, 201]:
        return "Successful"
    else:
        return response.text


def mod_record(baseurl, zone, record, rtype, value, ttl, session):
    url = f"{baseurl}/config-dns/v2/zones/{zone}/names/{record}/types/{rtype}"

    payload = {
        "name": record,
        "type": rtype,
        "rdata": [value],
        "ttl": int(ttl)
    }

    response = session.put(url, json=payload)
    print("[Akamai MOD RESPONSE]:", response.text)

    if response.status_code in [200, 201]:
        return "Successful"
    else:
        return response.text


def del_record(baseurl, zone, record, rtype, session):
    url = f"{baseurl}/config-dns/v2/zones/{zone}/names/{record}/types/{rtype}"

    response = session.delete(url)
    print("[Akamai DEL RESPONSE]:", response.text)

    if response.status_code in [202, 204]:
        return "Successful"
    else:
        return response.text


# ---------------- MAIN WRAPPER ----------------
def akam(record, value, action, zone, rtype, ttl):
    print(f"[Akamai] Processing: {record}.{zone}")

    baseurl, session = get_session(zone)

    try:
        # -------- MOD --------
        if action == "mod":
            result = mod_record(baseurl, zone, record, rtype, value, ttl, session)

            if result == "Successful":
                return "Successful"

            # fallback to ADD
            print("[Akamai] MOD failed → trying ADD")
            result = add_record(baseurl, zone, record, rtype, value, ttl, session)

            return result

        # -------- ADD --------
        elif action == "add":
            return add_record(baseurl, zone, record, rtype, value, ttl, session)

        # -------- DELETE --------
        elif action == "del":
            return del_record(baseurl, zone, record, rtype, session)

        else:
            return "Err"

    except Exception as e:
        print("[Akamai ERROR]:", e)
        return "Err"