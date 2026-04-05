import pytest
from django.urls import reverse

from core.models import FamilyMember

@pytest.mark.django_db
class TestAuthViews:
    def test_register_redirect(self, anonymous_client):
        resp = anonymous_client.post(reverse('register'), {
            'username': 'newuser', 'email': 'n@t.com',
            'password1': 'Test1234!', 'password2': 'Test1234!'
        })
        assert resp.status_code == 302

    def test_protected_redirect_anonymous(self, anonymous_client):
        for url in ['family_dashboard', 'transaction_list', 'budget_list', 'reports']:
            assert anonymous_client.get(reverse(url)).status_code == 302

@pytest.mark.django_db
class TestFamilyViews:
    def test_create_family(self, authenticated_client, user):
        resp = authenticated_client.post(reverse('family_create'), {'name': 'Петровы'})
        assert resp.status_code == 302
        assert FamilyMember.objects.filter(user=user).exists()
        assert FamilyMember.objects.get(user=user).is_head is True

    def test_leave_family_member(self, member_client, family_member):
        resp = member_client.post(reverse('family_leave'))
        assert resp.status_code == 302
        assert not FamilyMember.objects.filter(id=family_member.id).exists()

@pytest.mark.django_db
class TestTransactionViews:
    def test_list_pagination(self, head_client, transactions_batch):
        # Допустимые значения: 10, 20, 50, 100 (остальное сбрасывается на 20)
        resp = head_client.get(reverse('transaction_list'), {'per_page': '10'})
        assert resp.status_code == 200
        assert len(resp.context['page_obj']) == 10

    def test_create_with_budget_warning(self, head_client, expense_category, budget):
        # Создаём транзакцию, превышающую бюджет
        resp = head_client.post(reverse('transaction_create'), {
            'amount': '10000', 'category': expense_category.id, 'date': '2025-10-20'
        })
        assert resp.status_code == 302
        # Проверка сообщения (упрощённо через follow)
        messages = list(resp.wsgi_request._messages)
        assert any('превышен' in m.message.lower() for m in messages)