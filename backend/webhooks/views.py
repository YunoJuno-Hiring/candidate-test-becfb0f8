import logging
from typing import Any
from urllib.parse import urlsplit

from django.db import transaction
from django.db.models import QuerySet
from django.shortcuts import get_object_or_404
from django.utils.cache import patch_cache_control
from rest_framework import generics, status
from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.serializers import BaseSerializer
from rest_framework.views import APIView

from accounts.models import Company

from .models import WebhookEndpoint
from .serializers import WebhookEndpointSerializer
from .services import resume, send_test_event

# Audit trail: who changed what, by id. Hosts rather than full URLs, which can carry tokens.
logger = logging.getLogger(__name__)


class IsCompanyAdmin(BasePermission):
    message = 'Only company admins can configure webhooks.'

    def has_permission(self, request: Request, view: APIView) -> bool:
        return hasattr(request.user, 'company_admin')


def admin_company(request: Request) -> Company:
    return request.user.company_admin.company  # type: ignore[union-attr]  # IsCompanyAdmin guarantees it


def company_endpoints(request: Request) -> QuerySet[WebhookEndpoint]:
    # Every lookup goes through here, so another company's endpoint is simply a 404.
    return WebhookEndpoint.objects.filter(company=admin_company(request)).order_by('id')


def host(url: str) -> str:
    return urlsplit(url).hostname or ''


def no_store(response: Response) -> Response:
    # Anything carrying the secret must not be kept by browsers or proxies.
    patch_cache_control(response, no_store=True)
    return response


class WebhookEndpointListCreateView(generics.ListCreateAPIView[WebhookEndpoint]):
    permission_classes = [IsCompanyAdmin]
    serializer_class = WebhookEndpointSerializer

    def get_queryset(self) -> QuerySet[WebhookEndpoint]:
        return company_endpoints(self.request)

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        endpoint = serializer.save(company=admin_company(request))
        logger.info(
            'User %s created webhook endpoint %s for company %s (host %s)',
            request.user.id,
            endpoint.id,
            endpoint.company_id,
            host(endpoint.url),
        )
        # The secret is in the create response only; listings never include it.
        return no_store(Response({**serializer.data, 'secret': endpoint.secret}, status=status.HTTP_201_CREATED))


class WebhookEndpointDetailView(generics.RetrieveUpdateDestroyAPIView[WebhookEndpoint]):
    permission_classes = [IsCompanyAdmin]
    serializer_class = WebhookEndpointSerializer

    def get_queryset(self) -> QuerySet[WebhookEndpoint]:
        return company_endpoints(self.request)

    def perform_update(self, serializer: BaseSerializer[WebhookEndpoint]) -> None:
        before = serializer.instance
        old_host, old_status = (host(before.url), before.status) if before else ('', '')
        with transaction.atomic():
            endpoint = serializer.save()
            if old_status != WebhookEndpoint.Status.ACTIVE and endpoint.status == WebhookEndpoint.Status.ACTIVE:
                resume(endpoint)  # sends only the most recent saved payload
        logger.info(
            'User %s updated webhook endpoint %s: host %s > %s, status %s > %s',
            self.request.user.id,
            endpoint.id,
            old_host,
            host(endpoint.url),
            old_status,
            endpoint.status,
        )

    def perform_destroy(self, instance: WebhookEndpoint) -> None:
        payloads = instance.payloads.count()
        endpoint_id = instance.id
        instance.delete()
        logger.info(
            'User %s deleted webhook endpoint %s and its %s payload(s)', self.request.user.id, endpoint_id, payloads
        )


class RevealSecretView(APIView):
    permission_classes = [IsCompanyAdmin]

    def post(self, request: Request, pk: int) -> Response:
        # TODO: don't show the secret after creation; add rotation instead.
        endpoint = get_object_or_404(company_endpoints(request), pk=pk)
        logger.warning('User %s revealed the secret for webhook endpoint %s', request.user.id, endpoint.id)
        return no_store(Response({'secret': endpoint.secret}))


class SendTestEventView(APIView):
    permission_classes = [IsCompanyAdmin]

    def post(self, request: Request, pk: int) -> Response:
        payload = send_test_event(get_object_or_404(company_endpoints(request), pk=pk))
        logger.info('User %s sent test payload %s to webhook endpoint %s', request.user.id, payload.id, pk)
        return Response({'id': payload.id}, status=status.HTTP_202_ACCEPTED)
