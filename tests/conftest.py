# tests/conftest.py
import os
import sys
import pytest
from decimal import Decimal
from datetime import date
from pathlib import Path
from django.contrib.auth.models import User, Group, Permission
from django.test import Client

_HEAD_CORE_PERMS = [
    'add_family', 'change_family', 'delete_family', 'view_family',
    'add_category', 'change_category', 'delete_category', 'view_category',
    'add_transaction', 'change_transaction', 'delete_transaction', 'view_transaction',
    'add_budget', 'change_budget', 'delete_budget', 'view_budget',
    'can_manage_family', 'can_delete_any_transaction', 'can_set_budget', 'can_import_export',
]
_MEMBER_CORE_PERMS = [
    'add_transaction', 'view_transaction', 'view_category',
    'add_budget', 'view_budget', 'can_import_export',
]
_VIEWER_CORE_PERMS = [
    'view_transaction', 'view_category', 'view_budget', 'can_view_family_reports',
]


def _grant_core_permissions(user, codenames):
    perms = list(
        Permission.objects.filter(
            content_type__app_label='core',
            codename__in=codenames,
        )
    )
    if perms:
        user.user_permissions.add(*perms)

# Добавляем проект в PYTHONPATH
ROOT_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = ROOT_DIR / 'family_finance'
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'family_finance.settings')
os.environ.setdefault('DEBUG', 'True')
os.environ.setdefault('SECRET_KEY', 'test-secret-key-for-testing')


def _core_models():
    from core.models import Budget, Category, Family, FamilyMember, Transaction

    return {
        'Budget': Budget,
        'Category': Category,
        'Family': Family,
        'FamilyMember': FamilyMember,
        'Transaction': Transaction,
    }

# ================= УЧЕТНЫЕ ЗАПИСИ =================
@pytest.fixture
def user(db):
    return User.objects.create_user(username='testuser', email='test@test.com', password='testpass123')

@pytest.fixture
def authenticated_client(user, db):
    c = Client()
    c.login(username='testuser', password='testpass123')
    return c

@pytest.fixture
def anonymous_client():
    return Client()

# ================= СЕМЬЯ И РОЛИ =================
@pytest.fixture
def family(db):
    return _core_models()['Family'].objects.create(name='Тестовая семья')

@pytest.fixture
def family_head(family, db):
    FamilyMember = _core_models()['FamilyMember']
    u = User.objects.create_user(username='head_user', password='headpass123')
    FamilyMember.objects.create(user=u, family=family, is_head=True)
    try:
        g = Group.objects.get(name='Глава семьи')
        u.groups.add(g)
    except Group.DoesNotExist:
        pass
    _grant_core_permissions(u, _HEAD_CORE_PERMS)
    return u

@pytest.fixture
def head_client(family_head, db):
    c = Client()
    c.login(username='head_user', password='headpass123')
    return c

@pytest.fixture
def family_member(family, db):
    FamilyMember = _core_models()['FamilyMember']
    u = User.objects.create_user(username='member_user', password='memberpass123')
    FamilyMember.objects.create(user=u, family=family, is_head=False)
    try:
        g = Group.objects.get(name='Член семьи')
        u.groups.add(g)
    except Group.DoesNotExist:
        pass
    _grant_core_permissions(u, _MEMBER_CORE_PERMS)
    return u

@pytest.fixture
def member_client(family_member, db):
    c = Client()
    c.login(username='member_user', password='memberpass123')
    return c

@pytest.fixture
def viewer_user(family, db):
    FamilyMember = _core_models()['FamilyMember']
    u = User.objects.create_user(username='viewer_user', password='viewerpass123')
    FamilyMember.objects.create(user=u, family=family, is_head=False)
    try:
        g = Group.objects.get(name='Наблюдатель')
        u.groups.add(g)
    except Group.DoesNotExist:
        pass
    _grant_core_permissions(u, _VIEWER_CORE_PERMS)
    return u

@pytest.fixture
def viewer_client(viewer_user, db):
    c = Client()
    c.login(username='viewer_user', password='viewerpass123')
    return c

# ================= КАТЕГОРИИ И ТРАНЗАКЦИИ =================
@pytest.fixture
def expense_category(family, db):
    Category = _core_models()['Category']
    return Category.objects.create(name='Продукты', type=Category.EXPENSE, family=family)

@pytest.fixture
def income_category(family, db):
    Category = _core_models()['Category']
    return Category.objects.create(name='Зарплата', type=Category.INCOME, family=family)

@pytest.fixture
def personal_category(user, db):
    Category = _core_models()['Category']
    return Category.objects.create(name='Личные', type=Category.EXPENSE, user=user)

@pytest.fixture
def transaction(user, expense_category, db):
    Transaction = _core_models()['Transaction']
    return Transaction.objects.create(
        user=user,
        category=expense_category,
        amount=Decimal('1000.00'),
        description='Тест',
        date=date.today(),
    )

@pytest.fixture
def transactions_batch(family, db):
    """Создаёт пакет тестовых транзакций с локальными пользователями."""
    models = _core_models()
    FamilyMember = models['FamilyMember']
    Category = models['Category']
    Transaction = models['Transaction']

    # Создаём пользователей локально для этой фикстуры
    head = User.objects.create_user(username='batch_head', password='pass123')
    member = User.objects.create_user(username='batch_member', password='pass123')
    
    FamilyMember.objects.create(user=head, family=family, is_head=False)
    FamilyMember.objects.create(user=member, family=family, is_head=False)
    
    cat_exp = Category.objects.create(name='Продукты', type=Category.EXPENSE, family=family)
    cat_inc = Category.objects.create(name='Зарплата', type=Category.INCOME, family=family)
    
    txs = []
    for i in range(10):
        txs.append(Transaction.objects.create(
            user=head if i % 2 == 0 else member,
            category=cat_exp,
            amount=Decimal('1000.00'),
            description=f'Расход {i+1}',
            date=date(2025, 10, 15)
        ))
    txs.append(Transaction.objects.create(
        user=head,
        category=cat_inc,
        amount=Decimal('50000.00'),
        date=date(2025, 10, 1)
    ))
    return txs
    
@pytest.fixture
def budget(family, expense_category, db):
    Budget = _core_models()['Budget']
    return Budget.objects.create(
        family=family,
        category=expense_category,
        amount=Decimal('10000.00'),
        month=date(2025, 10, 1),
    )

@pytest.fixture
def full_family_setup(family, family_head, family_member, expense_category, income_category, budget, transactions_batch):
    return {
        'family': family, 'head': family_head, 'member': family_member,
        'expense_category': expense_category, 'income_category': income_category,
        'budget': budget, 'transactions': transactions_batch
    }

def pytest_configure(config):
    """
    Выполняется при инициализации pytest.
    Переопределяет настройки Django для тестовой среды.
    """
    from django.conf import settings
    settings.USE_I18N = False
    settings.USE_L10N = False
    settings.LANGUAGE_CODE = 'en'
