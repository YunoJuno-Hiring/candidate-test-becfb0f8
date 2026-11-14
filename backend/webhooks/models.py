# Webhook models live here.
#
# Task C implements outbound webhooks: a configurable endpoint, a delivery
# log, and async delivery for one system event. The WebhookEndpoint and
# delivery-log models belong in this file.
import base64
import secrets
from typing import Self

from django.conf import settings
from django.db import models, transaction
from django.db.models import OuterRef, Subquery
from django.utils import timezone

from accounts.models import Company


def generate_secret() -> str:
    # Standard Webhooks format: whsec_ + base64 of random bytes (the prefix helps secret scanners).
    return 'whsec_' + base64.b64encode(secrets.token_bytes(32)).decode()


class WebhookEndpointQuerySet(models.QuerySet['WebhookEndpoint']):
    def for_company(self, company: Company) -> Self:
        return self.filter(company=company)

    def with_last_attempt_id(self) -> Self:
        # The newest attempt's id per endpoint, worked out inside the same SQL query (a correlated subquery).
        latest = WebhookPayloadEvent.objects.attempts().newest_first().filter(payload__endpoint=OuterRef('pk'))
        return self.annotate(last_attempt_id=Subquery(latest.values('id')[:1]))


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

    objects = WebhookEndpointQuerySet.as_manager()
    # Not fields: set only on rows from with_last_attempt_id(), and by the list view that fetches those attempts.
    last_attempt_id: int | None
    last_attempt: WebhookPayloadEvent | None

    def __str__(self) -> str:
        return self.url

    # The three below are guarded single-row updates, so racing workers can't both act on stale state.
    def claim_alert(self) -> bool:
        # True for the one worker that marks the incident; only it emails the admins.
        return bool(WebhookEndpoint.objects.filter(pk=self.pk, alerted_at=None).update(alerted_at=timezone.now()))

    def clear_alert(self) -> None:
        # The incident is over (a success), or its email failed and the next failure should try again.
        WebhookEndpoint.objects.filter(pk=self.pk).update(alerted_at=None)

    def disable(self) -> None:
        # Only an active endpoint is disabled; a paused one stays paused.
        WebhookEndpoint.objects.filter(pk=self.pk, status=self.Status.ACTIVE).update(status=self.Status.DISABLED)

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


class WebhookPayloadQuerySet(models.QuerySet['WebhookPayload']):
    def newest_first(self) -> Self:
        return self.order_by('-created_at', '-id')


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
    # Where the endpoint pointed when the event happened. Each attempt records where it actually went.
    url = models.URLField(max_length=2048)
    payload = models.JSONField()
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    # When a failed payload is due its next retry; None once delivered or given up.
    next_attempt_at = models.DateTimeField(null=True, blank=True)

    objects = WebhookPayloadQuerySet.as_manager()

    def __str__(self) -> str:
        return f'{self.id}'

    def transition(self, to_status: str, response_code: int | None = None, error: str = '', url: str = '') -> bool:
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
                url=url,
            )
        self.status = to_status
        return True


# The moves that end an attempt; the others (to queued) just start one.
ATTEMPT_RESULTS = [WebhookPayload.Status.DELIVERED, WebhookPayload.Status.FAILED]


class WebhookPayloadEventQuerySet(models.QuerySet['WebhookPayloadEvent']):
    def attempts(self) -> Self:
        return self.filter(to_status__in=ATTEMPT_RESULTS)

    def newest_first(self) -> Self:
        return self.order_by('-created_at', '-id')


class WebhookPayloadEvent(models.Model):
    """One row per status change: the delivery log (what happened, when, and the response)."""

    payload = models.ForeignKey(WebhookPayload, on_delete=models.CASCADE, related_name='events')
    from_status = models.CharField(max_length=10, choices=WebhookPayload.Status.choices)
    to_status = models.CharField(max_length=10, choices=WebhookPayload.Status.choices)
    response_code = models.PositiveSmallIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    # The URL an attempt was sent to: the audit trail survives the endpoint's URL being changed. Blank if no attempt.
    url = models.URLField(max_length=2048, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = WebhookPayloadEventQuerySet.as_manager()

    class Meta:
        ordering = ['created_at']

    def __str__(self) -> str:
        return f'{self.payload_id}: {self.from_status} > {self.to_status}'
