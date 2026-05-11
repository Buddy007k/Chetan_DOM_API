import boto3
import configparser


def get_client():
    config = configparser.ConfigParser(strict=False)
    config.read('./config/config.cfg')

    access_key = config.get('r53', 'access_key')
    secret = config.get('r53', 'secret')

    client = boto3.client(
        'route53',
        aws_access_key_id=access_key,
        aws_secret_access_key=secret
    )

    return client


def get_zone_id(zone, client):
    """Get Hosted Zone ID safely"""
    if not zone.endswith("."):
        zone = zone + "."

    response = client.list_hosted_zones_by_name(DNSName=zone)

    for z in response.get("HostedZones", []):
        if z["Name"] == zone:
            return z["Id"].split("/")[-1]

    return None


def awsdns(record, value, action, zone, rtype, ttl):
    fqdn = f"{record}.{zone}"
    print(f"[AWS] Processing: {fqdn}")

    try:
        client = get_client()

        # -------- GET ZONE --------
        zone_id = get_zone_id(zone, client)

        if not zone_id:
            print(f"[AWS] Hosted Zone NOT found: {zone}")
            return "Err"

        print(f"[AWS] Using Zone ID: {zone_id}")

        # -------- ACTION MAP --------
        if action == "add":
            change_action = "CREATE"
        elif action == "mod":
            change_action = "UPSERT"
        elif action == "del":
            change_action = "DELETE"
        else:
            return "Err"

        # -------- FORMAT VALUE --------
        if rtype == "TXT":
            rr_value = f"\"{value}\""
        else:
            rr_value = value

        payload = {
            "Comment": "DNS automation",
            "Changes": [
                {
                    "Action": change_action,
                    "ResourceRecordSet": {
                        "Name": fqdn,
                        "Type": rtype,
                        "TTL": int(ttl),
                        "ResourceRecords": [
                            {"Value": rr_value}
                        ]
                    }
                }
            ]
        }

        # -------- EXECUTE --------
        response = client.change_resource_record_sets(
            HostedZoneId=zone_id,
            ChangeBatch=payload
        )

        print("[AWS RESPONSE]:", response)

        if response["ResponseMetadata"]["HTTPStatusCode"] == 200:
            return "Successful"
        else:
            return str(response)

    except Exception as e:
        print("[AWS ERROR]:", str(e))
        return "Err"