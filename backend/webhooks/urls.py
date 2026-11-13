from django.urls import path

from . import views

urlpatterns = [
    path('webhook-endpoints/', views.WebhookEndpointListCreateView.as_view(), name='webhook-endpoint-list'),
    path('webhook-endpoints/<int:pk>/', views.WebhookEndpointDetailView.as_view(), name='webhook-endpoint-detail'),
    path('webhook-endpoints/<int:pk>/reveal-secret/', views.RevealSecretView.as_view(), name='webhook-reveal-secret'),
    path('webhook-endpoints/<int:pk>/test/', views.SendTestEventView.as_view(), name='webhook-test-event'),
]
