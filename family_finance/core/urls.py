from django.urls import path

from .openapi import openapi_schema, swagger_ui
from . import views

urlpatterns = [
    path('openapi.json', openapi_schema, name='openapi_schema'),
    path('swagger/', swagger_ui, name='swagger_ui'),
    path('register/', views.register_view, name='register'),
    path('', views.family_dashboard, name='family_dashboard'),
    path('family/create/', views.family_create, name='family_create'),
    path('family/members/', views.family_members, name='family_members'),
    path('family/invite/', views.family_invite_member, name='family_invite'),
    path(
        'family/member/<int:member_id>/role/',
        views.family_member_role_update,
        name='family_member_role',
    ),
    path('family/leave/', views.family_leave, name='family_leave'),
    path('transactions/', views.transaction_list, name='transaction_list'),
    path('transactions/create/', views.transaction_create, name='transaction_create'),
    path(
        'transactions/<int:pk>/delete/',
        views.transaction_delete,
        name='transaction_delete',
    ),
    path('categories/create/', views.category_create, name='category_create'),
    path('budgets/', views.budget_list, name='budget_list'),
    path('reports/', views.reports_view, name='reports'),
    path('export/csv/', views.export_csv, name='export_csv'),
    path('import/csv/', views.import_csv, name='import_csv'),
    path('budgets/<int:pk>/delete/', views.budget_delete, name='budget_delete'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),
]
