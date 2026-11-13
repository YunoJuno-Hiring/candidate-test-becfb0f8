import pytest

from accounts.models import Company
from webhooks.models import WebhookEndpoint, WebhookPayload

Status = WebhookPayload.Status


@pytest.fixture
def payload(northstar: Company) -> WebhookPayload:
    endpoint = WebhookEndpoint.objects.create(company=northstar, url='https://example.com/hook')
    return WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload={'type': 'test'})


def moves(payload: WebhookPayload) -> list[tuple[str, str]]:
    return list(payload.events.values_list('from_status', 'to_status'))


@pytest.mark.django_db
def test_happy_path_records_each_move(payload: WebhookPayload) -> None:
    assert payload.transition(Status.QUEUED)
    assert payload.transition(Status.DELIVERED, response_code=200)

    payload.refresh_from_db()
    assert payload.status == Status.DELIVERED
    assert moves(payload) == [(Status.CREATED, Status.QUEUED), (Status.QUEUED, Status.DELIVERED)]
    assert payload.events.get(to_status=Status.DELIVERED).response_code == 200


@pytest.mark.django_db
def test_sad_path_requeues_then_delivers(payload: WebhookPayload) -> None:
    payload.transition(Status.QUEUED)
    payload.transition(Status.FAILED, response_code=503, error='Service Unavailable')
    payload.transition(Status.QUEUED)
    payload.transition(Status.DELIVERED, response_code=200)

    failure = payload.events.get(to_status=Status.FAILED)
    assert (failure.response_code, failure.error) == (503, 'Service Unavailable')
    # The attempt number is the count of times it was queued.
    assert payload.events.filter(to_status=Status.QUEUED).count() == 2


@pytest.mark.django_db
def test_illegal_move_raises_and_writes_nothing(payload: WebhookPayload) -> None:
    with pytest.raises(ValueError, match='created > delivered'):
        payload.transition(Status.DELIVERED)

    payload.refresh_from_db()
    assert payload.status == Status.CREATED
    assert not payload.events.exists()


@pytest.mark.django_db
def test_stale_worker_loses_the_race_without_writing(payload: WebhookPayload) -> None:
    # Two workers load the same row; the first moves it, the second still thinks it's 'created'.
    first = WebhookPayload.objects.get(pk=payload.pk)
    second = WebhookPayload.objects.get(pk=payload.pk)

    assert first.transition(Status.QUEUED) is True
    assert second.transition(Status.QUEUED) is False

    assert moves(payload) == [(Status.CREATED, Status.QUEUED)]
