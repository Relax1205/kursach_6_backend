from .roles import get_family_member_for_user, get_member_role


def family_context(request):
    if not request.user.is_authenticated:
        return {
            'is_family': False,
            'family': None,
            'is_head': False,
            'can_manage': False,
            'family_role': None,
        }

    family_member = get_family_member_for_user(request.user)
    if not family_member:
        return {
            'is_family': False,
            'family': None,
            'is_head': False,
            'can_manage': False,
            'family_role': None,
        }

    return {
        'is_family': True,
        'family': family_member.family,
        'is_head': family_member.is_head,
        'can_manage': request.user.has_perm('core.can_manage_family'),
        'family_role': get_member_role(family_member),
    }
