from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from .models import Family, FamilyMember, Category, Transaction, Budget

def create_default_groups():
    """Создает стандартные группы прав при первом запуске."""
    
    # 1. Глава семьи (ЕСТЬ право на бюджет)
    head_group, _ = Group.objects.get_or_create(name='Глава семьи')
    head_group.permissions.clear()
    head_group.permissions.add(
        *Permission.objects.filter(
            content_type__app_label='core',
            codename__in=[
                'add_family', 'change_family', 'delete_family', 'view_family',
                'add_category', 'change_category', 'delete_category', 'view_category',
                'add_transaction', 'change_transaction', 'delete_transaction', 'view_transaction',
                'add_budget', 'change_budget', 'delete_budget', 'view_budget',
                'can_manage_family', 'can_delete_any_transaction', 'can_set_budget', 'can_import_export'
            ]
        )
    )
    
    # 2. Член семьи (ЕСТЬ право на бюджет)
    member_group, _ = Group.objects.get_or_create(name='Член семьи')
    member_group.permissions.clear()
    member_group.permissions.add(
        *Permission.objects.filter(
            content_type__app_label='core',
            codename__in=[
                'add_transaction', 'view_transaction', 'view_category',
                'add_budget', 'view_budget', 'can_import_export'
            ]
        )
    )
    
    # 3. Наблюдатель (НЕТ права на бюджет!)
    viewer_group, _ = Group.objects.get_or_create(name='Наблюдатель')
    viewer_group.permissions.clear()
    viewer_group.permissions.add(
        *Permission.objects.filter(
            content_type__app_label='core',
            codename__in=[
                'view_transaction', 'view_category', 'view_budget', 'can_view_family_reports'
            ]
        )
    )

try:
    create_default_groups()
except Exception:
    pass

@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ['name', 'created_at']
    search_fields = ['name']

@admin.register(FamilyMember)
class FamilyMemberAdmin(admin.ModelAdmin):
    list_display = ['user', 'family', 'is_head', 'joined_at']
    list_filter = ['family', 'is_head']
    raw_id_fields = ['user']

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'type', 'family', 'created_at']
    list_filter = ['type', 'family']

@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'user', 'category', 'amount', 'description']
    list_filter = ['date', 'category__type', 'user']
    search_fields = ['description', 'user__username']

@admin.register(Budget)
class BudgetAdmin(admin.ModelAdmin):
    list_display = ['family', 'category', 'amount', 'month']
    list_filter = ['family', 'month']