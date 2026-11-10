from ipaddress import ip_address

from django.conf import settings


def get_client_ip(request):
    try:
        peer = ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return None
    if any(peer in network for network in settings.TRUSTED_PROXY_NETWORKS):
        # Only a proxy that overwrites this single-IP header may be trusted.
        try:
            return str(ip_address(request.META.get("HTTP_X_REAL_IP", "")))
        except ValueError:
            pass
    return str(peer)
