import logging
from typing import Any
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import ATTEMPT_RESULTS, WebhookEndpoint, WebhookPayload, WebhookPayloadEvent
from .validators import validate_webhook_url

logger = logging.getLogger(__name__)


def attempt_result(event: WebhookPayloadEvent) -> dict[str, Any]:
    return {
        'status': event.to_status,
        'response_code': event.response_code,
        'error': event.error,
        'url': event.url,
        'at': event.created_at,
    }


class WebhookEndpointSerializer(serializers.ModelSerializer[WebhookEndpoint]):
    # The secret and company are never accepted from clients: the model generates one, the view sets the other.
    last_delivery = serializers.SerializerMethodField()

    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'url', 'status', 'last_delivery']

    def get_last_delivery(self, endpoint: WebhookEndpoint) -> dict[str, Any] | None:
        # The most recent attempt to any of its payloads. The list view attaches it for every row in one query;
        # single-endpoint responses look it up here.
        if hasattr(endpoint, 'last_attempt'):
            latest = endpoint.last_attempt
        else:
            latest = WebhookPayloadEvent.objects.attempts().newest_first().filter(payload__endpoint=endpoint).first()
        return attempt_result(latest) if latest else None

    def validate_url(self, url: str) -> str:
        try:
            validate_webhook_url(url)
        except DjangoValidationError as error:  # re-raised as DRF's, so the client gets a 400 on 'url'
            # A typo, or someone probing our network (SSRF): either way, worth seeing.
            request = self.context.get('request')
            logger.warning(
                'Webhook URL rejected for user %s: host %s (%s)',
                getattr(getattr(request, 'user', None), 'id', None),
                urlsplit(url).hostname,
                '; '.join(error.messages),
            )
            raise serializers.ValidationError(error.messages) from error
        return url

    def validate_status(self, status: str) -> str:
        if status == WebhookEndpoint.Status.DISABLED:
            raise serializers.ValidationError('Only the system disables an endpoint; pause it instead.')
        return status


class WebhookDeliverySerializer(serializers.ModelSerializer[WebhookPayload]):
    """A payload with its attempts: the delivery log's "what fired, when, response code, attempt number"."""

    event_id = serializers.SerializerMethodField()
    event_type = serializers.SerializerMethodField()
    attempts = serializers.SerializerMethodField()

    class Meta:
        model = WebhookPayload
        fields = ['id', 'event_id', 'event_type', 'status', 'created_at', 'next_attempt_at', 'attempts']

    def get_event_id(self, payload: WebhookPayload) -> str:
        return str(payload.payload.get('id', ''))

    def get_event_type(self, payload: WebhookPayload) -> str:
        return str(payload.payload.get('type', ''))

    def get_attempts(self, payload: WebhookPayload) -> list[dict[str, Any]]:
        # Uses the prefetched events (oldest first); each delivered or failed move is one attempt.
        results = [event for event in payload.events.all() if event.to_status in ATTEMPT_RESULTS]
        return [{'attempt': number, **attempt_result(event)} for number, event in enumerate(results, start=1)]
