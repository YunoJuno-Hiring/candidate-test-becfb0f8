import logging
import uuid
from typing import Any

from django.conf import settings
from django.utils import timezone

from accounts.models import Company

from . import tasks
from .models import EventType, WebhookEndpoint, WebhookPayload

logger = logging.getLogger(__name__)


def queue(payload: WebhookPayload) -> None:
    # The task row is written in the caller's transaction: if that rolls back, nothing is sent.
    payload.transition(WebhookPayload.Status.QUEUED)
    tasks.deliver_payload.enqueue(payload.id)


def envelope(event_type: str, data: dict[str, Any]) -> dict[str, Any]:
    """The versioned wrapper every event shares. id is stable across retries: the consumer's dedupe key."""
    return {
        'id': f'evt_{uuid.uuid4().hex}',
        'type': event_type,
        'version': settings.WEBHOOK_PAYLOAD_VERSION,
        'created_at': timezone.now().isoformat(),
        'data': data,
    }


def emit(company: Company, event_type: str, data: dict[str, Any]) -> None:
    """Save one payload per endpoint of the company. Call inside the transaction making the change."""
    body = envelope(event_type, data)
    queued = saved = 0
    for endpoint in WebhookEndpoint.objects.for_company(company):
        payload = WebhookPayload.objects.create(endpoint=endpoint, url=endpoint.url, payload=body)
        if endpoint.status == WebhookEndpoint.Status.ACTIVE:
            queue(payload)
            queued += 1
        else:
            saved += 1  # paused or disabled: saved, not sent
    logger.info('Event %s (%s) for company %s: %s queued, %s saved', body['id'], event_type, company.id, queued, saved)


def send_test_event(endpoint: WebhookEndpoint) -> WebhookPayload:
    # Queued even when disabled: a test is how an admin proves it works again. The view refuses paused ones.
    payload = WebhookPayload.objects.create(
        endpoint=endpoint, url=endpoint.url, payload=envelope(EventType.TEST, {'endpoint_id': endpoint.id})
    )
    queue(payload)
    return payload


def resume(endpoint: WebhookEndpoint) -> None:
    """Make an endpoint active again and send only its most recent saved payload; older ones stay as a record."""
    endpoint.status = WebhookEndpoint.Status.ACTIVE
    endpoint.save(update_fields=['status'])
    latest = endpoint.payloads.filter(status=WebhookPayload.Status.CREATED).newest_first().first()
    if latest:
        queue(latest)
    logger.info(
        'Webhook endpoint %s resumed; queued latest saved payload: %s', endpoint.id, latest.id if latest else None
    )
