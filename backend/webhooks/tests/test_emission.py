import json

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from accounts.models import Company
from webhooks.models import WebhookEndpoint, WebhookPayload

CONTRACT = {'daily_rate': '600.00', 'start_date': '2026-06-01', 'end_date': '2026-12-31', 'status': 'active'}


def create_contract(admin_client: APIClient, freelancer_user: User, **overrides: str) -> int:
    resp = admin_client.post('/api/contracts/', {**CONTRACT, 'freelancer': freelancer_user.freelancer.id, **overrides})
    return int(resp.status_code)


@pytest.mark.django_db
def test_a_new_contract_creates_a_payload_for_each_of_the_companys_endpoints(
    admin_client: APIClient, freelancer_user: User, northstar: Company, meridian: Company
) -> None:
    active = WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/a')
    paused = WebhookEndpoint.objects.create(
        company=northstar, url='https://8.8.8.8/b', status=WebhookEndpoint.Status.PAUSED
    )
    other = WebhookEndpoint.objects.create(company=meridian, url='https://8.8.8.8/c')

    assert create_contract(admin_client, freelancer_user) == 201

    assert active.payloads.get().status == WebhookPayload.Status.QUEUED
    assert paused.payloads.get().status == WebhookPayload.Status.CREATED  # saved, not sent
    assert not other.payloads.exists()


@pytest.mark.django_db
def test_the_payload_is_thin_and_versioned(admin_client: APIClient, freelancer_user: User, northstar: Company) -> None:
    WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/hook')

    create_contract(admin_client, freelancer_user)

    body = WebhookPayload.objects.get().payload
    assert (body['type'], body['version']) == ('contract.created', 1)
    assert {'id', 'created_at', 'data'} <= body.keys()
    assert set(body['data']) == {'id', 'status', 'start_date', 'end_date', 'download_url'}
    # No personal data or commercial terms cross the boundary.
    assert 'daily_rate' not in json.dumps(body)
    assert freelancer_user.freelancer.name not in json.dumps(body)


@pytest.mark.django_db
def test_no_payload_when_contract_creation_fails(
    admin_client: APIClient, freelancer_user: User, northstar: Company
) -> None:
    WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/hook')

    assert create_contract(admin_client, freelancer_user, end_date='2026-01-01') == 400  # ends before it starts

    assert not WebhookPayload.objects.exists()
