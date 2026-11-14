import base64
import hashlib
import hmac
import json
import logging
import smtplib
import socket
from collections.abc import Callable
from datetime import timedelta
from typing import Any

import httpx
import pytest
from django.contrib.auth.models import User
from django.core import mail
from django.utils import timezone

from accounts.models import Company
from webhooks import delivery
from webhooks.delivery import deliver
from webhooks.models import WebhookEndpoint, WebhookPayload

Status = WebhookPayload.Status


def client(status: int, seen: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        return httpx.Response(status)

    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture
def endpoint(northstar: Company, admin_user: User) -> WebhookEndpoint:
    return WebhookEndpoint.objects.create(company=northstar, url='https://8.8.8.8/hook')


@pytest.fixture
def new_payload(endpoint: WebhookEndpoint) -> Callable[[], WebhookPayload]:
    def make() -> WebhookPayload:
        payload = WebhookPayload.objects.create(
            endpoint=endpoint, url=endpoint.url, payload={'id': 'evt_1', 'type': 'contract.created'}
        )
        payload.transition(Status.QUEUED)
        return payload

    return make


def attempt(payload: WebhookPayload, http: httpx.Client) -> None:
    # One delivery attempt; a retry is the sweeper moving it failed > queued first.
    if payload.status == Status.FAILED:
        payload.transition(Status.QUEUED)
    deliver(payload, client=http)


@pytest.mark.django_db
def test_a_2xx_response_marks_it_delivered(new_payload: Callable[[], WebhookPayload]) -> None:
    payload = new_payload()
    attempt(payload, client(200))

    assert payload.status == Status.DELIVERED
    assert payload.events.get(to_status=Status.DELIVERED).response_code == 200


@pytest.mark.django_db
def test_requests_are_signed_per_standard_webhooks(
    endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    seen: list[httpx.Request] = []
    attempt(new_payload(), client(200, seen))
    request = seen[0]

    msg_id, timestamp = request.headers['webhook-id'], request.headers['webhook-timestamp']
    key = base64.b64decode(endpoint.secret.removeprefix('whsec_'))
    signed = f'{msg_id}.{timestamp}.'.encode() + request.content
    expected = base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()
    assert request.headers['webhook-signature'] == f'v1,{expected}'
    assert json.loads(request.content)['id'] == msg_id  # the consumer's dedupe key


def expected_signature(secret: str, request: httpx.Request) -> str:
    key = base64.b64decode(secret.removeprefix('whsec_'))
    signed = f'{request.headers["webhook-id"]}.{request.headers["webhook-timestamp"]}.'.encode() + request.content
    return 'v1,' + base64.b64encode(hmac.new(key, signed, hashlib.sha256).digest()).decode()


@pytest.mark.django_db
def test_after_a_rotation_requests_carry_a_signature_from_each_secret(
    endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    old = endpoint.secret
    endpoint.rotate_secret()
    seen: list[httpx.Request] = []
    attempt(new_payload(), client(200, seen))

    assert seen[0].headers['webhook-signature'].split(' ') == [
        expected_signature(endpoint.secret, seen[0]),
        expected_signature(old, seen[0]),
    ]


@pytest.mark.django_db
def test_once_the_grace_period_ends_only_the_new_secret_signs(
    endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    endpoint.rotate_secret()
    endpoint.previous_secret_expires_at = timezone.now()
    endpoint.save()
    seen: list[httpx.Request] = []
    attempt(new_payload(), client(200, seen))

    assert seen[0].headers['webhook-signature'] == expected_signature(endpoint.secret, seen[0])


@pytest.mark.django_db
@pytest.mark.parametrize('status', [302, 404, 500, 503])
def test_anything_but_2xx_fails_and_schedules_a_retry(new_payload: Callable[[], WebhookPayload], status: int) -> None:
    payload = new_payload()
    attempt(payload, client(status))

    assert payload.status == Status.FAILED
    assert payload.events.get(to_status=Status.FAILED).response_code == status
    assert payload.next_attempt_at is not None and payload.next_attempt_at > timezone.now()


@pytest.mark.django_db
def test_a_connection_error_fails_with_the_error_recorded(new_payload: Callable[[], WebhookPayload]) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError('Connection refused')

    payload = new_payload()
    attempt(payload, httpx.Client(transport=httpx.MockTransport(refuse)))

    failure = payload.events.get(to_status=Status.FAILED)
    assert (failure.response_code, failure.error) == (None, 'Connection refused')


@pytest.mark.django_db
def test_the_url_is_checked_again_at_send_time(
    monkeypatch: pytest.MonkeyPatch, endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    # The hostname now resolves internally (DNS changed after the endpoint was saved): nothing is sent.
    monkeypatch.setattr(socket, 'getaddrinfo', lambda *args, **kwargs: [(0, 0, 0, '', ('10.0.0.1', 443))])
    endpoint.url = 'https://hooks.example.com/hook'
    endpoint.save()
    seen: list[httpx.Request] = []
    payload = new_payload()

    attempt(payload, client(200, seen))

    assert seen == []
    assert payload.status == Status.FAILED


@pytest.mark.django_db
def test_admins_are_emailed_once_after_the_fourth_failed_retry(new_payload: Callable[[], WebhookPayload]) -> None:
    payload = new_payload()
    for _ in range(4):  # the first attempt and retries 1-3
        attempt(payload, client(503))
    assert mail.outbox == []

    attempt(payload, client(503))  # retry 4
    assert [m.to for m in mail.outbox] == [['admin@test.test']]

    attempt(payload, client(503))  # retry 5: no second email
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_one_email_per_endpoint_incident_and_success_resets_it(new_payload: Callable[[], WebhookPayload]) -> None:
    first, second = new_payload(), new_payload()
    for _ in range(5):
        attempt(first, client(503))
        attempt(second, client(503))
    assert len(mail.outbox) == 1  # two failing deliveries, one incident

    attempt(new_payload(), client(200))  # the destination recovers
    third = new_payload()
    for _ in range(5):
        attempt(third, client(503))
    assert len(mail.outbox) == 2  # a new incident


@pytest.mark.django_db
def test_gives_up_after_7_days_and_disables_the_endpoint(
    endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    payload = new_payload()
    payload.events.update(created_at=timezone.now() - timedelta(days=7))  # first queued a week ago

    attempt(payload, client(503))

    endpoint.refresh_from_db()
    assert payload.next_attempt_at is None
    assert endpoint.status == WebhookEndpoint.Status.DISABLED


@pytest.mark.django_db
def test_a_success_re_enables_a_disabled_endpoint(
    endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    endpoint.status = WebhookEndpoint.Status.DISABLED
    endpoint.save()

    attempt(new_payload(), client(200))

    endpoint.refresh_from_db()
    assert endpoint.status == WebhookEndpoint.Status.ACTIVE


@pytest.mark.django_db
def test_a_success_does_not_unpause_a_paused_endpoint(
    endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    endpoint.status = WebhookEndpoint.Status.PAUSED
    endpoint.save()

    attempt(new_payload(), client(200))

    endpoint.refresh_from_db()
    assert endpoint.status == WebhookEndpoint.Status.PAUSED


@pytest.mark.django_db
def test_a_failed_alert_email_is_tried_again_on_the_next_failure(
    monkeypatch: pytest.MonkeyPatch, endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    real_send_mail = delivery.send_mail

    def mail_server_down(*args: Any, **kwargs: Any) -> int:
        raise smtplib.SMTPException('Mail server unavailable')

    payload = new_payload()
    for _ in range(4):
        attempt(payload, client(503))
    monkeypatch.setattr(delivery, 'send_mail', mail_server_down)
    attempt(payload, client(503))  # retry 4: the email fails, but delivery bookkeeping carries on

    endpoint.refresh_from_db()
    assert endpoint.alerted_at is None  # not marked as alerted, so it isn't lost
    assert payload.status == Status.FAILED and payload.next_attempt_at is not None

    monkeypatch.setattr(delivery, 'send_mail', real_send_mail)
    attempt(payload, client(503))  # retry 5: the mail server is back
    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_failures_are_logged_by_id_without_the_url(
    caplog: pytest.LogCaptureFixture, endpoint: WebhookEndpoint, new_payload: Callable[[], WebhookPayload]
) -> None:
    # Webhook URLs can carry tokens, so logs identify endpoints by id instead.
    endpoint.url = 'https://8.8.8.8/hook?token=s3cret'
    endpoint.save()
    payload = new_payload()

    with caplog.at_level(logging.WARNING, logger='webhooks'):
        attempt(payload, client(503))

    assert f'payload {payload.id} to endpoint {endpoint.id} failed on attempt 1 (HTTP 503)' in caplog.text
    assert 's3cret' not in caplog.text
