# Webhook models live here.
#
# Task C implements outbound webhooks: a configurable endpoint, a delivery
# log, and async delivery for one system event. The WebhookEndpoint and
# delivery-log models belong in this file.
import base64
import secrets

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from accounts.models import Company


def generate_secret() -> str:
    # Standard Webhooks format: whsec_ + base64 of random bytes (the prefix helps secret scanners).
    return 'whsec_' + base64.b64encode(secrets.token_bytes(32)).decode()


class WebhookEndpoint(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active'
        PAUSED = 'paused'  # by an admin; only an admin unpauses
        DISABLED = 'disabled'  # by the system after 7 days of failures; a successful delivery re-enables

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='webhook_endpoints')

    # URLField defaults to 200 chars; real URLs with query strings run longer.
    url = models.URLField(max_length=2048)
    # Generated for each new endpoint, wherever it's created; never set by hand.
    secret = models.CharField(max_length=64, default=generate_secret, editable=False)
    # The secret before the last rotation; deliveries carry a signature from it too until it expires.
    previous_secret = models.CharField(max_length=64, blank=True, editable=False)
    previous_secret_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    # Set when admins are emailed about a failing incident; a success clears it, so one email per incident.
    alerted_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return self.url

    def rotate_secret(self) -> None:
        # Only one previous secret is kept: rotating twice within the grace period drops the oldest.
        self.previous_secret = self.secret
        self.previous_secret_expires_at = timezone.now() + settings.WEBHOOK_SECRET_ROTATION_GRACE
        self.secret = generate_secret()
        self.save(update_fields=['secret', 'previous_secret', 'previous_secret_expires_at'])

    def signing_secrets(self) -> list[str]:
        # The current secret first, then the previous one while its grace period lasts.
        expires = self.previous_secret_expires_at
        if self.previous_secret and expires and expires > timezone.now():
            return [self.secret, self.previous_secret]
        return [self.secret]


class WebhookPayload(models.Model):
    class Status(models.TextChoices):
        CREATED = 'created'  # saved; stays here while the endpoint is paused or disabled
        QUEUED = 'queued'
        DELIVERED = 'delivered'
        FAILED = 'failed'  # requeued on the backoff schedule

    # The legal moves. Happy path: created > queued > delivered. Sad path: queued > failed > queued.
    TRANSITIONS: dict[str, set[str]] = {
        Status.CREATED: {Status.QUEUED},
        Status.QUEUED: {Status.DELIVERED, Status.FAILED},
        Status.FAILED: {Status.QUEUED},
    }

    # Deleting an endpoint deletes its delivery history too: a deliberate choice, to keep deletion simple.
    endpoint = models.ForeignKey(WebhookEndpoint, on_delete=models.CASCADE, related_name='payloads')
    url = models.URLField(max_length=2048)
    payload = models.JSONField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    # When a failed payload is due its next retry; None once delivered or given up.
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f'{self.id}'

    def transition(self, to_status: str, response_code: int | None = None, error: str = '') -> bool:
        """Move to to_status and record the event. False if another worker moved it first."""
        from_status = self.status
        if to_status not in self.TRANSITIONS.get(from_status, set()):
            raise ValueError(f'Illegal webhook payload transition: {from_status} > {to_status}')

        with transaction.atomic():
            # Only writes if the row is still in the status we read, so two racing workers can't both move it.
            moved = WebhookPayload.objects.filter(pk=self.pk, status=from_status).update(status=to_status)
            if not moved:
                return False
            WebhookPayloadEvent.objects.create(
                payload=self,
                from_status=from_status,
                to_status=to_status,
                response_code=response_code,
                error=error,
            )
        self.status = to_status
        return True


class WebhookPayloadEvent(models.Model):
    """One row per status change: the delivery log (what happened, when, and the response)."""

    payload = models.ForeignKey(WebhookPayload, on_delete=models.CASCADE, related_name='events')
    from_status = models.CharField(max_length=10, choices=WebhookPayload.Status.choices)
    to_status = models.CharField(max_length=10, choices=WebhookPayload.Status.choices)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.payload_id}: {self.from_status} > {self.to_status}'
