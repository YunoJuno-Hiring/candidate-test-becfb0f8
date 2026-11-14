import ipaddress
import socket
from urllib.parse import urlsplit

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_webhook_url(url: str) -> None:
    """Reject URLs our server shouldn't POST to: anything but https, or hosts that resolve internally (SSRF)."""
    parts = urlsplit(url)
    host = parts.hostname or ''
    try:
        port = parts.port or 443  # urlsplit only checks the port when it's read: 70000 or 'abc' raise here
    except ValueError as error:
        raise ValidationError('Webhook URL has an invalid port.') from error
    if host in settings.WEBHOOK_DEV_ALLOWED_HOSTS:
        return  # dev only: the local receiver, over plain http
    if parts.scheme != 'https':
        raise ValidationError('Webhook URLs must use https.')

    # Every address the host resolves to must be public, or one internal record would get through.
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(host, port)}
    except (socket.gaierror, UnicodeError) as error:  # UnicodeError: a name IDNA can't encode, e.g. a 64+ char label
        raise ValidationError(f'Could not resolve {host}.') from error
    if not all(ipaddress.ip_address(address).is_global for address in addresses):
        raise ValidationError('Webhook URLs must not point at private or internal addresses.')
