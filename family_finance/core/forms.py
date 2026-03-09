# core/forms.py
from django import forms
from django.contrib.auth.models import User, Group
from django.contrib.auth.forms import UserCreationForm
from .models import Transaction, Category, Budget, FamilyMember, Family
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import date
import re

class TransactionForm(forms.ModelForm):
    class Meta:
        model = Transaction
        fields = ['amount', 'category', 'description', 'date']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'category': forms.Select(attrs={'class': 'form-control'}),
            'description': forms.TextInput(attrs={'class': 'form-control'}),
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        try:
            family_member = FamilyMember.objects.get(user=user)
            family = family_member.family
            self.fields['category'].queryset = Category.objects.filter(family=family)
        except FamilyMember.DoesNotExist:
            self.fields['category'].queryset = Category.objects.filter(user=user)

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise ValidationError('Сумма должна быть положительной.')
        return amount

class CategoryForm(forms.ModelForm):
    """Форма для создания категории."""
    class Meta:
        model = Category
        fields = ['name', 'type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-control'}),
        }

class BudgetForm(forms.ModelForm):
    """Форма для установки месячного бюджета."""
    month = forms.CharField(
        label='Месяц',
        widget=forms.TextInput(attrs={'type': 'month', 'class': 'form-control'})
    )

    class Meta:
        model = Budget
        fields = ['category', 'amount', 'month']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        try:
            family_member = FamilyMember.objects.get(user=user)
            family = family_member.family
            self.fields['category'].queryset = Category.objects.filter(family=family, type=Category.EXPENSE)
        except FamilyMember.DoesNotExist:
            self.fields['category'].queryset = Category.objects.filter(user=user, type=Category.EXPENSE)

    def clean_month(self):
        """Преобразуем формат YYYY-MM в дату (первое число месяца)."""
        month_value = self.cleaned_data['month']
        if not month_value:
            raise ValidationError('Укажите месяц.')
        if not re.match(r'^\d{4}-\d{2}$', month_value):
            raise ValidationError('Введите месяц в формате ГГГГ-ММ (например, 2026-03).')
        try:
            year, month = map(int, month_value.split('-'))
            if month < 1 or month > 12:
                raise ValidationError('Месяц должен быть от 01 до 12.')
            return date(year, month, 1)
        except (ValueError, TypeError):
            raise ValidationError('Неверный формат месяца.')

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise ValidationError('Сумма должна быть положительной.')
        return amount

class FamilyMemberFilterForm(forms.Form):
    """Форма для фильтрации транзакций по члену семьи."""
    member = forms.ChoiceField(
        label='Пользователь',
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        choices = [('all', 'Все пользователи')]
        try:
            family_member = FamilyMember.objects.get(user=user)
            family = family_member.family
            for member in family.members.select_related('user').order_by('user__username'):
                choices.append((member.user.id, member.user.username))
        except FamilyMember.DoesNotExist:
            pass
        self.fields['member'].choices = choices

# === ФОРМЫ ДЛЯ УПРАВЛЕНИЯ СЕМЬЕЙ ===

class FamilyCreateForm(forms.ModelForm):
    """Форма для создания новой семьи."""
    class Meta:
        model = Family
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Например: Семья Ивановых'})
        }

class FamilyMemberAddForm(forms.Form):
    """Форма для добавления/приглашения участника в семью."""
    username = forms.CharField(
        label='Имя пользователя',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Логин пользователя'})
    )
    role = forms.ChoiceField(
        label='Роль в семье',
        choices=[
            ('head', 'Глава семьи'),
            ('member', 'Член семьи'),
            ('viewer', 'Наблюдатель')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        super().__init__(*args, **kwargs)
        if not (self.request_user and self.request_user.has_perm('core.can_manage_family')):
            self.fields['role'].choices = [
                ('member', 'Член семьи'),
                ('viewer', 'Наблюдатель')
            ]

    def clean_username(self):
        username = self.cleaned_data['username']
        try:
            user = User.objects.get(username=username)
            if FamilyMember.objects.filter(user=user).exists():
                existing_family = FamilyMember.objects.get(user=user).family
                if self.request_user:
                    try:
                        current_family = FamilyMember.objects.get(user=self.request_user).family
                        if existing_family == current_family:
                            raise ValidationError('Этот пользователь уже состоит в вашей семье.')
                        else:
                            raise ValidationError('Пользователь уже состоит в другой семье.')
                    except FamilyMember.DoesNotExist:
                        pass
        except User.DoesNotExist:
            raise ValidationError('Пользователь с таким именем не найден.')
        return username

class FamilyMemberRoleForm(forms.Form):
    """Форма для изменения роли участника семьи."""
    role = forms.ChoiceField(
        label='Роль',
        choices=[
            ('head', 'Глава семьи'),
            ('member', 'Член семьи'),
            ('viewer', 'Наблюдатель')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )

# === ФОРМЫ РЕГИСТРАЦИИ И ПРИГЛАШЕНИЯ ===

class UserRegistrationForm(UserCreationForm):
    """Форма регистрации нового пользователя."""
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'})
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Логин'})
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Пароль'})
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Подтвердите пароль'})
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].help_text = ''
        self.fields['password2'].help_text = ''

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже зарегистрирован.')
        return email

class FamilyMemberInviteForm(forms.Form):
    """Форма для приглашения нового участника семьи (создание аккаунта главой)."""
    username = forms.CharField(
        label='Логин',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Придумайте логин'})
    )
    email = forms.EmailField(
        label='Email',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'})
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    role = forms.ChoiceField(
        label='Роль в семье',
        choices=[
            ('member', 'Член семьи'),
            ('viewer', 'Наблюдатель')
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Пользователь с таким логином уже существует.')
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Пароли не совпадают.')
        return cleaned_data