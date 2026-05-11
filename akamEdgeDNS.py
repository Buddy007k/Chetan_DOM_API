import requests
import json
import configparser
from akamai.edgegrid import EdgeGridAuth


def get_session(zone):
    config = configparser.ConfigParser(strict=False)
    config.read('./config/config.cfg')

    grp2_zone_list = ['gaana.com', 'magicbricks.com']

    if zone in grp2_zone_list:
        section = 'akamg2'
    else:
        section = 'akam'

    return {
        "host": config.get(section, 'host'),
        "client_token": config.get(section, 'client_token'),
        "client_secret": config.get(section, 'client_secret'),
        "access_token": config.get(section, 'access_token')
    }


def create_session(auth):
    session = requests.Session()
    session.auth = EdgeGridAuth(
        client_token=auth["client_token"],
        client_secret=auth["client_secret"],
        access_token=auth["access_token"]
    )
    return session


def akam(record, value, action, zone, rtype, ttl):
    fqdn = f"{record}.{zone}"
    print(f"[Akamai] Processing: {fqdn}")

    auth = get_session(zone)
    baseurl = f"https://{auth['host']}"
    session = create_session(auth)

    url = f"{baseurl}/config-dns/v2/zones/{zone}/names/{record}/types/{rtype}"

    payload = {
        "name": record,
        "type": rtype,
        "ttl": int(ttl),
        "rdata": [value]
    }

    headers = {"Content-Type": "application/json"}

    try:
        # ---------- MOD ----------
        if action == "mod":
            response = session.put(url, data=json.dumps(payload), headers=headers)
            print("[Akamai MOD RESPONSE]:", response.text)

            if response.status_code in [200, 201]:
                return "Successful"

            # If record not found → fallback to ADD
            if "does not exist" in response.text.lower():
                print("[Akamai] MOD failed → trying ADD")
                return akam(record, value, "add", zone, rtype, ttl)

            return response.text

        # ---------- ADD ----------
        elif action == "add":
            response = session.post(url, data=json.dumps(payload), headers=headers)
            print("[Akamai ADD RESPONSE]:", response.text)

            if response.status_code in [200, 201]:
                return "Successful"

            return response.text

        # ---------- DELETE ----------
        elif action == "del":
            response = session.delete(url, headers=headers)

            if response.status_code in [202, 204]:
                return "Successful"

            return response.text

        else:
            return "Err"

    except Exception as e:
        print("[Akamai Exception]:", str(e))
        return "Err"