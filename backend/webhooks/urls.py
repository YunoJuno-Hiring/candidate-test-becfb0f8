from django.urls import path

from . import views

urlpatterns = [
    # Stub endpoints — real behaviour is part of Task C
    path('webhook-endpoints/', views.WebhookEndpointListCreateView.as_view(), name='webhook-endpoint-list'),
    path('webhook-endpoints/<str:pk>/', views.WebhookEndpointDestroyView.as_view(), name='webhook-endpoint-detail'),
]
