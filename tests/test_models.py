import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from core.models import Family, FamilyMember, Category, Transaction, Budget

@pytest.mark.django_db
class TestFamilyModel:
    def test_create_with_name(self):
        f = Family.objects.create(name='Ивановы')
        assert f.name == 'Ивановы'

    def test_default_name(self):
        f = Family.objects.create()
        assert f.name == 'Моя семья'

    def test_str(self):
        assert str(Family.objects.create(name='Тест')) == 'Тест'

@pytest.mark.django_db
class TestFamilyMemberModel:
    def test_one_to_one_constraint(self, user, family):
        FamilyMember.objects.create(user=user, family=family)
        with pytest.raises(ValidationError):
            FamilyMember.objects.create(user=user, family=Family.objects.create(name='Вторая'))

    def test_is_head_flag(self, user, family):
        m = FamilyMember.objects.create(user=user, family=family, is_head=True)
        assert m.is_head is True

@pytest.mark.django_db
class TestCategoryModel:
    def test_constants(self):
        assert Category.INCOME == 'income'
        assert Category.EXPENSE == 'expense'

    def test_family_category(self, family):
        c = Category.objects.create(name='Еда', type=Category.EXPENSE, family=family)
        assert c.family == family

    def test_personal_category(self, user):
        c = Category.objects.create(name='Личное', type=Category.EXPENSE, user=user)
        assert c.user == user

@pytest.mark.django_db
class TestTransactionModel:
    def test_create_and_ordering(self, user, family, expense_category):
        FamilyMember.objects.create(user=user, family=family)
        t1 = Transaction.objects.create(user=user, category=expense_category, amount=100, date=date(2025, 1, 1))
        t2 = Transaction.objects.create(user=user, category=expense_category, amount=200, date=date(2025, 1, 2))
        assert Transaction.objects.all()[0] == t2  # Сортировка по убыванию даты

@pytest.mark.django_db
class TestBudgetModel:
    def test_str_format(self, family, expense_category):
        b = Budget.objects.create(family=family, category=expense_category, amount=5000, month=date(2025, 10, 1))
        # ✅ Исправлено: формат суммы в __str__ модели — без .00 для целых чисел
        assert str(b) == f'{expense_category} — 5000 (2025-10)'
