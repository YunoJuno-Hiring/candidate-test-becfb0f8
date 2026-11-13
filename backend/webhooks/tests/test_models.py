import base64

import pytest

from accounts.models import Company
from webhooks.models import WebhookEndpoint


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
