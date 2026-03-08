# core/tests.py
"""
Тесты для приложения управления личными финансами.
Покрывают модели, формы, сервисы и основные сценарии использования.
"""

from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone
from datetime import date
from decimal import Decimal
from .models import Transaction, Category, Budget
from .forms import TransactionForm, CategoryForm, BudgetForm
from .services import get_monthly_summary, get_expense_breakdown_by_category, export_transactions_to_csv, import_transactions_from_csv
from io import StringIO
import csv


class UserModelMixin:
    """Миксин для создания тестового пользователя."""
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='testpass123')
        self.client = Client()
        self.client.login(username='testuser', password='testpass123')


class CategoryModelTest(UserModelMixin, TestCase):
    """Тесты модели Category."""

    def test_create_category(self):
        category = Category.objects.create(
            name='Еда',
            type=Category.EXPENSE,
            user=self.user
        )
        self.assertEqual(str(category), 'Еда (Расход)')
        self.assertEqual(category.user, self.user)

    def test_unique_together_constraint(self):
        Category.objects.create(name='Зарплата', type=Category.INCOME, user=self.user)
        with self.assertRaises(Exception):
            Category.objects.create(name='Зарплата', type=Category.INCOME, user=self.user)


class TransactionModelTest(UserModelMixin, TestCase):
    """Тесты модели Transaction."""

    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(
            name='Продукты',
            type=Category.EXPENSE,
            user=self.user
        )

    def test_create_transaction(self):
        transaction = Transaction.objects.create(
            user=self.user,
            amount=Decimal('150.75'),
            category=self.category,
            description='Покупка в магазине',
            date=date.today()
        )
        self.assertEqual(transaction.amount, Decimal('150.75'))
        self.assertEqual(str(transaction), f'Продукты (Расход) — 150.75 ({date.today()})')


class BudgetModelTest(UserModelMixin, TestCase):
    """Тесты модели Budget."""

    def setUp(self):
        super().setUp()
        self.category = Category.objects.create(
            name='Транспорт',
            type=Category.EXPENSE,
            user=self.user
        )

    def test_create_budget(self):
        budget_date = date(2025, 10, 1)
        budget = Budget.objects.create(
            user=self.user,
            category=self.category,
            amount=Decimal('5000.00'),
            month=budget_date
        )
        self.assertEqual(budget.month, budget_date)
        self.assertEqual(str(budget), 'Транспорт (Расход) — 5000.00 (2025-10)')


class FormsTest(UserModelMixin, TestCase):
    """Тесты форм."""

    def setUp(self):
        super().setUp()
        self.expense_cat = Category.objects.create(name='Еда', type=Category.EXPENSE, user=self.user)
        self.income_cat = Category.objects.create(name='ЗП', type=Category.INCOME, user=self.user)

    def test_transaction_form_valid(self):
        form_data = {
            'amount': '200.00',
            'category': self.expense_cat.id,
            'description': 'Обед',
            'date': date.today()
        }
        form = TransactionForm(data=form_data, user=self.user)
        self.assertTrue(form.is_valid())

    def test_transaction_form_invalid_amount(self):
        form_data = {
            'amount': '-50.00',  # Отрицательная сумма — недопустима в форме (хотя модель позволяет)
            'category': self.expense_cat.id,
            'description': 'Ошибка',
            'date': date.today()
        }
        form = TransactionForm(data=form_data, user=self.user)
        self.assertFalse(form.is_valid())

    def test_budget_form_sets_first_day_of_month(self):
        form_data = {
            'category': self.expense_cat.id,
            'amount': '3000.00',
            'month': '2025-10-15'  # Должно стать 2025-10-01
        }
        form = BudgetForm(data=form_data, user=self.user)
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data['month'], date(2025, 10, 1))


class ServicesTest(UserModelMixin, TestCase):
    """Тесты сервисов (бизнес-логики)."""

    def setUp(self):
        super().setUp()
        self.expense_cat = Category.objects.create(name='Еда', type=Category.EXPENSE, user=self.user)
        self.income_cat = Category.objects.create(name='ЗП', type=Category.INCOME, user=self.user)

        # Транзакции за октябрь 2025
        Transaction.objects.create(user=self.user, amount=Decimal('50000'), category=self.income_cat, date=date(2025, 10, 5))
        Transaction.objects.create(user=self.user, amount=Decimal('1000'), category=self.expense_cat, date=date(2025, 10, 10))
        Transaction.objects.create(user=self.user, amount=Decimal('500'), category=self.expense_cat, date=date(2025, 10, 20))

    def test_get_monthly_summary(self):
        result = get_monthly_summary(self.user, 2025, 10)
        self.assertEqual(result['income'], Decimal('50000'))
        self.assertEqual(result['expense'], Decimal('1500'))
        self.assertEqual(result['balance'], Decimal('48500'))

    def test_get_expense_breakdown(self):
        result = list(get_expense_breakdown_by_category(self.user, 2025, 10))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['category__name'], 'Еда')
        self.assertEqual(result[0]['total'], Decimal('1500'))

    def test_export_csv(self):
        output = StringIO()
        export_transactions_to_csv(output, self.user)
        output.seek(0)
        reader = csv.reader(output)
        rows = list(reader)
        self.assertEqual(len(rows), 4)  # заголовок + 3 транзакции
        self.assertIn('Еда', rows[1][2])  # категория в третьем столбце
    
    def test_import_csv(self):
        # Удалим все существующие транзакции этого пользователя
        Transaction.objects.filter(user=self.user).delete()
        
        csv_data = (
            "Дата,Тип,Категория,Сумма,Описание\n"
            "2025-10-01,Доход,ЗП,50000,\n"
            "2025-10-02,Расход,Еда,1000,Продукты\n"
        )
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_file = SimpleUploadedFile("transactions.csv", csv_data.encode('utf-8'), content_type="text/csv")

        count = import_transactions_from_csv(csv_file, self.user)
        self.assertEqual(count, 2)

        # Теперь должно быть ровно 2 транзакции
        self.assertEqual(Transaction.objects.filter(user=self.user).count(), 2)
        self.assertTrue(Transaction.objects.filter(category__name='ЗП', amount=Decimal('50000')).exists())
        self.assertTrue(Transaction.objects.filter(category__name='Еда', amount=Decimal('1000')).exists())


class ViewsTest(UserModelMixin, TestCase):
    """Тесты представлений (базовое покрытие)."""

    def test_transaction_list_view(self):
        response = self.client.get(reverse('transaction_list'))
        self.assertEqual(response.status_code, 200)

    def test_reports_view(self):
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)

    def test_export_csv_view(self):
        response = self.client.get(reverse('export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('attachment; filename="transactions.csv"', response['Content-Disposition'])
    
    def test_import_csv_view(self):
        response = self.client.get(reverse('import_csv'))
        self.assertEqual(response.status_code, 200)

    def test_transaction_delete(self):
        # Создаём транзакцию
        category = Category.objects.create(name='Тест', type=Category.EXPENSE, user=self.user)
        transaction = Transaction.objects.create(
            user=self.user,
            category=category,
            amount=Decimal('100.00'),
            date=date.today()
        )
        
        # Удаляем через POST
        response = self.client.post(reverse('transaction_delete', kwargs={'pk': transaction.pk}))
        self.assertEqual(response.status_code, 302)  # редирект
        self.assertFalse(Transaction.objects.filter(pk=transaction.pk).exists())
