# core/views.py
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.utils import timezone
from datetime import date
from dateutil.relativedelta import relativedelta
from django.http import HttpResponse
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from .models import Transaction, Category, Budget, FamilyMember
from .forms import TransactionForm, CategoryForm, BudgetForm, FamilyMemberFilterForm
from .services import (
    get_monthly_summary,
    get_expense_breakdown_by_category,
    get_budget_vs_actual,
    export_transactions_to_csv,
    import_transactions_from_csv
)

def get_user_family(request):
    """Вспомогательная функция для получения семьи пользователя."""
    try:
        family_member = FamilyMember.objects.get(user=request.user)
        return family_member.family
    except FamilyMember.DoesNotExist:
        return None

@login_required
def transaction_list(request):
    family = get_user_family(request)
    
    if family:
        transactions = Transaction.objects.filter(user__familymember__family=family)
    else:
        transactions = Transaction.objects.filter(user=request.user)
    
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')
    category_id = request.GET.get('category')
    member_id = request.GET.get('member')
    
    if start_date:
        transactions = transactions.filter(date__gte=start_date)
    if end_date:
        transactions = transactions.filter(date__lte=end_date)
    if category_id:
        transactions = transactions.filter(category_id=category_id)
    if member_id and member_id != 'all' and family:
        transactions = transactions.filter(user_id=member_id)
    
    transactions = transactions.select_related('category', 'user')
    
    if family:
        categories = Category.objects.filter(family=family)
    else:
        categories = Category.objects.filter(user=request.user)
    
    member_filter_form = FamilyMemberFilterForm(user=request.user, initial={'member': member_id or 'all'})
    
    return render(request, 'core/transaction_list.html', {
        'transactions': transactions,
        'categories': categories,
        'start_date': start_date,
        'end_date': end_date,
        'selected_category': category_id,
        'member_filter_form': member_filter_form,
        'is_family': family is not None,
    })

@login_required
def transaction_create(request):
    if request.method == 'POST':
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            transaction.save()
            messages.success(request, 'Транзакция добавлена.')
            return redirect('transaction_list')
    else:
        form = TransactionForm(user=request.user)
    return render(request, 'core/transaction_form.html', {'form': form, 'title': 'Добавить транзакцию'})

@login_required
def category_create(request):
    family = get_user_family(request)
    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = form.save(commit=False)
            if family:
                category.family = family
            else:
                category.user = request.user
            category.save()
            messages.success(request, 'Категория создана.')
            return redirect('transaction_create')
    else:
        form = CategoryForm()
    return render(request, 'core/transaction_form.html', {'form': form, 'title': 'Создать категорию'})

@login_required
def budget_list(request):
    # === ПРОВЕРКА ПРАВ ===
    if not request.user.has_perm('core.can_set_budget'):
        return render(request, 'core/budget_list.html', {
            'no_permission': True,
            'is_family': get_user_family(request) is not None,
        })
    
    family = get_user_family(request)
    
    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            if family:
                budget.family = family
            else:
                budget.user = request.user
            
            # Проверка на дубликат с правильными параметрами
            if family:
                existing = Budget.objects.filter(
                    family=family,
                    category=budget.category,
                    month=budget.month
                ).first()
            else:
                existing = Budget.objects.filter(
                    user=request.user,
                    category=budget.category,
                    month=budget.month
                ).first()
            
            if existing:
                existing.amount = budget.amount
                existing.save()
                messages.success(request, 'Бюджет обновлён.')
            else:
                budget.save()
                messages.success(request, 'Бюджет установлен.')
            return redirect('budget_list')
        else:
            # Форма не валидна - выводим ошибки
            messages.error(request, f'Ошибка в форме: {form.errors}')
    else:
        form = BudgetForm(user=request.user)
    
    today = date.today()
    current_month = today.replace(day=1)
    last_month = current_month - relativedelta(months=1)
    
    # Получаем бюджеты семьи или личные
    if family:
        budgets = Budget.objects.filter(
            family=family,
            month__in=[last_month, current_month]
        ).select_related('category')
    else:
        budgets = Budget.objects.filter(
            user=request.user,
            month__in=[last_month, current_month]
        ).select_related('category')
    
    return render(request, 'core/budget_list.html', {
        'form': form,
        'budgets': budgets,
        'current_month': current_month,
        'last_month': last_month,
        'is_family': family is not None,
        'no_permission': False,
    })
@login_required
def reports_view(request):
    family = get_user_family(request)
    today = date.today()
    year, month = today.year, today.month
    
    if family:
        summary = get_monthly_summary(family=family, year=year, month=month)
        expense_data = get_expense_breakdown_by_category(family=family, year=year, month=month)
        budget_comparison = get_budget_vs_actual(family=family, year=year, month=month)
    else:
        summary = get_monthly_summary(user=request.user, year=year, month=month)
        expense_data = get_expense_breakdown_by_category(user=request.user, year=year, month=month)
        budget_comparison = get_budget_vs_actual(user=request.user, year=year, month=month)
    
    from .models import Transaction, Category
    if family:
        total_expenses = Transaction.objects.filter(
            user__familymember__family=family,
            category__type=Category.EXPENSE
        ).count()
    else:
        total_expenses = Transaction.objects.filter(
            user=request.user,
            category__type=Category.EXPENSE
        ).count()
    
    labels = [item['category__name'] for item in expense_data]
    values = [float(item['total']) for item in expense_data]
    
    return render(request, 'core/reports.html', {
        'labels': labels,
        'values': values,
        'summary': summary,
        'expense_data': expense_data,
        'budget_comparison': budget_comparison,
        'current_month': f"{today.strftime('%B')} {year}",
        'is_family': family is not None,
        'has_any_expenses': total_expenses > 0,
    })

@login_required
def export_csv(request):
    if not request.user.has_perm('core.can_import_export'):
        raise PermissionDenied("У вас нет прав на экспорт данных.")
        
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    
    family = get_user_family(request)
    if family:
        transactions = Transaction.objects.filter(user__familymember__family=family).select_related('category', 'user')
        writer = csv.writer(response)
        writer.writerow(['Дата', 'Пользователь', 'Тип', 'Категория', 'Сумма', 'Описание'])
        for t in transactions:
            writer.writerow([
                t.date.strftime('%Y-%m-%d'),
                t.user.username,
                'Доход' if t.category.type == Category.INCOME else 'Расход',
                t.category.name,
                t.amount,
                t.description or ''
            ])
    else:
        export_transactions_to_csv(response, request.user)
    
    return response

@login_required
def import_csv(request):
    if not request.user.has_perm('core.can_import_export'):
        raise PermissionDenied("У вас нет прав на импорт данных.")

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Файл не выбран.')
            return render(request, 'core/import_csv.html')
        if not csv_file.name.endswith('.csv'):
            messages.error(request, 'Только CSV-файлы разрешены.')
            return render(request, 'core/import_csv.html')
        try:
            count = import_transactions_from_csv(csv_file, request.user)
            messages.success(request, f'Успешно импортировано {count} транзакций.')
            return redirect('transaction_list')
        except Exception as e:
            messages.error(request, f'Ошибка при импорте: {str(e)}')
            return render(request, 'core/import_csv.html')
    return render(request, 'core/import_csv.html')

@login_required
def transaction_delete(request, pk):
    """Удаление транзакции с проверкой прав."""
    transaction = get_object_or_404(Transaction, pk=pk)
    
    if transaction.user == request.user:
        pass
    elif request.user.has_perm('core.can_delete_any_transaction'):
        pass
    else:
        messages.error(request, 'Вы не можете удалить чужую транзакцию.')
        return redirect('transaction_list')
    
    if request.method == 'POST':
        transaction.delete()
        messages.success(request, 'Транзакция удалена.')
        return redirect('transaction_list')
    
    return render(request, 'core/transaction_confirm_delete.html', {'transaction': transaction})