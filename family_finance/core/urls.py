from django.urls import path
from . import views

urlpatterns = [
    path('', views.transaction_list, name='transaction_list'),
    path('dashboard/', views.family_dashboard, name='family_dashboard'),
    
    # === РЕГИСТРАЦИЯ И ПРИГЛАШЕНИЕ ===
    path('register/', views.register_view, name='register'),
    path('family/invite/', views.family_invite_member, name='family_invite'),
    
    # === УПРАВЛЕНИЕ СЕМЬЕЙ ===
    path('family/create/', views.family_create, name='family_create'),
    path('family/join/', views.family_join, name='family_join'),
    path('family/members/', views.family_members, name='family_members'),
    path('family/members/<int:member_id>/role/', views.family_member_role_update, name='family_member_role'),
    path('family/leave/', views.family_leave, name='family_leave'),
    
    # === ТРАНЗАКЦИИ ===
    path('transaction/add/', views.transaction_create, name='transaction_create'),
    path('category/add/', views.category_create, name='category_create'),
    path('transaction/<int:pk>/delete/', views.transaction_delete, name='transaction_delete'),
    
    # === БЮДЖЕТЫ И ОТЧЁТЫ ===
    path('budgets/', views.budget_list, name='budget_list'),
    path('reports/', views.reports_view, name='reports'),
    
    # === ЭКСПОРТ/ИМПОРТ ===
    path('export/csv/', views.export_csv, name='export_csv'),
    path('import/csv/', views.import_csv, name='import_csv'),
]