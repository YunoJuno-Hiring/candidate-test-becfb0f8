from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import WebhookEndpoint
from .validators import validate_webhook_url


class WebhookEndpointSerializer(serializers.ModelSerializer[WebhookEndpoint]):
    # The secret and company are never accepted from clients: the model generates one, the view sets the other.
    class Meta:
        model = WebhookEndpoint
        fields = ['id', 'url', 'status']

    def validate_url(self, url: str) -> str:
        try:
            validate_webhook_url(url)
        except DjangoValidationError as error:  # re-raised as DRF's, so the client gets a 400 on 'url'
            raise serializers.ValidationError(error.messages) from error
        return url

    def validate_status(self, status: str) -> str:
        if status == WebhookEndpoint.Status.DISABLED:
            raise serializers.ValidationError('Only the system disables an endpoint; pause it instead.')
        return status
