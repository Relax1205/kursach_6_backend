import csv
from datetime import date as dt_date
from decimal import Decimal, InvalidOperation
from io import StringIO

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Sum
from django.utils import timezone

from .models import Budget, Category, FamilyMember, Transaction

HEADER_ALIASES = {
    'date': ('Дата', 'Date'),
    'user': ('Пользователь', 'User'),
    'type': ('Тип', 'Type'),
    'category': ('Категория', 'Category'),
    'amount': ('Сумма', 'Amount'),
    'description': ('Описание', 'Description'),
}


def _get_period_bounds(year, month):
    start_date = dt_date(year, month, 1)
    end_date = start_date + relativedelta(months=1) - relativedelta(days=1)
    return start_date, end_date


def _get_transactions_queryset(user=None, family=None):
    if family:
        return Transaction.objects.filter(user__familymember__family=family)
    return Transaction.objects.filter(user=user)


def get_monthly_summary(user=None, family=None, year=None, month=None):
    start_date, end_date = _get_period_bounds(year, month)
    base_qs = _get_transactions_queryset(user=user, family=family)

    income = base_qs.filter(
        category__type=Category.INCOME,
        date__range=[start_date, end_date],
    ).aggregate(total=Sum('amount'))['total'] or 0

    expense = base_qs.filter(
        category__type=Category.EXPENSE,
        date__range=[start_date, end_date],
    ).aggregate(total=Sum('amount'))['total'] or 0

    return {
        'income': income,
        'expense': expense,
        'balance': income - expense,
    }


def get_expense_breakdown_by_category(user=None, family=None, year=None, month=None):
    start_date, end_date = _get_period_bounds(year, month)
    base_qs = _get_transactions_queryset(user=user, family=family)

    return (
        base_qs.filter(
            category__type=Category.EXPENSE,
            date__range=[start_date, end_date],
        )
        .values('category__name')
        .annotate(total=Sum('amount'))
        .order_by('-total', 'category__name')
    )


def export_transactions_to_csv(response, user, family=None, include_user=None):
    if include_user is None:
        include_user = family is not None

    writer = csv.writer(response)
    headers = ['Дата']
    if include_user:
        headers.append('Пользователь')
    headers.extend(['Тип', 'Категория', 'Сумма', 'Описание'])
    writer.writerow(headers)

    transactions = (
        _get_transactions_queryset(user=user, family=family)
        .select_related('category', 'user')
        .order_by('-date', '-created_at')
    )

    for transaction in transactions:
        row = [transaction.date.strftime('%Y-%m-%d')]
        if include_user:
            row.append(transaction.user.username)
        row.extend(
            [
                'Доход'
                if transaction.category.type == Category.INCOME
                else 'Расход',
                transaction.category.name,
                transaction.amount,
                transaction.description or '',
            ]
        )
        writer.writerow(row)


def get_budget_vs_actual(user=None, family=None, year=None, month=None):
    start_date, end_date = _get_period_bounds(year, month)
    base_qs = _get_transactions_queryset(user=user, family=family)

    if family:
        budgets = Budget.objects.filter(family=family, month=start_date).select_related(
            'category'
        )
    else:
        budgets = Budget.objects.filter(user=user, month=start_date).select_related(
            'category'
        )

    result = []
    for budget in budgets.order_by('category__name'):
        actual = base_qs.filter(
            category=budget.category,
            date__range=[start_date, end_date],
        ).aggregate(total=Sum('amount'))['total'] or 0

        diff = budget.amount - actual
        result.append(
            {
                'category_name': budget.category.name,
                'budget_amount': budget.amount,
                'actual_amount': actual,
                'difference': diff,
                'is_over_budget': actual > budget.amount,
            }
        )
    return result


def get_budget_status(category, user=None, family=None, target_date=None, date=None):
    if target_date is None and date is not None:
        target_date = date
    current_date = target_date or timezone.localdate()
    month_start = current_date.replace(day=1)
    month_end = month_start + relativedelta(months=1) - relativedelta(days=1)
    base_qs = _get_transactions_queryset(user=user, family=family)

    if family:
        budget = Budget.objects.filter(
            family=family,
            category=category,
            month=month_start,
        ).first()
    else:
        budget = Budget.objects.filter(
            user=user,
            category=category,
            month=month_start,
        ).first()

    if not budget:
        return {'has_budget': False}

    spent = base_qs.filter(
        category=category,
        date__range=[month_start, month_end],
    ).aggregate(total=Sum('amount'))['total'] or 0

    remaining = budget.amount - spent
    percent_used = (spent / budget.amount * 100) if budget.amount > 0 else 0

    warning = None
    warning_type = 'info'
    if percent_used >= 100:
        warning = f"Бюджет '{category.name}' превышен на {abs(remaining):.2f} ₽!"
        warning_type = 'danger'
    elif percent_used >= 80:
        warning = (
            f"Внимание! Бюджет '{category.name}' использован на "
            f'{percent_used:.0f}%. Осталось {remaining:.2f} ₽.'
        )
        warning_type = 'warning'

    return {
        'has_budget': True,
        'budget_amount': budget.amount,
        'spent': spent,
        'remaining': remaining,
        'percent_used': percent_used,
        'warning': warning,
        'warning_type': warning_type,
    }


def _get_row_value(row, key):
    for alias in HEADER_ALIASES[key]:
        value = row.get(alias)
        if value is not None:
            return value.strip()
    return ''


def _parse_transaction_type(type_value, row_number):
    normalized = type_value.lower()
    if normalized in {'доход', Category.INCOME}:
        return Category.INCOME
    if normalized in {'расход', Category.EXPENSE}:
        return Category.EXPENSE
    raise ValidationError(f'Строка {row_number}: неизвестный тип операции "{type_value}".')


def import_transactions_from_csv(file, user):
    content = file.read().decode('utf-8-sig')
    reader = csv.DictReader(StringIO(content))
    if not reader.fieldnames:
        raise ValidationError('Пустой CSV-файл.')

    missing_headers = [
        key
        for key in ('date', 'type', 'category', 'amount')
        if not any(alias in reader.fieldnames for alias in HEADER_ALIASES[key])
    ]
    if missing_headers:
        raise ValidationError('CSV-файл не содержит обязательные колонки.')

    family_member = FamilyMember.objects.select_related('family').filter(user=user).first()
    family = family_member.family if family_member else None
    family_users = {}
    if family:
        family_users = {
            member.user.username: member.user
            for member in family.members.select_related('user')
        }

    count = 0
    with db_transaction.atomic():
        for row_number, row in enumerate(reader, start=2):
            if not row or all((value or '').strip() == '' for value in row.values()):
                continue

            date_str = _get_row_value(row, 'date')
            type_str = _get_row_value(row, 'type')
            category_name = _get_row_value(row, 'category')
            amount_str = _get_row_value(row, 'amount')
            description = _get_row_value(row, 'description')
            username = _get_row_value(row, 'user')

            if not date_str or not type_str or not category_name or not amount_str:
                raise ValidationError(
                    f'Строка {row_number}: заполните дату, тип, категорию и сумму.'
                )

            category_type = _parse_transaction_type(type_str, row_number)

            try:
                amount = Decimal(amount_str)
            except InvalidOperation as exc:
                raise ValidationError(
                    f'Строка {row_number}: сумма "{amount_str}" имеет неверный формат.'
                ) from exc

            if amount <= 0:
                raise ValidationError(f'Строка {row_number}: сумма должна быть положительной.')

            try:
                transaction_date = dt_date.fromisoformat(date_str)
            except ValueError as exc:
                raise ValidationError(
                    f'Строка {row_number}: дата "{date_str}" должна быть в формате ГГГГ-ММ-ДД.'
                ) from exc

            transaction_user = user
            if family and username:
                transaction_user = family_users.get(username)
                if transaction_user is None:
                    raise ValidationError(
                        f'Строка {row_number}: пользователь "{username}" не найден в семье.'
                    )
                if transaction_user != user and not user.has_perm('core.can_manage_family'):
                    raise ValidationError(
                        f'Строка {row_number}: можно импортировать операции только от своего имени.'
                    )

            if family:
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    type=category_type,
                    family=family,
                )
            else:
                category, _ = Category.objects.get_or_create(
                    name=category_name,
                    type=category_type,
                    user=user,
                )

            Transaction.objects.create(
                user=transaction_user,
                category=category,
                amount=amount,
                description=description,
                date=transaction_date,
            )
            count += 1

    return count
