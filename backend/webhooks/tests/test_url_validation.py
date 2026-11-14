import socket

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from webhooks.validators import validate_webhook_url


def fake_dns(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    # Every hostname resolves to ip, so no test touches the real network.
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [(0, 0, 0, '', (ip, 443))])


@pytest.mark.parametrize('url', ['https://8.8.8.8/hook', 'https://hooks.example.com/hook'])
def test_public_https_urls_are_allowed(monkeypatch: pytest.MonkeyPatch, url: str) -> None:
    fake_dns(monkeypatch, '93.184.215.14')
    validate_webhook_url(url)


@pytest.mark.parametrize('url', ['http://8.8.8.8/hook', 'ftp://8.8.8.8/hook'])
def test_only_https_is_allowed(url: str) -> None:
    with pytest.raises(ValidationError):
        validate_webhook_url(url)


@pytest.mark.parametrize('ip', ['127.0.0.1', '10.0.0.5', '172.16.0.1', '192.168.1.1', '169.254.169.254', '::1'])
def test_hosts_resolving_to_internal_addresses_are_rejected(monkeypatch: pytest.MonkeyPatch, ip: str) -> None:
    fake_dns(monkeypatch, ip)
    with pytest.raises(ValidationError):
        validate_webhook_url('https://hooks.example.com/hook')


@pytest.mark.parametrize('url', ['https://example.com:70000/hook', 'https://example.com:abc/hook'])
def test_invalid_ports_are_rejected(url: str) -> None:
    with pytest.raises(ValidationError, match='invalid port'):
        validate_webhook_url(url)


def test_hostnames_dns_cannot_encode_are_rejected() -> None:
    with pytest.raises(ValidationError, match='Could not resolve'):
        validate_webhook_url(f'https://{"a" * 64}.com/hook')  # DNS labels max out at 63 characters


@override_settings(WEBHOOK_DEV_ALLOWED_HOSTS=['localhost', 'webhook-receiver'])
def test_the_dev_allowlist_permits_the_local_receiver() -> None:
    validate_webhook_url('http://localhost:8027/hook')
    validate_webhook_url('http://webhook-receiver:8027/hook')


@override_settings(WEBHOOK_DEV_ALLOWED_HOSTS=[])
def test_without_the_allowlist_the_local_receiver_is_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_webhook_url('http://localhost:8027/hook')
