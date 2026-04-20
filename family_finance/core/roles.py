from django.contrib.auth.models import Group, Permission
from django.db import transaction

from .models import FamilyMember

ROLE_HEAD = 'head'
ROLE_MEMBER = 'member'
ROLE_VIEWER = 'viewer'

ROLE_GROUP_NAMES = {
    ROLE_HEAD: 'Глава семьи',
    ROLE_MEMBER: 'Член семьи',
    ROLE_VIEWER: 'Наблюдатель',
}

ROLE_PERMISSION_CODENAMES = {
    ROLE_HEAD: [
        'add_family',
        'change_family',
        'delete_family',
        'view_family',
        'add_category',
        'change_category',
        'delete_category',
        'view_category',
        'add_transaction',
        'change_transaction',
        'delete_transaction',
        'view_transaction',
        'add_budget',
        'change_budget',
        'delete_budget',
        'view_budget',
        'can_manage_family',
        'can_delete_any_transaction',
        'can_set_budget',
        'can_import_export',
    ],
    ROLE_MEMBER: [
        'add_transaction',
        'view_transaction',
        'view_category',
        'add_budget',
        'view_budget',
        'can_import_export',
    ],
    ROLE_VIEWER: [
        'view_transaction',
        'view_category',
        'view_budget',
        'can_view_family_reports',
    ],
}

ALL_ROLE_GROUP_NAMES = tuple(ROLE_GROUP_NAMES.values())
ALL_ROLE_PERMISSION_CODENAMES = sorted(
    {
        codename
        for codenames in ROLE_PERMISSION_CODENAMES.values()
        for codename in codenames
    }
)


def get_family_member_for_user(user):
    return FamilyMember.objects.select_related('family').filter(user=user).first()


def get_family_for_user(user):
    family_member = get_family_member_for_user(user)
    return family_member.family if family_member else None


def get_member_role(member):
    if member.is_head:
        return ROLE_HEAD
    if member.user.groups.filter(name=ROLE_GROUP_NAMES[ROLE_MEMBER]).exists():
        return ROLE_MEMBER
    return ROLE_VIEWER


def clear_family_role_access(user):
    ensure_default_groups()
    role_groups = list(user.groups.filter(name__in=ALL_ROLE_GROUP_NAMES))
    if role_groups:
        user.groups.remove(*role_groups)

    role_permissions = list(
        Permission.objects.filter(
            content_type__app_label='core',
            codename__in=ALL_ROLE_PERMISSION_CODENAMES,
            user=user,
        )
    )
    if role_permissions:
        user.user_permissions.remove(*role_permissions)


def _assign_role_group(user, role):
    ensure_default_groups()
    group = Group.objects.filter(name=ROLE_GROUP_NAMES[role]).first()
    if group:
        user.groups.add(group)


def ensure_default_groups():
    permissions = {
        permission.codename: permission
        for permission in Permission.objects.filter(
            content_type__app_label='core',
            codename__in=ALL_ROLE_PERMISSION_CODENAMES,
        )
    }

    for role, group_name in ROLE_GROUP_NAMES.items():
        group, _ = Group.objects.get_or_create(name=group_name)
        group.permissions.set(
            [
                permissions[codename]
                for codename in ROLE_PERMISSION_CODENAMES[role]
                if codename in permissions
            ]
        )


@transaction.atomic
def assign_family_role(member, role, demoted_head_role=ROLE_VIEWER):
    if role not in ROLE_GROUP_NAMES:
        raise ValueError(f'Unknown family role: {role}')

    if role == ROLE_HEAD:
        former_heads = list(
            member.family.members.select_related('user')
            .filter(is_head=True)
            .exclude(pk=member.pk)
        )
        for former_head in former_heads:
            former_head.is_head = False
            former_head.save(update_fields=['is_head'])
            clear_family_role_access(former_head.user)
            _assign_role_group(former_head.user, demoted_head_role)

    clear_family_role_access(member.user)
    member.is_head = role == ROLE_HEAD
    member.save(update_fields=['is_head'])
    _assign_role_group(member.user, role)
    return member
