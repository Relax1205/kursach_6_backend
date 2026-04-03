# tests/conftest.py
import os
import pytest
from decimal import Decimal
from datetime import date
from django.contrib.auth.models import User, Group
from django.test import Client

# Добавляем проект в PYTHONPATH
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'family_finance.settings')

from core.models import Family, FamilyMember, Category, Transaction, Budget

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
    return Family.objects.create(name='Тестовая семья')

@pytest.fixture
def family_head(family, db):
    u = User.objects.create_user(username='head_user', password='headpass123')
    FamilyMember.objects.create(user=u, family=family, is_head=True)
    try:
        g = Group.objects.get(name='Глава семьи')
        u.groups.add(g)
        u.user_permissions.add(*g.permissions.all())
    except Group.DoesNotExist: pass
    return u

@pytest.fixture
def head_client(family_head, db):
    c = Client()
    c.login(username='head_user', password='headpass123')
    return c

@pytest.fixture
def family_member(family, db):
    u = User.objects.create_user(username='member_user', password='memberpass123')
    FamilyMember.objects.create(user=u, family=family, is_head=False)
    try:
        g = Group.objects.get(name='Член семьи')
        u.groups.add(g)
        u.user_permissions.add(*g.permissions.all())
    except Group.DoesNotExist: pass
    return u

@pytest.fixture
def member_client(family_member, db):
    c = Client()
    c.login(username='member_user', password='memberpass123')
    return c

@pytest.fixture
def viewer_user(family, db):
    u = User.objects.create_user(username='viewer_user', password='viewerpass123')
    FamilyMember.objects.create(user=u, family=family, is_head=False)
    try:
        g = Group.objects.get(name='Наблюдатель')
        u.groups.add(g)
        u.user_permissions.add(*g.permissions.all())
    except Group.DoesNotExist: pass
    return u

@pytest.fixture
def viewer_client(viewer_user, db):
    c = Client()
    c.login(username='viewer_user', password='viewerpass123')
    return c

# ================= КАТЕГОРИИ И ТРАНЗАКЦИИ =================
@pytest.fixture
def expense_category(family, db):
    return Category.objects.create(name='Продукты', type=Category.EXPENSE, family=family)

@pytest.fixture
def income_category(family, db):
    return Category.objects.create(name='Зарплата', type=Category.INCOME, family=family)

@pytest.fixture
def personal_category(user, db):
    return Category.objects.create(name='Личные', type=Category.EXPENSE, user=user)

@pytest.fixture
def transaction(user, expense_category, db):
    return Transaction.objects.create(user=user, category=expense_category, amount=Decimal('1000.00'), description='Тест', date=date.today())

@pytest.fixture
def transactions_batch(family, db):
    """Создаёт пакет тестовых транзакций с локальными пользователями."""
    # Создаём пользователей локально для этой фикстуры
    head = User.objects.create_user(username='batch_head', password='pass123')
    member = User.objects.create_user(username='batch_member', password='pass123')
    
    FamilyMember.objects.create(user=head, family=family, is_head=True)
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
    return Budget.objects.create(family=family, category=expense_category, amount=Decimal('10000.00'), month=date(2025, 10, 1))

@pytest.fixture
def full_family_setup(family, family_head, family_member, expense_category, income_category, budget, transactions_batch):
    return {
        'family': family, 'head': family_head, 'member': family_member,
        'expense_category': expense_category, 'income_category': income_category,
        'budget': budget, 'transactions': transactions_batch
    }