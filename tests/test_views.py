import pytest
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Budget, Category, FamilyMember, Transaction

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

    def test_dashboard_shows_member_role(self, member_client):
        resp = member_client.get(reverse('family_dashboard'))

        assert resp.status_code == 200
        assert resp.context['family_role'] == 'member'
        assert 'Член семьи' in resp.content.decode('utf-8')

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

    def test_head_can_delete_any_family_transaction(self, head_client, family_member, expense_category):
        transaction = Transaction.objects.create(
            user=family_member,
            category=expense_category,
            amount=Decimal('450.00'),
            description='Чужая транзакция',
            date=date(2025, 10, 12),
        )

        get_response = head_client.get(
            reverse('transaction_delete', kwargs={'pk': transaction.pk})
        )
        assert get_response.status_code == 200

        post_response = head_client.post(
            reverse('transaction_delete', kwargs={'pk': transaction.pk})
        )
        assert post_response.status_code == 302
        assert not Transaction.objects.filter(pk=transaction.pk).exists()


@pytest.mark.django_db
class TestFamilyManagementViews:
    def test_head_can_invite_member_from_form(self, head_client, family):
        response = head_client.get(reverse('family_invite'))
        assert response.status_code == 200

        post_response = head_client.post(
            reverse('family_invite'),
            {
                'username': 'invited_user',
                'email': 'invited@example.com',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
                'role': 'viewer',
            },
        )

        assert post_response.status_code == 302
        invited_member = FamilyMember.objects.get(user__username='invited_user')
        assert invited_member.family == family
        assert invited_member.is_head is False

    def test_head_can_open_role_update_page(self, head_client, family_member):
        member = FamilyMember.objects.get(user=family_member)

        response = head_client.get(
            reverse('family_member_role', kwargs={'member_id': member.pk})
        )

        assert response.status_code == 200
        assert response.context['current_role'] == 'member'

    def test_family_leave_confirmation_page_for_member(self, member_client):
        response = member_client.get(reverse('family_leave'))

        assert response.status_code == 200
        assert 'Выход из семьи' in response.content.decode('utf-8')


@pytest.mark.django_db
class TestBudgetViews:
    def test_head_can_open_and_delete_budget(self, head_client, budget):
        response = head_client.get(reverse('budget_delete', kwargs={'pk': budget.pk}))
        assert response.status_code == 200

        post_response = head_client.post(reverse('budget_delete', kwargs={'pk': budget.pk}))
        assert post_response.status_code == 302
        assert not Budget.objects.filter(pk=budget.pk).exists()

    def test_head_can_view_budget_list_with_existing_budgets(self, head_client, family, expense_category):
        current_month = date.today().replace(day=1)
        Budget.objects.create(
            family=family,
            category=expense_category,
            amount=Decimal('15000.00'),
            month=current_month,
        )

        response = head_client.get(reverse('budget_list'))

        assert response.status_code == 200
        assert response.context['no_permission'] is False
        assert response.context['budgets'].count() >= 1


@pytest.mark.django_db
class TestCategoryViews:
    def test_head_can_open_category_create_page(self, head_client):
        response = head_client.get(reverse('category_create'))

        assert response.status_code == 200
        assert 'Создать категорию' in response.content.decode('utf-8')

    def test_head_can_delete_unused_category(self, head_client, family):
        category = Category.objects.create(
            name='Быт',
            type=Category.EXPENSE,
            family=family,
        )

        response = head_client.get(reverse('category_delete', kwargs={'pk': category.pk}))
        assert response.status_code == 200

        post_response = head_client.post(
            reverse('category_delete', kwargs={'pk': category.pk})
        )
        assert post_response.status_code == 302
        assert not Category.objects.filter(pk=category.pk).exists()

    def test_category_delete_rejects_category_with_transactions(
        self, head_client, family_head, expense_category
    ):
        Transaction.objects.create(
            user=family_head,
            category=expense_category,
            amount=Decimal('999.00'),
            description='Привязанная',
            date=date(2025, 10, 10),
        )

        response = head_client.post(
            reverse('category_delete', kwargs={'pk': expense_category.pk}),
            follow=True,
        )

        assert response.status_code == 200
        assert Category.objects.filter(pk=expense_category.pk).exists()
        messages = list(response.context['messages'])
        assert any('Нельзя удалить категорию' in m.message for m in messages)


@pytest.mark.django_db
class TestReportsAndImportViews:
    def test_viewer_can_open_family_reports(self, viewer_client):
        response = viewer_client.get(reverse('reports'))

        assert response.status_code == 200
        assert 'Финансовые отчёты' in response.content.decode('utf-8')

    def test_member_can_open_import_page(self, member_client):
        response = member_client.get(reverse('import_csv'))

        assert response.status_code == 200
        assert 'Импорт транзакций из CSV' in response.content.decode('utf-8')

    def test_import_csv_requires_uploaded_file(self, member_client):
        response = member_client.post(reverse('import_csv'), {}, follow=True)

        assert response.status_code == 200
        messages = list(response.context['messages'])
        assert any('Файл не выбран' in m.message for m in messages)

    def test_import_csv_rejects_non_csv_file(self, member_client):
        invalid_file = SimpleUploadedFile(
            'transactions.txt',
            b'not-a-csv',
            content_type='text/plain',
        )

        response = member_client.post(
            reverse('import_csv'),
            {'csv_file': invalid_file},
            follow=True,
        )

        assert response.status_code == 200
        messages = list(response.context['messages'])
        assert any('Разрешены только CSV-файлы' in m.message for m in messages)

    def test_export_csv_without_transactions_redirects(self, head_client):
        response = head_client.get(reverse('export_csv'), follow=True)

        assert response.status_code == 200
        assert response.redirect_chain
        messages = list(response.context['messages'])
        assert any('нет транзакций для экспорта' in m.message.lower() for m in messages)
