import pytest
from django.urls import reverse
from core.models import Transaction, Budget

@pytest.mark.django_db
class TestRolePermissions:
    def test_head_can_manage_family(self, head_client):
        assert head_client.get(reverse('family_members')).status_code == 200
        assert head_client.get(reverse('family_members')).context['is_head'] is True

    def test_member_cannot_manage_family(self, member_client, family):
        resp = member_client.post(reverse('family_members'), {'username': 'fake', 'role': 'member'})
        assert resp.status_code == 302  # Редирект с ошибкой

    def test_viewer_cannot_export(self, viewer_client):
        assert viewer_client.get(reverse('export_csv')).status_code == 403

    def test_viewer_cannot_set_budget(self, viewer_client):
        resp = viewer_client.get(reverse('budget_list'))
        assert resp.context['no_permission'] is True

    def test_member_can_set_budget(self, member_client):
        resp = member_client.get(reverse('budget_list'))
        assert resp.context['no_permission'] is False