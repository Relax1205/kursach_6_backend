from dateutil.relativedelta import relativedelta
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    BudgetForm,
    CategoryForm,
    FamilyCreateForm,
    FamilyMemberAddForm,
    FamilyMemberFilterForm,
    FamilyMemberInviteForm,
    FamilyMemberRoleForm,
    TransactionForm,
    UserRegistrationForm,
)
from .models import Budget, Category, Family, FamilyMember, Transaction
from .roles import (
    ROLE_HEAD,
    assign_family_role,
    clear_family_role_access,
    get_family_for_user,
    get_family_member_for_user,
    get_member_role,
)
from .services import (
    export_transactions_to_csv,
    get_budget_status,
    get_budget_vs_actual,
    get_expense_breakdown_by_category,
    get_monthly_summary,
    import_transactions_from_csv,
)


def get_user_family(request):
    return get_family_for_user(request.user)


def get_user_family_member(request):
    return get_family_member_for_user(request.user)


def _can_manage_family_reports(user, family):
    return family is None or user.has_perm('core.can_manage_family') or user.has_perm(
        'core.can_view_family_reports'
    )


def _can_manage_budgets(user, family):
    return family is None or user.has_perm('core.can_set_budget')


def _can_import_export(user, family):
    return family is None or user.has_perm('core.can_import_export')


def _can_manage_family_categories(user, family, permission_codename):
    return family is None or user.has_perm(f'core.{permission_codename}')


def register_view(request):
    if request.user.is_authenticated:
        return redirect('transaction_list')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(
                request,
                f'Добро пожаловать, {user.username}! Регистрация успешна.',
            )
            return redirect('family_dashboard')
        messages.error(request, 'Исправьте ошибки в форме.')
    else:
        form = UserRegistrationForm()

    return render(request, 'registration/register.html', {'form': form})


@login_required
def family_invite_member(request):
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
                password=form.cleaned_data['password1'],
            )
            family_member = FamilyMember.objects.create(
                user=user,
                family=family,
                is_head=False,
            )
            assign_family_role(family_member, form.cleaned_data['role'])
            messages.success(
                request,
                f'Пользователь {user.username} успешно добавлен в семью.',
            )
            return redirect('family_members')
        messages.error(request, 'Не удалось пригласить участника. Проверьте форму.')
    else:
        form = FamilyMemberInviteForm()

    return render(request, 'core/family_invite.html', {'form': form, 'family': family})


@login_required
def family_dashboard(request):
    family_member = get_user_family_member(request)
    context = {}

    if family_member:
        family = family_member.family
        current_month = timezone.localdate().replace(day=1)
        context.update(
            {
                'members_count': family.members.count(),
                'transactions_count': Transaction.objects.filter(
                    user__familymember__family=family
                ).count(),
                'budgets_count': Budget.objects.filter(
                    family=family,
                    month=current_month,
                ).count(),
            }
        )

    return render(request, 'core/family_dashboard.html', context)


@login_required
def family_create(request):
    if get_user_family(request):
        messages.error(request, 'Вы уже состоите в семье. Нельзя создать новую.')
        return redirect('family_dashboard')

    if request.method == 'POST':
        form = FamilyCreateForm(request.POST)
        if form.is_valid():
            family = form.save()
            family_member = FamilyMember.objects.create(
                user=request.user,
                family=family,
                is_head=False,
            )
            assign_family_role(family_member, ROLE_HEAD)
            messages.success(
                request,
                f'Семья "{family.name}" успешно создана. Вы назначены главой семьи.',
            )
            return redirect('family_dashboard')
    else:
        form = FamilyCreateForm()

    return render(
        request,
        'core/family_form.html',
        {'form': form, 'title': 'Создать семью', 'action': 'create'},
    )


@login_required
def family_members(request):
    family = get_user_family(request)
    if not family:
        messages.error(request, 'Вы не состоите в семье.')
        return redirect('family_create')

    members = family.members.select_related('user').order_by('-is_head', 'user__username')
    members_with_roles = [
        {'member': member, 'role': get_member_role(member)}
        for member in members
    ]

    if request.method == 'POST':
        if not request.user.has_perm('core.can_manage_family'):
            messages.error(request, 'У вас нет прав на управление участниками.')
            return redirect('family_members')

        form = FamilyMemberAddForm(request.POST, request_user=request.user)
        if form.is_valid():
            user = form.get_target_user()
            family_member = FamilyMember.objects.create(
                user=user,
                family=family,
                is_head=False,
            )
            role = form.cleaned_data['role']
            assign_family_role(family_member, role)
            messages.success(
                request,
                f'Пользователь {user.username} добавлен в семью с ролью "{role}".',
            )
            return redirect('family_members')
        messages.error(request, 'Ошибка в форме добавления участника.')
    else:
        form = FamilyMemberAddForm(request_user=request.user)

    return render(
        request,
        'core/family_members.html',
        {
            'family': family,
            'members_with_roles': members_with_roles,
            'form': form,
            'is_head': request.user.has_perm('core.can_manage_family'),
        },
    )


@login_required
def family_member_role_update(request, member_id):
    family = get_user_family(request)
    if not family or not request.user.has_perm('core.can_manage_family'):
        messages.error(request, 'У вас нет прав на это действие.')
        return redirect('family_members')

    member = get_object_or_404(FamilyMember, id=member_id, family=family)
    current_role = get_member_role(member)

    if request.method == 'POST':
        form = FamilyMemberRoleForm(request.POST)
        if form.is_valid():
            role = form.cleaned_data['role']
            try:
                assign_family_role(member, role)
            except ValidationError as exc:
                messages.error(request, ' '.join(exc.messages))
                return redirect('family_members')
            messages.success(
                request,
                f'Роль пользователя {member.user.username} изменена.',
            )
            return redirect('family_members')
        messages.error(request, 'Не удалось изменить роль пользователя.')
    else:
        form = FamilyMemberRoleForm(initial={'role': current_role})

    return render(
        request,
        'core/family_member_role.html',
        {
            'member': member,
            'form': form,
            'family': family,
            'current_role': current_role,
        },
    )


@login_required
def family_leave(request):
    family_member = get_user_family_member(request)
    if not family_member:
        messages.error(request, 'Вы не состоите в семье.')
        return redirect('family_dashboard')

    if family_member.is_head:
        messages.error(
            request,
            'Глава семьи не может покинуть семью. Сначала назначьте нового главу.',
        )
        return redirect('family_members')

    if request.method == 'POST':
        clear_family_role_access(request.user)
        family_member.delete()
        messages.success(request, 'Вы покинули семью.')
        return redirect('family_dashboard')

    return render(request, 'core/family_leave_confirm.html', {'family': family_member.family})


@login_required
def transaction_list(request):
    family = get_user_family(request)
    transactions = (
        Transaction.objects.filter(user__familymember__family=family)
        if family
        else Transaction.objects.filter(user=request.user)
    )

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

    transactions = transactions.select_related('category', 'user').order_by(
        '-date', '-created_at'
    )

    categories = (
        Category.objects.filter(family=family)
        if family
        else Category.objects.filter(user=request.user)
    ).order_by('type', 'name')

    per_page = request.GET.get('per_page', '20')
    try:
        per_page = int(per_page)
        if per_page not in [10, 20, 50, 100]:
            per_page = 20
    except (TypeError, ValueError):
        per_page = 20

    paginator = Paginator(transactions, per_page)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.get_page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.get_page(1)

    member_filter_form = FamilyMemberFilterForm(
        user=request.user,
        initial={'member': member_id or 'all'},
    )

    return render(
        request,
        'core/transaction_list.html',
        {
            'page_obj': page_obj,
            'paginator': paginator,
            'categories': categories,
            'start_date': start_date,
            'end_date': end_date,
            'selected_category': category_id,
            'member_filter_form': member_filter_form,
            'per_page': per_page,
            'per_page_options': [10, 20, 50, 100],
        },
    )


@login_required
def transaction_create(request):
    family = get_user_family(request)
    if family and not request.user.has_perm('core.add_transaction'):
        messages.error(request, 'У вас нет прав на создание транзакций.')
        return redirect('transaction_list')

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
                    target_date=transaction.date,
                )
                if budget_info.get('has_budget'):
                    projected_spent = budget_info['spent'] + transaction.amount
                    projected_percent = (
                        projected_spent / budget_info['budget_amount'] * 100
                    )
                    if projected_percent >= 100:
                        messages.warning(
                            request,
                            (
                                f"Бюджет '{transaction.category.name}' будет превышен на "
                                f"{projected_spent - budget_info['budget_amount']:.2f} ₽!"
                            ),
                        )
                    elif projected_percent >= 80:
                        messages.warning(
                            request,
                            (
                                f"Внимание! Бюджет '{transaction.category.name}' будет "
                                f'использован на {projected_percent:.0f}%.'
                            ),
                        )

            transaction.save()
            messages.success(request, 'Транзакция добавлена.')
            return redirect('transaction_list')
    else:
        form = TransactionForm(user=request.user)

    return render(
        request,
        'core/transaction_form.html',
        {'form': form, 'title': 'Добавить транзакцию'},
    )


@login_required
def category_create(request):
    family = get_user_family(request)
    if family and not _can_manage_family_categories(request.user, family, 'add_category'):
        messages.error(request, 'У вас нет прав на создание категорий.')
        return redirect('transaction_list')

    if request.method == 'POST':
        form = CategoryForm(request.POST, user=request.user)
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
        form = CategoryForm(user=request.user)

    categories = (
        Category.objects.filter(family=family)
        if family
        else Category.objects.filter(user=request.user)
    ).order_by('type', 'name')

    return render(
        request,
        'core/transaction_form.html',
        {
            'form': form,
            'title': 'Создать категорию',
            'categories': categories,
        },
    )


@login_required
def budget_list(request):
    family = get_user_family(request)
    if not _can_manage_budgets(request.user, family):
        return render(
            request,
            'core/budget_list.html',
            {
                'no_permission': True,
                'is_family': family is not None,
            },
        )

    if request.method == 'POST':
        form = BudgetForm(request.POST, user=request.user)
        if form.is_valid():
            budget = form.save(commit=False)
            scope = {
                'category': budget.category,
                'month': budget.month,
            }
            if family:
                scope['family'] = family
            else:
                scope['user'] = request.user

            _, created = Budget.objects.update_or_create(
                defaults={'amount': budget.amount},
                **scope,
            )
            messages.success(
                request,
                'Бюджет установлен.' if created else 'Бюджет обновлён.',
            )
            return redirect('budget_list')
        messages.error(request, 'Ошибка в форме бюджета.')
    else:
        form = BudgetForm(user=request.user)

    current_month = timezone.localdate().replace(day=1)
    last_month = current_month - relativedelta(months=1)
    if family:
        budgets = Budget.objects.filter(
            family=family,
            month__in=[last_month, current_month],
        )
    else:
        budgets = Budget.objects.filter(
            user=request.user,
            month__in=[last_month, current_month],
        )
    budgets = budgets.select_related('category').order_by('-month', 'category__name')

    return render(
        request,
        'core/budget_list.html',
        {
            'form': form,
            'budgets': budgets,
            'current_month': current_month,
            'last_month': last_month,
            'is_family': family is not None,
            'no_permission': False,
        },
    )


@login_required
def budget_delete(request, pk):
    budget = get_object_or_404(Budget, pk=pk)
    family = get_user_family(request)

    if family:
        if budget.family_id != family.id:
            messages.error(request, 'Вы не можете удалить бюджет другой семьи.')
            return redirect('budget_list')
        if not request.user.has_perm('core.can_set_budget'):
            messages.error(request, 'У вас нет прав на удаление бюджетов.')
            return redirect('budget_list')
    else:
        if budget.user_id != request.user.id:
            messages.error(request, 'Вы не можете удалить чужой бюджет.')
            return redirect('budget_list')

    if request.method == 'POST':
        category_name = budget.category.name
        month_label = budget.month.strftime('%Y-%m')
        budget.delete()
        messages.success(
            request,
            f'Бюджет "{category_name}" за {month_label} успешно удалён.',
        )
        return redirect('budget_list')

    return render(request, 'core/budget_confirm_delete.html', {'budget': budget})


@login_required
def reports_view(request):
    family = get_user_family(request)
    if not _can_manage_family_reports(request.user, family):
        messages.error(request, 'У вас нет прав на просмотр семейных отчётов.')
        return redirect('family_dashboard')

    today = timezone.localdate()
    year, month = today.year, today.month

    if family:
        summary = get_monthly_summary(family=family, year=year, month=month)
        expense_data = get_expense_breakdown_by_category(
            family=family,
            year=year,
            month=month,
        )
        budget_comparison = get_budget_vs_actual(family=family, year=year, month=month)
    else:
        summary = get_monthly_summary(user=request.user, year=year, month=month)
        expense_data = get_expense_breakdown_by_category(
            user=request.user,
            year=year,
            month=month,
        )
        budget_comparison = get_budget_vs_actual(user=request.user, year=year, month=month)

    labels = [item['category__name'] for item in expense_data]
    values = [float(item['total']) for item in expense_data]

    return render(
        request,
        'core/reports.html',
        {
            'labels': labels,
            'values': values,
            'summary': summary,
            'expense_data': expense_data,
            'budget_comparison': budget_comparison,
            'current_month': f'{today.month:02d}.{year}',
            'is_family': family is not None,
            'has_any_expenses': bool(values),
        },
    )


@login_required
def export_csv(request):
    family = get_user_family(request)
    if not _can_import_export(request.user, family):
        raise PermissionDenied('У вас нет прав на экспорт данных.')

    transactions = (
        Transaction.objects.filter(user__familymember__family=family)
        if family
        else Transaction.objects.filter(user=request.user)
    )
    if not transactions.exists():
        messages.warning(
            request,
            'У вас нет транзакций для экспорта. Сначала добавьте данные.',
        )
        return redirect('transaction_list')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="transactions.csv"'
    export_transactions_to_csv(response, request.user, family=family)
    return response


@login_required
def import_csv(request):
    family = get_user_family(request)
    if not _can_import_export(request.user, family):
        raise PermissionDenied('У вас нет прав на импорт данных.')

    has_transactions = (
        Transaction.objects.filter(user__familymember__family=family).exists()
        if family
        else Transaction.objects.filter(user=request.user).exists()
    )

    if request.method == 'POST':
        csv_file = request.FILES.get('csv_file')
        if not csv_file:
            messages.error(request, 'Файл не выбран.')
            return render(
                request,
                'core/import_csv.html',
                {'has_transactions': has_transactions},
            )
        if not csv_file.name.lower().endswith('.csv'):
            messages.error(request, 'Разрешены только CSV-файлы.')
            return render(
                request,
                'core/import_csv.html',
                {'has_transactions': has_transactions},
            )
        try:
            count = import_transactions_from_csv(csv_file, request.user)
        except ValidationError as exc:
            messages.error(request, ' '.join(exc.messages))
            return render(
                request,
                'core/import_csv.html',
                {'has_transactions': has_transactions},
            )
        except Exception as exc:
            messages.error(request, f'Ошибка при импорте: {exc}')
            return render(
                request,
                'core/import_csv.html',
                {'has_transactions': has_transactions},
            )

        if count == 0:
            messages.warning(
                request,
                'Файл пуст или не содержит корректных данных.',
            )
        else:
            messages.success(request, f'Успешно импортировано {count} транзакций.')
        return redirect('transaction_list')

    return render(request, 'core/import_csv.html', {'has_transactions': has_transactions})


@login_required
def transaction_delete(request, pk):
    transaction = get_object_or_404(Transaction, pk=pk)
    family = get_user_family(request)

    if family:
        if not FamilyMember.objects.filter(user=transaction.user, family=family).exists():
            messages.error(request, 'Вы не можете удалить транзакцию вне вашей семьи.')
            return redirect('transaction_list')
        can_delete = request.user.has_perm(
            'core.can_delete_any_transaction'
        ) or transaction.user_id == request.user.id
    else:
        can_delete = transaction.user_id == request.user.id

    if not can_delete:
        messages.error(request, 'Вы не можете удалить эту транзакцию.')
        return redirect('transaction_list')

    if request.method == 'POST':
        transaction.delete()
        messages.success(request, 'Транзакция удалена.')
        return redirect('transaction_list')

    return render(request, 'core/transaction_confirm_delete.html', {'transaction': transaction})


@login_required
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    family = get_user_family(request)

    if family:
        if category.family_id != family.id:
            messages.error(request, 'Вы не можете удалить категорию другой семьи.')
            return redirect('transaction_create')
        if not request.user.has_perm('core.delete_category'):
            messages.error(request, 'У вас нет прав на удаление категорий.')
            return redirect('transaction_create')
    else:
        if category.user_id != request.user.id:
            messages.error(request, 'Вы не можете удалить чужую категорию.')
            return redirect('transaction_create')

    if Transaction.objects.filter(category=category).exists():
        messages.error(
            request,
            'Нельзя удалить категорию, к которой привязаны транзакции.',
        )
        return redirect('transaction_create')

    if request.method == 'POST':
        category_name = category.name
        category.delete()
        messages.success(request, f'Категория "{category_name}" успешно удалена.')
        return redirect('transaction_create')

    return render(request, 'core/category_confirm_delete.html', {'category': category})
