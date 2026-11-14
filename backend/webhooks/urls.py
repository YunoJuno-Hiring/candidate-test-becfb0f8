from django.urls import path

from . import views

urlpatterns = [
    path('webhook-endpoints/', views.WebhookEndpointListCreateView.as_view(), name='webhook-endpoint-list'),
    path('webhook-endpoints/<int:pk>/', views.WebhookEndpointDetailView.as_view(), name='webhook-endpoint-detail'),
    path('webhook-endpoints/<int:pk>/rotate-secret/', views.RotateSecretView.as_view(), name='webhook-rotate-secret'),
    path('webhook-endpoints/<int:pk>/test/', views.SendTestEventView.as_view(), name='webhook-test-event'),
    path('webhook-endpoints/<int:pk>/deliveries/', views.DeliveriesView.as_view(), name='webhook-deliveries'),
]
