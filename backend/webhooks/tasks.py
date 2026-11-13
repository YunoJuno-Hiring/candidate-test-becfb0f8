from django_tasks import task

from . import delivery
from .models import WebhookPayload


@task()
def deliver_payload(payload_id: int) -> None:
    """Run by the db_worker. A failed payload is due a retry: requeue it, then attempt it."""
    payload = WebhookPayload.objects.select_related('endpoint').filter(pk=payload_id).first()
    if payload is None:
        return  # the endpoint was deleted, taking its payloads with it
    if payload.status == WebhookPayload.Status.FAILED:
        payload.transition(WebhookPayload.Status.QUEUED)
    # If another worker moved it first (or it was delivered), there's nothing to do.
    if payload.status == WebhookPayload.Status.QUEUED:
        delivery.deliver(payload)
