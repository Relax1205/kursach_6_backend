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
from django.contrib.auth.models import User, Group
from django.contrib.auth import login
from django.core.exceptions import PermissionDenied
from .models import Transaction, Category, Budget, FamilyMember, Family
from .forms import (
    TransactionForm, CategoryForm, BudgetForm, FamilyMemberFilterForm,
    FamilyCreateForm, FamilyMemberAddForm, FamilyMemberRoleForm,
    UserRegistrationForm, FamilyMemberInviteForm
)
from .services import (
    get_monthly_summary,
    get_expense_breakdown_by_category,
    get_budget_vs_actual,
    export_transactions_to_csv,
    import_transactions_from_csv,
    get_budget_status
)

def get_user_family(request):
    """Вспомогательная функция для получения семьи пользователя."""
    try:
        family_member = FamilyMember.objects.get(user=request.user)
        return family_member.family
    except FamilyMember.DoesNotExist:
        return None

def get_user_family_member(request):
    """Вспомогательная функция для получения записи участника семьи."""
    try:
        return FamilyMember.objects.get(user=request.user)
    except FamilyMember.DoesNotExist:
        return None

# === РЕГИСТРАЦИЯ ===

def register_view(request):
    """Страница регистрации нового пользователя."""
    if request.user.is_authenticated:
        return redirect('transaction_list')
    
    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Добро пожаловать, {user.username}! Регистрация успешна.')
            return redirect('family_dashboard')
        else:
            messages.error(request, 'Исправьте ошибки в форме.')
    else:
        form = UserRegistrationForm()
    
    return render(request, 'registration/register.html', {'form': form})

    
@login_required
def family_invite_member(request):
    """Глава семьи создаёт аккаунт для нового участника."""
    family = get_user_family(request)
    
    if not family or not request.user.has_perm('core.can_manage_family'):
        messages.error(request, 'У вас нет прав на приглашение участников.')
        return redirect('family_members')
    
    if request.method == 'POST':
        form = FamilyMemberInviteForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data['username'],
                email=form.cleaned_data.get('email', ''),
                password=form.cleaned_data['password1']
            )
            
            family_member = FamilyMember.objects.create(
                user=user,
                family=family,
                is_head=False
            )
            
            role = form.cleaned_data['role']
            if role == 'member':
                try:
                    member_group = Group.objects.get(name='Член семьи')
                    user.groups.add(member_group)
                    user.user_permissions.add(*member_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            elif role == 'viewer':
                try:
                    viewer_group = Group.objects.get(name='Наблюдатель')
                    user.groups.add(viewer_group)
                    user.user_permissions.add(*viewer_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            
            messages.success(request, f'Пользователь {user.username} успешно добавлен в семью!')
            return redirect('family_members')
    else:
        form = FamilyMemberInviteForm()
    
    return render(request, 'core/family_invite.html', {
        'form': form,
        'family': family
    })

# === УПРАВЛЕНИЕ СЕМЬЕЙ ===

@login_required
def family_dashboard(request):
    """Главная страница семьи / Личный кабинет."""
    # is_family и family уже доступны в шаблоне через контекстный процессор
    
    context = {}
    if request.user.is_authenticated:
        try:
            family_member = FamilyMember.objects.get(user=request.user)
            family = family_member.family
            context['members_count'] = family.members.count()
            context['transactions_count'] = Transaction.objects.filter(
                user__familymember__family=family
            ).count()
            context['budgets_count'] = Budget.objects.filter(
                family=family,
                month=date.today().replace(day=1)
            ).count()
        except FamilyMember.DoesNotExist:
            pass
    
    return render(request, 'core/family_dashboard.html', context)


@login_required
def family_create(request):
    """Создание новой семьи."""
    if get_user_family(request):
        messages.error(request, 'Вы уже состоите в семье. Нельзя создать новую.')
        return redirect('family_dashboard')
    
    if request.method == 'POST':
        form = FamilyCreateForm(request.POST)
        if form.is_valid():
            family = form.save()
            FamilyMember.objects.create(
                user=request.user,
                family=family,
                is_head=True
            )
            try:
                head_group = Group.objects.get(name='Глава семьи')
                request.user.groups.add(head_group)
                request.user.user_permissions.add(*head_group.permissions.all())
            except Group.DoesNotExist:
                pass
            
            messages.success(request, f'Семья "{family.name}" успешно создана! Вы назначены главой семьи.')
            return redirect('family_dashboard')
    else:
        form = FamilyCreateForm()
    
    return render(request, 'core/family_form.html', {
        'form': form,
        'title': 'Создать семью',
        'action': 'create'
    })

@login_required
def family_join(request):
    """Страница для входа в существующую семью."""
    if get_user_family(request):
        messages.error(request, 'Вы уже состоите в семье.')
        return redirect('family_dashboard')
    
    families = Family.objects.all()[:10]
    
    return render(request, 'core/family_join.html', {
        'families': families
    })

@login_required
def family_members(request):
    """Управление участниками семьи."""
    family = get_user_family(request)
    
    if not family:
        messages.error(request, 'Вы не состоите в семье.')
        return redirect('family_create')
    
    if not request.user.has_perm('core.can_manage_family'):
        messages.error(request, 'У вас нет прав на управление участниками.')
        return redirect('family_dashboard')
    
    members = family.members.select_related('user').order_by('-is_head', 'user__username')
    
    members_with_roles = []
    for member in members:
        if member.is_head:
            role = 'head'
        elif member.user.groups.filter(name='Член семьи').exists():
            role = 'member'
        else:
            role = 'viewer'
        members_with_roles.append({
            'member': member,
            'role': role
        })
    
    if request.method == 'POST':
        form = FamilyMemberAddForm(request.POST, request_user=request.user)
        if form.is_valid():
            username = form.cleaned_data['username']
            role = form.cleaned_data['role']
            
            user = User.objects.get(username=username)
            family_member, created = FamilyMember.objects.get_or_create(
                user=user,
                family=family
            )
            
            if role == 'head':
                family.members.update(is_head=False)
                family_member.is_head = True
                try:
                    head_group = Group.objects.get(name='Глава семьи')
                    user.groups.clear()
                    user.groups.add(head_group)
                    user.user_permissions.add(*head_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            elif role == 'member':
                family_member.is_head = False
                try:
                    member_group = Group.objects.get(name='Член семьи')
                    user.groups.clear()
                    user.groups.add(member_group)
                    user.user_permissions.add(*member_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            elif role == 'viewer':
                family_member.is_head = False
                try:
                    viewer_group = Group.objects.get(name='Наблюдатель')
                    user.groups.clear()
                    user.groups.add(viewer_group)
                    user.user_permissions.add(*viewer_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            
            family_member.save()
            messages.success(request, f'Пользователь {username} добавлен в семью с ролью "{role}".')
            return redirect('family_members')
    else:
        form = FamilyMemberAddForm(request_user=request.user)
    
    return render(request, 'core/family_members.html', {
        'family': family,
        'members_with_roles': members_with_roles,
        'form': form,
        'is_head': request.user.has_perm('core.can_manage_family')
    })

@login_required
def family_member_role_update(request, member_id):
    """Изменение роли участника семьи."""
    family = get_user_family(request)
    
    if not family or not request.user.has_perm('core.can_manage_family'):
        messages.error(request, 'У вас нет прав на это действие.')
        return redirect('family_members')
    
    member = get_object_or_404(FamilyMember, id=member_id, family=family)
    
    if request.method == 'POST':
        form = FamilyMemberRoleForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data['role']
            
            if role == 'head':
                family.members.update(is_head=False)
                member.is_head = True
                try:
                    head_group = Group.objects.get(name='Глава семьи')
                    member.user.groups.clear()
                    member.user.groups.add(head_group)
                    member.user.user_permissions.add(*head_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            elif role == 'member':
                member.is_head = False
                try:
                    member_group = Group.objects.get(name='Член семьи')
                    member.user.groups.clear()
                    member.user.groups.add(member_group)
                    member.user.user_permissions.add(*member_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            elif role == 'viewer':
                member.is_head = False
                try:
                    viewer_group = Group.objects.get(name='Наблюдатель')
                    member.user.groups.clear()
                    member.user.groups.add(viewer_group)
                    member.user.user_permissions.add(*viewer_group.permissions.all())
                except Group.DoesNotExist:
                    pass
            
            member.save()
            messages.success(request, f'Роль пользователя {member.user.username} изменена.')
            return redirect('family_members')
    else:
        if member.is_head:
            initial_role = 'head'
        elif member.user.groups.filter(name='Член семьи').exists():
            initial_role = 'member'
        else:
            initial_role = 'viewer'
        form = FamilyMemberRoleForm(initial={'role': initial_role})
    
    current_role = 'head' if member.is_head else ('member' if member.user.groups.filter(name='Член семьи').exists() else 'viewer')
    
    return render(request, 'core/family_member_role.html', {
        'member': member,
        'form': form,
        'family': family,
        'current_role': current_role
    })

@login_required
def family_leave(request):
    """Выход из семьи."""
    family = get_user_family(request)
    
    if not family:
        messages.error(request, 'Вы не состоите в семье.')
        return redirect('family_dashboard')
    
    family_member = get_user_family_member(request)
    
    if family_member.is_head:
        messages.error(request, 'Глава семьи не может покинуть семью. Сначала назначьте нового главу.')
        return redirect('family_members')
    
    if request.method == 'POST':
        family_member.delete()
        messages.success(request, 'Вы покинули семью.')
        return redirect('family_dashboard')
    
    return render(request, 'core/family_leave_confirm.html', {
        'family': family
    })

# === ТРАНЗАКЦИИ ===

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
    })

@login_required
def transaction_create(request):
    family = get_user_family(request)
    if request.method == 'POST':
        form = TransactionForm(request.POST, user=request.user)
        if form.is_valid():
            transaction = form.save(commit=False)
            transaction.user = request.user
            if transaction.category.type == Category.EXPENSE:
                budget_info = get_budget_status(
                    transaction.category,
                    user=request.user,
                    family=family,
                    date=transaction.date
                )
                if budget_info.get('has_budget'):
                    projected_spent = budget_info['spent'] + transaction.amount
                    projected_percent = (projected_spent / budget_info['budget_amount'] * 100)
                    if projected_percent >= 100:
                        messages.warning(
                            request,
                            f"Бюджет '{transaction.category.name}' будет превышен на {projected_spent - budget_info['budget_amount']:.2f} ₽!"
                        )
                    elif projected_percent >= 80:
                        messages.warning(
                            request,
                            f"Внимание! Бюджет '{transaction.category.name}' будет использован на {projected_percent:.0f}%."
                        )
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

# === БЮДЖЕТЫ ===

@login_required
def budget_list(request):
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
            messages.error(request, f'Ошибка в форме: {form.errors}')
    else:
        form = BudgetForm(user=request.user)

    today = date.today()
    current_month = today.replace(day=1)
    last_month = current_month - relativedelta(months=1)

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

# === ОТЧЁТЫ ===

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

# === ЭКСПОРТ/ИМПОРТ ===

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

# === УДАЛЕНИЕ ===

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