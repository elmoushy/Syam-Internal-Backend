"""
URL configuration for Audit app.
"""

from django.urls import path
from . import views

app_name = 'audit'

urlpatterns = [
    path('logs/', views.AuditLogListView.as_view(), name='logs-list'),
    path('stats/', views.AuditLogStatsView.as_view(), name='stats'),
    path('actors/', views.ActorsListView.as_view(), name='actors-list'),
    path('actions/', views.ActionsListView.as_view(), name='actions-list'),
]
