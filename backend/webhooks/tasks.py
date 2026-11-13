import logging

from django_tasks import task

from . import delivery
from .models import WebhookPayload

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
    delivery.deliver(payload)
