# Generated manually for creating default permission groups
from django.db import migrations

def create_default_groups(apps, schema_editor):
    """
    Создаёт стандартные группы прав при применении миграции.
    Использует apps.get_model() для совместимости с миграциями.
    """
    Group = apps.get_model('auth', 'Group')
    Permission = apps.get_model('auth', 'Permission')
    
    # 1. Глава семьи (полные права)
    head_group, _ = Group.objects.get_or_create(name='Глава семьи')
    head_permissions = Permission.objects.filter(
        content_type__app_label='core',
        codename__in=[
            'add_family', 'change_family', 'delete_family', 'view_family',
            'add_category', 'change_category', 'delete_category', 'view_category',
            'add_transaction', 'change_transaction', 'delete_transaction', 'view_transaction',
            'add_budget', 'change_budget', 'delete_budget', 'view_budget',
            'can_manage_family', 'can_delete_any_transaction', 'can_set_budget', 'can_import_export'
        ]
    )
    head_group.permissions.set(head_permissions)
    
    # 2. Член семьи (может добавлять транзакции и бюджеты)
    member_group, _ = Group.objects.get_or_create(name='Член семьи')
    member_permissions = Permission.objects.filter(
        content_type__app_label='core',
        codename__in=[
            'add_transaction', 'view_transaction', 'view_category',
            'add_budget', 'view_budget', 'can_import_export'
        ]
    )
    member_group.permissions.set(member_permissions)
    
    # 3. Наблюдатель (только просмотр)
    viewer_group, _ = Group.objects.get_or_create(name='Наблюдатель')
    viewer_permissions = Permission.objects.filter(
        content_type__app_label='core',
        codename__in=[
            'view_transaction', 'view_category', 'view_budget', 'can_view_family_reports'
        ]
    )
    viewer_group.permissions.set(viewer_permissions)

def remove_default_groups(apps, schema_editor):
    """
    Удаляет группы при откате миграции (для безопасности).
    """
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name__in=['Глава семьи', 'Член семьи', 'Наблюдатель']).delete()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_budget_options_alter_family_options_and_more'),
        ('auth', '0012_alter_user_first_name_max_length'),  # Зависимость от auth
    ]

    operations = [
        migrations.RunPython(create_default_groups, remove_default_groups),
    ]