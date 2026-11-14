import logging

from django_tasks import task

from . import delivery
from .models import EventType, WebhookEndpoint, WebhookPayload

logger = logging.getLogger(__name__)


@task()
def deliver_payload(payload_id: int) -> None:
    """Run by the db_worker. A failed payload is due a retry: requeue it, then attempt it."""
    payload = WebhookPayload.objects.select_related('endpoint').filter(pk=payload_id).first()
    if payload is None:
        logger.debug('Webhook payload %s no longer exists (endpoint deleted); nothing to send', payload_id)
        return
    if payload.status == WebhookPayload.Status.FAILED:
        payload.transition(WebhookPayload.Status.QUEUED)
    if payload.status != WebhookPayload.Status.QUEUED:
        logger.debug('Webhook payload %s is %s, not queued; another worker had it', payload_id, payload.status)
        return
    # Paused means nothing is sent. Disabled still takes test events: a successful one is how it's re-enabled.
    status = payload.endpoint.status
    is_test = payload.payload.get('type') == EventType.TEST
    if status == WebhookEndpoint.Status.PAUSED or (status == WebhookEndpoint.Status.DISABLED and not is_test):
        delivery.abandon(payload, 'Endpoint is not active')
        return
    delivery.deliver(payload)
