import pytest
from rest_framework.test import APIClient

from accounts.models import Company
from webhooks.models import WebhookEndpoint, WebhookPayload

URL = '/api/webhook-endpoints/'
VALID = 'https://8.8.8.8/hook'  # an IP literal, so URL validation needs no DNS lookup


@pytest.fixture
def endpoint(northstar: Company) -> WebhookEndpoint:
    return WebhookEndpoint.objects.create(company=northstar, url=VALID)


@pytest.mark.django_db
def test_freelancers_cannot_use_the_api(freelancer_client: APIClient) -> None:
    assert freelancer_client.get(URL).status_code == 403
    assert freelancer_client.post(URL, {'url': VALID}).status_code == 403


@pytest.mark.django_db
def test_admins_see_only_their_companys_endpoints(
    admin_client: APIClient, endpoint: WebhookEndpoint, meridian: Company
) -> None:
    WebhookEndpoint.objects.create(company=meridian, url=VALID)

    assert [e['id'] for e in admin_client.get(URL).data] == [endpoint.id]


@pytest.mark.django_db
def test_another_companys_endpoint_is_not_found(admin_client: APIClient, meridian: Company) -> None:
    other = WebhookEndpoint.objects.create(company=meridian, url=VALID)

    assert admin_client.patch(f'{URL}{other.id}/', {'url': VALID}).status_code == 404
    assert admin_client.post(f'{URL}{other.id}/reveal-secret/').status_code == 404
    assert admin_client.post(f'{URL}{other.id}/test/').status_code == 404
    assert admin_client.delete(f'{URL}{other.id}/').status_code == 404


@pytest.mark.django_db
def test_create_returns_the_secret_but_listing_does_not(admin_client: APIClient, northstar: Company) -> None:
    resp = admin_client.post(URL, {'url': VALID})

    assert resp.status_code == 201
    assert resp.data['secret'].startswith('whsec_')
    assert resp.data['status'] == 'active'
    assert 'no-store' in resp['Cache-Control']
    assert WebhookEndpoint.objects.get(pk=resp.data['id']).company == northstar
    assert 'secret' not in admin_client.get(URL).data[0]


@pytest.mark.django_db
def test_clients_cannot_set_the_secret_or_company(admin_client: APIClient, meridian: Company) -> None:
    resp = admin_client.post(URL, {'url': VALID, 'secret': 'whsec_mine', 'company': meridian.id})

    assert resp.data['secret'] != 'whsec_mine'
    assert WebhookEndpoint.objects.get(pk=resp.data['id']).company != meridian


@pytest.mark.django_db
def test_reveal_secret(admin_client: APIClient, endpoint: WebhookEndpoint) -> None:
    resp = admin_client.post(f'{URL}{endpoint.id}/reveal-secret/')

    assert resp.data == {'secret': endpoint.secret}
    assert 'no-store' in resp['Cache-Control']


@pytest.mark.django_db
def test_admins_can_edit_the_url(admin_client: APIClient, endpoint: WebhookEndpoint) -> None:
    assert admin_client.patch(f'{URL}{endpoint.id}/', {'url': 'https://8.8.4.4/new'}).status_code == 200

    endpoint.refresh_from_db()
    assert endpoint.url == 'https://8.8.4.4/new'


@pytest.mark.django_db
def test_invalid_urls_are_rejected(admin_client: APIClient) -> None:
    resp = admin_client.post(URL, {'url': 'http://8.8.8.8/hook'})

    assert resp.status_code == 400
    assert 'url' in resp.data


@pytest.mark.django_db
@pytest.mark.parametrize(('to_status', 'expected'), [('paused', 200), ('active', 200), ('disabled', 400)])
def test_admins_can_pause_and_resume_but_not_disable(
    admin_client: APIClient, endpoint: WebhookEndpoint, to_status: str, expected: int
) -> None:
    assert admin_client.patch(f'{URL}{endpoint.id}/', {'status': to_status}).status_code == expected


@pytest.mark.django_db
def test_resuming_queues_only_the_most_recent_saved_payload(
    admin_client: APIClient, endpoint: WebhookEndpoint
) -> None:
    endpoint.status = WebhookEndpoint.Status.PAUSED
    endpoint.save()
    older = WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload={})
    newer = WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload={})

    admin_client.patch(f'{URL}{endpoint.id}/', {'status': 'active'})

    older.refresh_from_db()
    newer.refresh_from_db()
    assert (older.status, newer.status) == (WebhookPayload.Status.CREATED, WebhookPayload.Status.QUEUED)


@pytest.mark.django_db
@pytest.mark.parametrize('status', ['active', 'paused', 'disabled'])
def test_test_events_are_queued_whatever_the_status(
    admin_client: APIClient, endpoint: WebhookEndpoint, status: str
) -> None:
    endpoint.status = status
    endpoint.save()

    assert admin_client.post(f'{URL}{endpoint.id}/test/').status_code == 202

    sent = endpoint.payloads.get()
    assert (sent.payload['type'], sent.status) == ('webhook.test', WebhookPayload.Status.QUEUED)


@pytest.mark.django_db
def test_delete_takes_the_history_with_it(admin_client: APIClient, endpoint: WebhookEndpoint) -> None:
    WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload={})

    assert admin_client.delete(f'{URL}{endpoint.id}/').status_code == 204
    assert not WebhookEndpoint.objects.exists()
    assert not WebhookPayload.objects.exists()
