import pytest
from django.urls import reverse
from core.models import Transaction, Budget, FamilyMember

@pytest.mark.django_db
class TestRolePermissions:
    def test_head_can_manage_family(self, head_client):
        assert head_client.get(reverse('family_members')).status_code == 200
        assert head_client.get(reverse('family_members')).context['is_head'] is True

    def test_member_cannot_manage_family(self, member_client, family):
        resp = member_client.post(reverse('family_members'), {'username': 'fake', 'role': 'member'})
        assert resp.status_code == 302  # Редирект с ошибкой

    def test_transfer_head_strips_old_head_permissions(self, head_client, family_head, family_member):
        """После назначения другого главы бывший глава теряет can_manage_family и группу главы."""
        fm_new = FamilyMember.objects.get(user=family_member)
        resp = head_client.post(
            reverse('family_member_role', kwargs={'member_id': fm_new.pk}),
            {'role': 'head'},
        )
        assert resp.status_code == 302
        family_head.refresh_from_db()
        assert not family_head.has_perm('core.can_manage_family')
        assert not family_head.groups.filter(name='Глава семьи').exists()
        assert family_head.groups.filter(name='Наблюдатель').exists()
        fm_new.refresh_from_db()
        assert fm_new.is_head is True

    def test_viewer_cannot_export(self, viewer_client):
        assert viewer_client.get(reverse('export_csv')).status_code == 403

    def test_viewer_cannot_set_budget(self, viewer_client):
        resp = viewer_client.get(reverse('budget_list'))
        assert resp.context['no_permission'] is True

    def test_member_cannot_set_budget(self, member_client):
        """У «Член семьи» в миграции нет can_set_budget — только add/view budget."""
        resp = member_client.get(reverse('budget_list'))
        assert resp.context['no_permission'] is True