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
