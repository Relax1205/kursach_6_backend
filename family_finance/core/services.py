# core/services.py
"""
Модуль бизнес-логики приложения управления финансами.
"""
import csv
from decimal import Decimal
from datetime import date
from django.core.exceptions import ValidationError
from django.db.models import Sum, Q
from .models import Transaction, Category, Budget, FamilyMember

def get_monthly_summary(user=None, family=None, year=None, month=None):
    """Возвращает сводку по доходам и расходам за указанный месяц."""
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    end_date -= date.resolution
    
    if family:
        base_qs = Transaction.objects.filter(user__familymember__family=family)
    else:
        base_qs = Transaction.objects.filter(user=user)
    
    income = base_qs.filter(
        category__type=Category.INCOME,
        date__range=[start_date, end_date]
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    expense = base_qs.filter(
        category__type=Category.EXPENSE,
        date__range=[start_date, end_date]
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    return {
        'income': income,
        'expense': expense,
        'balance': income - expense,
    }

def get_expense_breakdown_by_category(user=None, family=None, year=None, month=None):
    """Возвращает детализацию расходов по категориям за месяц."""
    start_date = date(year, month, 1)
    if month == 12:
        end_date = date(year + 1, 1, 1)
    else:
        end_date = date(year, month + 1, 1)
    end_date -= date.resolution
    
    if family:
        base_qs = Transaction.objects.filter(user__familymember__family=family)
    else:
        base_qs = Transaction.objects.filter(user=user)
    
    return (
        base_qs.filter(
            category__type=Category.EXPENSE,
            date__range=[start_date, end_date]
        )
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total')
    )

def export_transactions_to_csv(response, user, family=None):
    """Экспортирует транзакции в CSV-файл."""
    writer = csv.writer(response)
    writer.writerow(['Дата', 'Пользователь', 'Тип', 'Категория', 'Сумма', 'Описание'])
    
    if family:
        transactions = Transaction.objects.filter(user__familymember__family=family).select_related('category', 'user').order_by('-date')
    else:
        transactions = Transaction.objects.filter(user=user).select_related('category').order_by('-date')
    
    for t in transactions:
        writer.writerow([
            t.date.strftime('%Y-%m-%d'),
            t.user.username,
            'Доход' if t.category.type == Category.INCOME else 'Расход',
            t.category.name,
            t.amount,
            t.description or ''
        ])

def get_budget_vs_actual(user=None, family=None, year=None, month=None):
    """Сравнивает установленные бюджеты с фактическими расходами за месяц."""
    from dateutil.relativedelta import relativedelta
    start_date = date(year, month, 1)
    end_date = start_date + relativedelta(months=1) - relativedelta(days=1)
    
    if family:
        budgets = Budget.objects.filter(family=family, month=start_date).select_related('category')
        base_qs = Transaction.objects.filter(user__familymember__family=family)
    else:
        budgets = Budget.objects.filter(user=user, month=start_date).select_related('category')
        base_qs = Transaction.objects.filter(user=user)
    
    result = []
    for budget in budgets:
        actual = base_qs.filter(
            category=budget.category,
            date__range=[start_date, end_date]
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        diff = budget.amount - actual
        result.append({
            'category_name': budget.category.name,
            'budget_amount': budget.amount,
            'actual_amount': actual,
            'difference': diff,
            'is_over_budget': actual > budget.amount,
        })
    return result

def import_transactions_from_csv(file, user):
    """Импортирует транзакции из CSV-файла."""
    from io import StringIO
    content = file.read().decode('utf-8')
    reader = csv.reader(StringIO(content))
    
    try:
        next(reader)
    except StopIteration:
        raise ValidationError("Пустой CSV-файл")
    
    count = 0
    try:
        family_member = FamilyMember.objects.get(user=user)
        family = family_member.family
    except FamilyMember.DoesNotExist:
        family = None
    
    for row in reader:
        if not row or all(cell.strip() == '' for cell in row):
            continue
        if len(row) < 4:
            continue
        
        date_str = row[0].strip()
        type_str = row[1].strip()
        category_name = row[2].strip()
        amount_str = row[3].strip()
        description = row[4].strip() if len(row) > 4 else ''
        
        if not date_str or not type_str or not category_name or not amount_str:
            continue
        
        if type_str == 'Доход':
            cat_type = Category.INCOME
        elif type_str == 'Расход':
            cat_type = Category.EXPENSE
        else:
            raise ValidationError(f'Неизвестный тип операции: {type_str}')
        
        if family:
            category, created = Category.objects.get_or_create(
                name=category_name,
                type=cat_type,
                family=family
            )
        else:
            category, created = Category.objects.get_or_create(
                name=category_name,
                type=cat_type,
                user=user
            )
        
        Transaction.objects.create(
            user=user,
            category=category,
            amount=Decimal(amount_str),
            description=description,
            date=date.fromisoformat(date_str)
        )
        count += 1
    return count