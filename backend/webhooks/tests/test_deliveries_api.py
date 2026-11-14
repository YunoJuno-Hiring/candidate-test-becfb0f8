import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from accounts.models import Company
from webhooks.models import WebhookEndpoint, WebhookPayload

Status = WebhookPayload.Status


@pytest.fixture
def endpoint(northstar: Company) -> WebhookEndpoint:
    return WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/hook')


def deliveries_url(endpoint: WebhookEndpoint) -> str:
    return f'/api/webhook-endpoints/{endpoint.id}/deliveries/'


def failed_then_delivered(endpoint: WebhookEndpoint) -> WebhookPayload:
    payload = WebhookPayload.objects.create(
        endpoint=endpoint, url=endpoint.url, payload={'id': 'evt_1', 'type': 'contract.created'}
    )
    payload.transition(Status.QUEUED)
    payload.transition(Status.FAILED, response_code=503, error='Service Unavailable')
    payload.transition(Status.QUEUED)
    payload.transition(Status.DELIVERED, response_code=200)
    return payload


@pytest.mark.django_db
def test_the_log_shows_what_fired_and_each_numbered_attempt(
    admin_client: APIClient, endpoint: WebhookEndpoint
) -> None:
    failed_then_delivered(endpoint)

    [delivery] = admin_client.get(deliveries_url(endpoint)).data

    assert (delivery['event_id'], delivery['event_type'], delivery['status']) == (
        'evt_1',
        'contract.created',
        'delivered',
    )
    attempts = [(a['attempt'], a['status'], a['response_code'], a['error']) for a in delivery['attempts']]
    assert attempts == [(1, 'failed', 503, 'Service Unavailable'), (2, 'delivered', 200, '')]


@pytest.mark.django_db
def test_the_log_shows_the_20_most_recent_newest_first(admin_client: APIClient, endpoint: WebhookEndpoint) -> None:
    for number in range(25):
        WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload={'id': f'evt_{number}'})

    data = admin_client.get(deliveries_url(endpoint)).data

    assert len(data) == 20
    assert data[0]['event_id'] == 'evt_24'


@pytest.mark.django_db
def test_another_companys_log_is_not_found(admin_client: APIClient, meridian: Company) -> None:
    other = WebhookEndpoint.objects.create(company=meridian, url='https://8.8.8.8/hook')

    assert admin_client.get(deliveries_url(other)).status_code == 404


@pytest.mark.django_db
def test_freelancers_cannot_read_the_log(freelancer_client: APIClient, endpoint: WebhookEndpoint) -> None:
    assert freelancer_client.get(deliveries_url(endpoint)).status_code == 403


@pytest.mark.django_db
def test_the_list_summarises_each_endpoints_last_delivery(admin_client: APIClient, endpoint: WebhookEndpoint) -> None:
    assert admin_client.get('/api/webhook-endpoints/').data[0]['last_delivery'] is None

    failed_then_delivered(endpoint)

    last = admin_client.get('/api/webhook-endpoints/').data[0]['last_delivery']
    assert (last['status'], last['response_code']) == ('delivered', 200)


def list_queries(client: APIClient) -> tuple[int, list[dict[str, object]]]:
    with CaptureQueriesContext(connection) as queries:
        data = client.get('/api/webhook-endpoints/').data
    return len(queries), data


@pytest.mark.django_db
def test_listing_endpoints_takes_the_same_queries_however_many_there_are(
    admin_client: APIClient, endpoint: WebhookEndpoint, northstar: Company
) -> None:
    failed_then_delivered(endpoint)
    one, _ = list_queries(admin_client)

    others = [WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/hook') for _ in range(5)]
    for other in others[:3]:
        payload = WebhookPayload.objects.create(endpoint=other, url=other.url, payload={'id': f'evt_{other.id}'})
        payload.transition(Status.QUEUED)
        payload.transition(Status.FAILED, response_code=500)
    six, data = list_queries(admin_client)

    assert six == one  # an N+1 would add a query per endpoint
    last = {row['id']: row['last_delivery'] for row in data}
    assert last[endpoint.id]['response_code'] == 200  # type: ignore[index]  # each row gets its own latest attempt
    assert [last[other.id] and last[other.id]['response_code'] for other in others] == [500, 500, 500, None, None]  # type: ignore[index]
