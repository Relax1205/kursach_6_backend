# core/context_processors.py
from .models import FamilyMember

def family_context(request):
    """
    Добавляет информацию о семье в контекст всех шаблонов.
    Доступно даже если пользователь не авторизован.
    """
    if not request.user.is_authenticated:
        return {
            'is_family': False,
            'family': None,
            'is_head': False,
            'can_manage': False,
        }
    
    try:
        family_member = FamilyMember.objects.get(user=request.user)
        family = family_member.family
        return {
            'is_family': True,
            'family': family,
            'is_head': family_member.is_head,
            'can_manage': request.user.has_perm('core.can_manage_family'),
        }
    except FamilyMember.DoesNotExist:
        return {
            'is_family': False,
            'family': None,
            'is_head': False,
            'can_manage': False,
        }