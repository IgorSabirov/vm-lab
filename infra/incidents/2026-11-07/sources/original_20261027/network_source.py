"""Installed control-plane helpers; no credentials are returned or logged."""
import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request

def metadata(path):
    request = urllib.request.Request(
        "http://169.254.169.254/computeMetadata/v1/" + path,
        headers={"Metadata-Flavor": "Google"})
    # Metadata must not traverse a user-configured HTTP proxy.
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=4) as response:
        return response.read(65536).decode().strip()

def public_ip():
    value = metadata("instance/network-interfaces/0/access-configs/0/external-ip")
    address = ipaddress.ip_address(value)
    if address.version != 4 or not address.is_global:
        raise RuntimeError("У ВМ нет публичного IPv4 в метаданных.")
    return str(address)

def reserve_ip(ip):
    try:
        token = json.loads(metadata("instance/service-accounts/default/token"))["access_token"]
        folder = metadata("instance/vendor/folder-id")
        if not folder or len(folder) > 50:
            raise ValueError("Invalid folder")
        def api(path, body=None, method=None):
            req = urllib.request.Request("https://vpc.api.cloud.yandex.net/vpc/v1/" + path,
                data=None if body is None else json.dumps(body).encode(), method=method,
                headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=12) as response:
                return json.load(response)
        page = ""
        target = None
        for _ in range(20):
            query = urllib.parse.urlencode({"folderId": folder, "pageSize": "1000", "pageToken": page})
            listing = api("addresses?" + query)
            target = next((a for a in listing.get("addresses", [])
                if a.get("externalIpv4Address", {}).get("address") == ip), None)
            if target:
                break
            page = listing.get("nextPageToken", "")
            if not page:
                break
        if not target:
            return {"reserved": None, "reason": "Адрес не найден через API Яндекса"}
        if not target.get("reserved"):
            api("addresses/" + urllib.parse.quote(target["id"], safe=""),
                {"updateMask": "reserved", "reserved": True}, "PATCH")
            import time
            for _ in range(10):
                target = api("addresses/" + urllib.parse.quote(target["id"], safe=""))
                if target.get("reserved"):
                    break
                time.sleep(1)
        return {"reserved": bool(target.get("reserved")), "address_id": target["id"]}
    except (OSError, ValueError, KeyError):
        return {"reserved": None, "reason": "Нет доступных прав Яндекса для проверки/закрепления IP"}

