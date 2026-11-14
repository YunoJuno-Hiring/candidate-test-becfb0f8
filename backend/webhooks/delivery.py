import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime

import httpx
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from accounts.models import CompanyAdmin

from . import services, tasks
from .models import WebhookEndpoint, WebhookPayload
from .schedule import next_attempt_at
from .validators import validate_webhook_url

logger = logging.getLogger(__name__)

Status = WebhookPayload.Status


def sign(secret: str, msg_id: str, timestamp: int, body: bytes) -> str:
    """Standard Webhooks: base64 HMAC-SHA256 of '{id}.{timestamp}.{body}', keyed by the decoded secret."""
    key = base64.b64decode(secret.removeprefix('whsec_'))
    digest = hmac.new(key, f'{msg_id}.{timestamp}.'.encode() + body, hashlib.sha256).digest()
    return 'v1,' + base64.b64encode(digest).decode()


def read_capped(response: httpx.Response, limit: int) -> str:
    # Stop at limit bytes, so a destination can't make us hold a huge error body. iter_raw, not iter_bytes:
    # decompressing a gzip "bomb" could still turn a few KB into gigabytes.
    if response.is_stream_consumed:  # already fully in memory, so there's nothing left to protect against
        return response.content[:limit].decode(errors='replace')
    data = b''
    for chunk in response.iter_raw():
        data += chunk
        if len(data) >= limit:
            break
    return data[:limit].decode(errors='replace')  # a character cut in half becomes a replacement character


def deliver(payload: WebhookPayload, client: httpx.Client | None = None) -> None:
    """Make one attempt to send a queued payload, then record the outcome and what happens next."""
    endpoint = payload.endpoint
    body = json.dumps(payload.payload).encode()
    msg_id = str(payload.payload.get('id', payload.id))
    timestamp = int(time.time())
    headers = {
        'content-type': 'application/json',
        'accept-encoding': 'identity',  # ask for an uncompressed reply: we only ever read a capped slice of it
        'webhook-id': msg_id,
        'webhook-timestamp': str(timestamp),
        # Standard Webhooks allows several space-separated signatures; receivers accept any that verifies.
        'webhook-signature': ' '.join(sign(secret, msg_id, timestamp, body) for secret in endpoint.signing_secrets()),
    }
    url = endpoint.url  # read once: what's validated, sent to and recorded must be the same URL
    try:
        validate_webhook_url(url)  # again at send time: DNS may have changed since it was saved
        with (
            client or httpx.Client(timeout=settings.WEBHOOK_TIMEOUT_SECONDS) as http,
            # Streamed, not buffered: the status arrives first, and a success's body is never read at all.
            http.stream('POST', url, content=body, headers=headers) as response,  # no redirects followed
        ):
            code = response.status_code
            reply = '' if response.is_success else read_capped(response, settings.WEBHOOK_MAX_ERROR_LENGTH)
    except ValidationError as error:
        return fail(payload, None, '; '.join(error.messages), url)
    except httpx.HTTPError as error:
        return fail(payload, None, str(error), url)
    except Exception as error:
        # Anything unexpected still fails into a retry, so a payload can never be stuck in queued. The admin sees only
        # the exception type; the traceback goes to the log.
        logger.exception('Unexpected error delivering webhook payload %s to endpoint %s', payload.id, endpoint.id)
        return fail(payload, None, f'Unexpected error ({type(error).__name__})', url)

    if 200 <= code < 300:
        succeed(payload, code, url)
    else:
        fail(payload, code, reply, url)


def succeed(payload: WebhookPayload, response_code: int, url: str = '') -> None:
    payload.transition(Status.DELIVERED, response_code=response_code, url=url)
    logger.info('Webhook payload %s delivered to endpoint %s: HTTP %s', payload.id, payload.endpoint_id, response_code)
    endpoint = payload.endpoint
    # A success ends the incident, and re-enables a disabled endpoint; it never unpauses a paused one.
    endpoint.clear_alert()
    if endpoint.status == WebhookEndpoint.Status.DISABLED:
        services.resume(endpoint)


def fail(payload: WebhookPayload, response_code: int | None, error: str, url: str = '') -> None:
    endpoint = payload.endpoint
    with transaction.atomic():  # the failure, its retry time and the queued retry are recorded together
        payload.transition(
            Status.FAILED, response_code=response_code, error=error[: settings.WEBHOOK_MAX_ERROR_LENGTH], url=url
        )
        failures = payload.events.filter(to_status=Status.FAILED).count()  # the first attempt, then retries
        first_attempt_at = payload.events.filter(to_status=Status.QUEUED).earliest('created_at').created_at
        payload.next_attempt_at = next_attempt_at(first_attempt_at, timezone.now(), retry=failures)
        payload.save(update_fields=['next_attempt_at'])

        # Endpoint id, not URL: URLs can carry tokens in their path or query string.
        outcome = f'HTTP {response_code}' if response_code else error[: settings.WEBHOOK_ERROR_SUMMARY_LENGTH]
        if payload.next_attempt_at is None:
            # Given up after 7 days: stop sending until a success re-enables it. A paused endpoint stays paused.
            endpoint.disable()
            logger.error(
                'Webhook payload %s gave up after %s attempts (%s); endpoint %s disabled',
                payload.id,
                failures,
                outcome,
                endpoint.id,
            )
            return
        tasks.deliver_payload.using(run_after=payload.next_attempt_at).enqueue(payload.id)
        logger.warning(
            'Webhook payload %s to endpoint %s failed on attempt %s (%s); retrying at %s',
            payload.id,
            endpoint.id,
            failures,
            outcome,
            payload.next_attempt_at,
        )

    if failures - 1 >= settings.WEBHOOK_EMAIL_AFTER_RETRY:
        alert_admins(endpoint, first_attempt_at + settings.WEBHOOK_GIVE_UP_AFTER, error or f'HTTP {response_code}')


def abandon(payload: WebhookPayload, reason: str) -> None:
    # Failed for good without being sent: no retry is scheduled and admins aren't alerted.
    with transaction.atomic():
        payload.transition(Status.FAILED, error=reason)
        payload.next_attempt_at = None
        payload.save(update_fields=['next_attempt_at'])
    logger.warning(
        'Webhook payload %s to endpoint %s not sent and will not be retried: %s (endpoint is %s)',
        payload.id,
        payload.endpoint_id,
        reason.lower(),
        payload.endpoint.status,
    )


def alert_admins(endpoint: WebhookEndpoint, disable_at: datetime, last_error: str) -> None:
    if not endpoint.claim_alert():  # another worker already emailed about this incident
        return
    admins = CompanyAdmin.objects.filter(company=endpoint.company).select_related('user')
    try:
        send_mail(
            subject=f'Webhook endpoint failing: {endpoint.url}',
            message=(
                f'Deliveries to {endpoint.url} have been failing for over an hour.\n'
                f'Last error: {last_error[: settings.WEBHOOK_ERROR_SUMMARY_LENGTH]}\n\n'
                f'We will keep retrying. If it is still failing on {disable_at:%d %B %Y at %H:%M} UTC, '
                'the endpoint will be disabled until a test event succeeds.'
            ),
            from_email=None,
            recipient_list=[admin.user.email for admin in admins],
        )
    except Exception:
        # Un-mark the incident, so the next failed retry tries the email again instead of never alerting.
        endpoint.clear_alert()
        logger.exception('Could not email admins that webhook endpoint %s is failing; will retry', endpoint.id)
        return
    logger.info('Emailed %s admin(s) that endpoint %s is failing', len(admins), endpoint.id)
    # TODO: email again when we give up and disable the endpoint.
