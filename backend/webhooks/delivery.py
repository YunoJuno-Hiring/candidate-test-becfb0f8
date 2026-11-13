import base64
import hashlib
import hmac
import json
import time
from datetime import datetime

import httpx
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import CompanyAdmin

from . import services, tasks
from .models import WebhookEndpoint, WebhookPayload
from .schedule import EMAIL_AFTER_RETRY, GIVE_UP_AFTER, next_attempt_at
from .validators import validate_webhook_url

TIMEOUT_SECONDS = 10
MAX_ERROR_LENGTH = 500  # the destination controls error text, so don't store unbounded amounts of it

Status = WebhookPayload.Status


def sign(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    """Standard Webhooks: base64 HMAC-SHA256 of '{id}.{timestamp}.{body}', keyed by the decoded secret."""
    key = base64.b64decode(secret.removeprefix('whsec_'))
    digest = hmac.new(key, f'{msg_id}.{timestamp}.'.encode() + body, hashlib.sha256).digest()
    return 'v1,' + base64.b64encode(digest).decode()


def deliver(payload: WebhookPayload, client: httpx.Client | None = None) -> None:
    """Make one attempt to send a queued payload, then record the outcome and what happens next."""
    endpoint = payload.endpoint
    body = json.dumps(payload.payload).encode()
    msg_id = str(payload.payload.get('id', payload.id))
    timestamp = int(time.time())
    headers = {
        'content-type': 'application/json',
        'webhook-id': msg_id,
        'webhook-timestamp': str(timestamp),
        'webhook-signature': sign(endpoint.secret, msg_id, timestamp, body),
    }
    try:
        validate_webhook_url(endpoint.url)  # again at send time: DNS may have changed since it was saved
        with client or httpx.Client(timeout=TIMEOUT_SECONDS) as http:
            response = http.post(endpoint.url, content=body, headers=headers)  # httpx doesn't follow redirects
    except ValidationError as error:
        return fail(payload, None, '; '.join(error.messages))
    except httpx.HTTPError as error:
        return fail(payload, None, str(error))

    if response.is_success:
        succeed(payload, response.status_code)
    else:
        fail(payload, response.status_code, response.text)


def succeed(payload: WebhookPayload, response_code: int) -> None:
    payload.transition(Status.DELIVERED, response_code=response_code)
    endpoint = payload.endpoint
    # A success ends the incident, and re-enables a disabled endpoint; it never unpauses a paused one.
    WebhookEndpoint.objects.filter(pk=endpoint.pk).update(alerted_at=None)
    if endpoint.status == WebhookEndpoint.Status.DISABLED:
        services.resume(endpoint)


def fail(payload: WebhookPayload, response_code: int | None, error: str) -> None:
    endpoint = payload.endpoint
    with transaction.atomic():  # the failure, its retry time and the queued retry are recorded together
        payload.transition(Status.FAILED, response_code=response_code, error=error[:MAX_ERROR_LENGTH])
        failures = payload.events.filter(to_status=Status.FAILED).count()  # the first attempt, then retries
        first_attempt_at = payload.events.filter(to_status=Status.QUEUED).earliest('created_at').created_at
        payload.next_attempt_at = next_attempt_at(first_attempt_at, timezone.now(), retry=failures)
        payload.save(update_fields=['next_attempt_at'])

        if payload.next_attempt_at is None:
            # Given up after 7 days: stop sending until a success re-enables it. A paused endpoint stays paused.
            WebhookEndpoint.objects.filter(pk=endpoint.pk, status=WebhookEndpoint.Status.ACTIVE).update(
                status=WebhookEndpoint.Status.DISABLED
            )
            return
        tasks.deliver_payload.using(run_after=payload.next_attempt_at).enqueue(payload.id)

    if failures - 1 >= EMAIL_AFTER_RETRY:
        alert_admins(endpoint, first_attempt_at + GIVE_UP_AFTER, error or f'HTTP {response_code}')


def alert_admins(endpoint: WebhookEndpoint, disable_at: datetime, last_error: str) -> None:
    # The guarded update means only one worker sends, once per incident.
    if not WebhookEndpoint.objects.filter(pk=endpoint.pk, alerted_at=None).update(alerted_at=timezone.now()):
        return
    admins = CompanyAdmin.objects.filter(company=endpoint.company).select_related('user')
    send_mail(
        subject=f'Webhook endpoint failing: {endpoint.url}',
        message=(
            f'Deliveries to {endpoint.url} have been failing for over an hour.\n'
            f'Last error: {last_error[:200]}\n\n'
            f'We will keep retrying. If it is still failing on {disable_at:%d %B %Y at %H:%M} UTC, '
            'the endpoint will be disabled until a test event succeeds.'
        ),
        from_email=None,
        recipient_list=[admin.user.email for admin in admins],
    )
    # TODO: email again when we give up and disable the endpoint.
