import pytest
from decimal import Decimal
from datetime import date
from io import StringIO
from core.services import get_monthly_summary, get_budget_status, import_transactions_from_csv, export_transactions_to_csv
from core.models import Transaction
from django.core.files.uploadedfile import SimpleUploadedFile

@pytest.mark.django_db
class TestMonthlySummary:
    def test_correct_calculation(self, family, transactions_batch):
        res = get_monthly_summary(family=family, year=2025, month=10)
        assert res['income'] == Decimal('50000.00')
        assert res['expense'] == Decimal('10000.00')
        assert res['balance'] == Decimal('40000.00')

    def test_empty_month(self, family):
        res = get_monthly_summary(family=family, year=2026, month=1)
        assert res == {'income': 0, 'expense': 0, 'balance': 0}

@pytest.mark.django_db
class TestBudgetStatus:
    def test_over_budget(self, family, expense_category, budget):
        Transaction.objects.create(user=family.members.first().user, category=expense_category, amount=12000, date=date(2025, 10, 10))
        status = get_budget_status(expense_category, family=family, date=date(2025, 10, 20))
        assert status['percent_used'] == 120
        assert status['warning_type'] == 'danger'

@pytest.mark.django_db
class TestCSVServices:
    def test_export_structure(self, user, transactions_batch):
        out = StringIO()
        export_transactions_to_csv(out, user, family=None)
        out.seek(0)
        lines = out.readlines()
        assert 'Дата,Пользователь,Тип,Категория,Сумма,Описание' in lines[0]
        assert len(lines) == 12  # header + 11 txs

    def test_import_valid(self, user):
        csv_data = "Дата,Тип,Категория,Сумма,Описание\n2025-10-01,Расход,Тест,100,Примечание"
        f = SimpleUploadedFile("test.csv", csv_data.encode('utf-8'), content_type="text/csv")
        count = import_transactions_from_csv(f, user)
        assert count == 1
        assert Transaction.objects.filter(user=user, category__name='Тест').exists()