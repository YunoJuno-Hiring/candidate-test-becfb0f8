import base64
from datetime import timedelta

import pytest
from django.utils import timezone

from accounts.models import Company
from webhooks.models import ROTATION_GRACE, WebhookEndpoint


def make_endpoint(company: Company) -> WebhookEndpoint:
    return WebhookEndpoint.objects.create(company=company, url='https://example.com/hook')


@pytest.mark.django_db
def test_new_endpoint_gets_a_standard_webhooks_secret(northstar: Company) -> None:
    endpoint = make_endpoint(northstar)

    prefix, _, encoded = endpoint.secret.partition('_')
    assert prefix == 'whsec'
    assert len(base64.b64decode(encoded, validate=True)) == 32


@pytest.mark.django_db
def test_each_endpoint_gets_its_own_secret(northstar: Company) -> None:
    assert make_endpoint(northstar).secret != make_endpoint(northstar).secret


@pytest.mark.django_db
def test_saving_an_endpoint_keeps_its_secret(northstar: Company) -> None:
    # The default only applies on creation; a later save must not rotate the secret.
    endpoint = make_endpoint(northstar)
    secret = endpoint.secret

    endpoint.status = WebhookEndpoint.Status.PAUSED
    endpoint.save()
    endpoint.refresh_from_db()

    assert endpoint.secret == secret


@pytest.mark.django_db
def test_rotating_signs_with_both_secrets_until_the_grace_period_ends(northstar: Company) -> None:
    endpoint = make_endpoint(northstar)
    old = endpoint.secret

    endpoint.rotate_secret()
    endpoint.refresh_from_db()
    assert endpoint.signing_secrets() == [endpoint.secret, old]  # current first

    endpoint.previous_secret_expires_at = timezone.now() - timedelta(seconds=1)
    assert endpoint.signing_secrets() == [endpoint.secret]


@pytest.mark.django_db
def test_rotating_twice_keeps_only_the_latest_previous_secret(northstar: Company) -> None:
    endpoint = make_endpoint(northstar)
    first = endpoint.secret
    endpoint.rotate_secret()
    second = endpoint.secret
    endpoint.rotate_secret()

    assert endpoint.signing_secrets() == [endpoint.secret, second]
    assert first not in endpoint.signing_secrets()
    assert endpoint.previous_secret_expires_at is not None
    assert endpoint.previous_secret_expires_at <= timezone.now() + ROTATION_GRACE
