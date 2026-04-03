# tests/test_forms.py
import pytest
from django.core.exceptions import ValidationError
from core.forms import TransactionForm, BudgetForm, FamilyMemberAddForm, UserRegistrationForm
from core.models import FamilyMember

@pytest.mark.django_db
class TestTransactionForm:
    def test_valid_amount(self, user, family, expense_category):
        # ✅ Добавляем пользователя в семью, чтобы категория была в queryset формы
        FamilyMember.objects.create(user=user, family=family)
        form = TransactionForm({
            'amount': '100.00',
            'category': expense_category.id,
            'description': 'Тестовая покупка',
            'date': '2025-10-01'
        }, user=user)
        assert form.is_valid(), f"Ошибки формы: {form.errors}"

    def test_negative_amount_invalid(self, user, family, expense_category):
        # ✅ Также добавляем пользователя в семью для консистентности
        FamilyMember.objects.create(user=user, family=family)
        form = TransactionForm({
            'amount': '-50',
            'category': expense_category.id,
            'description': 'Тест',
            'date': '2025-10-01'
        }, user=user)
        assert not form.is_valid()
        assert 'amount' in form.errors

@pytest.mark.django_db
class TestBudgetForm:
    def test_month_format_valid(self, user, family, expense_category):
        # ✅ Добавляем пользователя в семью + передаём все поля
        FamilyMember.objects.create(user=user, family=family)
        form = BudgetForm({
            'category': expense_category.id,
            'amount': '1000.00',
            'month': '2025-12'
        }, user=user)
        assert form.is_valid(), f"Ошибки формы: {form.errors}"

    def test_month_format_invalid(self, user, family, expense_category):
        FamilyMember.objects.create(user=user, family=family)
        form = BudgetForm({
            'category': expense_category.id,
            'amount': '1000.00',
            'month': '12-2025'  # ❌ Неверный формат
        }, user=user)
        assert not form.is_valid()
        assert 'month' in form.errors

@pytest.mark.django_db
class TestFamilyMemberAddForm:
    def test_existing_user_in_same_family(self, user, family, family_head):
        # ✅ Создаём связь пользователя с семьёй
        FamilyMember.objects.create(user=user, family=family)
        form = FamilyMemberAddForm(
            {'username': 'testuser', 'role': 'member'},
            request_user=family_head
        )
        assert not form.is_valid()
        assert 'username' in form.errors
        # Проверяем текст ошибки
        assert 'уже состоит' in str(form.errors['username']).lower()