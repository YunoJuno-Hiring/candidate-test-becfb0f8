import ipaddress
import socket
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_webhook_url(url: str) -> None:
    """Reject URLs our server shouldn't POST to: anything but https, or hosts that resolve internally (SSRF)."""
    parts = urlsplit(url)
    host = parts.hostname or ''
    if host in settings.WEBHOOK_DEV_ALLOWED_HOSTS:
        return  # dev only: the local receiver, over plain http
    if parts.scheme != 'https':
        raise ValidationError('Webhook URLs must use https.')

    # Every address the host resolves to must be public, or one internal record would get through.
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, parts.port or 443)}
    except socket.gaierror as error:
        raise ValidationError(f'Could not resolve {host}.') from error
    if not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise ValidationError('Webhook URLs must not point at private or internal addresses.')
