from datetime import timedelta
from typing import Any

import httpx
import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from django_tasks_db.models import DBTaskResult

from accounts.models import Company
from webhooks import delivery, services, tasks
from webhooks.models import WebhookEndpoint, WebhookPayload

Status = WebhookPayload.Status


@pytest.fixture
def endpoint(northstar: Company, admin_user: User) -> WebhookEndpoint:
    return WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/hook')


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[tuple[int, str]]:
    # Stands in for the real send, recording what deliver_payload handed over and in what status.
    calls: list[tuple[int, str]] = []
    monkeypatch.setattr(delivery, 'deliver', lambda payload: calls.append((payload.id, payload.status)))
    return calls


def make_payload(endpoint: WebhookEndpoint, *moves: str) -> WebhookPayload:
    payload = WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload={'id': 'evt_1'})
    for to_status in moves:
        payload.transition(to_status)
    return payload


def jobs_for(payload: WebhookPayload) -> list[DBTaskResult[Any, Any]]:
    return list(
        DBTaskResult.objects.filter(task_path='webhooks.tasks.deliver_payload', args_kwargs__args=[payload.id])
    )


def reply(status: int) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(status)))


# deliver_payload: what the worker runs


@pytest.mark.django_db
def test_a_queued_payload_is_sent(endpoint: WebhookEndpoint, sent: list[tuple[int, str]]) -> None:
    payload = make_payload(endpoint, Status.QUEUED)

    tasks.deliver_payload.call(payload.id)

    assert sent == [(payload.id, Status.QUEUED)]


@pytest.mark.django_db
def test_a_failed_payload_is_requeued_then_sent(endpoint: WebhookEndpoint, sent: list[tuple[int, str]]) -> None:
    payload = make_payload(endpoint, Status.QUEUED, Status.FAILED)

    tasks.deliver_payload.call(payload.id)

    assert sent == [(payload.id, Status.QUEUED)]
    assert payload.events.filter(from_status=Status.FAILED, to_status=Status.QUEUED).exists()


@pytest.mark.django_db
@pytest.mark.parametrize('moves', [(Status.QUEUED, Status.DELIVERED), ()], ids=['delivered', 'created'])
def test_a_payload_that_is_not_queued_is_left_alone(
    endpoint: WebhookEndpoint, sent: list[tuple[int, str]], moves: tuple[str, ...]
) -> None:
    # Another worker already had it, or it was never queued: sending again would deliver it twice.
    payload = make_payload(endpoint, *moves)

    tasks.deliver_payload.call(payload.id)

    assert sent == []


@pytest.mark.django_db
def test_a_deleted_payload_is_skipped(endpoint: WebhookEndpoint, sent: list[tuple[int, str]]) -> None:
    payload = make_payload(endpoint, Status.QUEUED)
    endpoint.delete()  # cascades to its payloads, but the job is already in the queue

    tasks.deliver_payload.call(payload.id)

    assert sent == []


# Enqueueing: without these jobs nothing is ever sent or retried


@pytest.mark.django_db
def test_emitting_an_event_enqueues_a_job_to_send_it(northstar: Company, endpoint: WebhookEndpoint) -> None:
    services.emit(northstar, 'contract.created', {})

    payload = endpoint.payloads.get()
    assert len(jobs_for(payload)) == 1


@pytest.mark.django_db
def test_a_failed_attempt_enqueues_its_retry_for_the_scheduled_time(endpoint: WebhookEndpoint) -> None:
    payload = make_payload(endpoint, Status.QUEUED)
    DBTaskResult.objects.all().delete()  # leave only the jobs the attempt enqueues

    delivery.deliver(payload, client=reply(503))

    [retry] = jobs_for(payload)
    assert retry.run_after == payload.next_attempt_at


@pytest.mark.django_db
def test_giving_up_enqueues_nothing(endpoint: WebhookEndpoint) -> None:
    payload = make_payload(endpoint, Status.QUEUED)
    payload.events.update(created_at=timezone.now() - timedelta(days=7))  # first queued a week ago
    DBTaskResult.objects.all().delete()

    delivery.deliver(payload, client=reply(503))

    assert jobs_for(payload) == []
