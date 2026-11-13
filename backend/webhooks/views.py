from typing import Any

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


class IsCompanyAdmin(BasePermission):
    message = 'Only company admins can configure webhooks.'

    def has_permission(self, request: Request, view: APIView) -> bool:
        return hasattr(request.user, 'company_admin')


def admin_company(request: Request) -> Company:
    return request.user.company_admin.company  # type: ignore[union-attr]  # IsCompanyAdmin guarantees it


def company_endpoints(request: Request) -> QuerySet[WebhookEndpoint]:
    # Every lookup goes through here, so another company's endpoint is simply a 404.
    return WebhookEndpoint.objects.filter(company=admin_company(request)).order_by('id')


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
        # The secret is in the create response only; listings never include it.
        return no_store(Response({**serializer.data, 'secret': endpoint.secret}, status=status.HTTP_201_CREATED))


class WebhookEndpointDetailView(generics.RetrieveUpdateDestroyAPIView[WebhookEndpoint]):
    permission_classes = [IsCompanyAdmin]
    serializer_class = WebhookEndpointSerializer

    def get_queryset(self) -> QuerySet[WebhookEndpoint]:
        return company_endpoints(self.request)

    def perform_update(self, serializer: BaseSerializer[WebhookEndpoint]) -> None:
        resuming = serializer.instance is not None and serializer.instance.status != WebhookEndpoint.Status.ACTIVE
        with transaction.atomic():
            endpoint = serializer.save()
            if resuming and endpoint.status == WebhookEndpoint.Status.ACTIVE:
                resume(endpoint)  # sends only the most recent saved payload


class RevealSecretView(APIView):
    permission_classes = [IsCompanyAdmin]

    def post(self, request: Request, pk: int) -> Response:
        # TODO: don't show the secret after creation; add rotation instead.
        endpoint = get_object_or_404(company_endpoints(request), pk=pk)
        return no_store(Response({'secret': endpoint.secret}))


class SendTestEventView(APIView):
    permission_classes = [IsCompanyAdmin]

    def post(self, request: Request, pk: int) -> Response:
        payload = send_test_event(get_object_or_404(company_endpoints(request), pk=pk))
        return Response({'id': payload.id}, status=status.HTTP_202_ACCEPTED)
