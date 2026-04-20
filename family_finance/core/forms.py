import re
from datetime import date

from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import Budget, Category, Family, FamilyMember, Transaction
from .roles import get_family_for_user


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
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        family = get_family_for_user(self.user)
        if family:
            queryset = Category.objects.filter(family=family)
        else:
            queryset = Category.objects.filter(user=self.user)
        self.fields['category'].queryset = queryset.order_by('type', 'name')
        self.fields['date'].initial = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data['amount']
        if amount <= 0:
            raise ValidationError('Сумма должна быть положительной.')
        return amount


class CategoryForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = ['name', 'type']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'type': forms.Select(attrs={'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.family = get_family_for_user(self.user)
        if self.family:
            self.instance.family = self.family
            self.instance.user = None
        else:
            self.instance.user = self.user
            self.instance.family = None

    def clean_name(self):
        return self.cleaned_data['name'].strip()

    def clean(self):
        cleaned_data = super().clean()
        name = cleaned_data.get('name')
        category_type = cleaned_data.get('type')
        if not name or not category_type:
            return cleaned_data

        queryset = Category.objects.filter(type=category_type, name__iexact=name)
        if self.family:
            exists = queryset.filter(family=self.family).exists()
        else:
            exists = queryset.filter(user=self.user).exists()
        if exists:
            raise ValidationError('Категория с таким названием и типом уже существует.')
        return cleaned_data


class BudgetForm(forms.ModelForm):
    month = forms.CharField(
        label='Месяц',
        widget=forms.TextInput(attrs={'type': 'month', 'class': 'form-control'}),
    )

    class Meta:
        model = Budget
        fields = ['category', 'amount', 'month']
        widgets = {
            'category': forms.Select(attrs={'class': 'form-control'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.family = get_family_for_user(self.user)
        if self.family:
            queryset = Category.objects.filter(
                family=self.family,
                type=Category.EXPENSE,
            )
            self.instance.family = self.family
            self.instance.user = None
        else:
            queryset = Category.objects.filter(user=self.user, type=Category.EXPENSE)
            self.instance.user = self.user
            self.instance.family = None
        self.fields['category'].queryset = queryset.order_by('name')
        self.fields['month'].initial = timezone.localdate().strftime('%Y-%m')

    def clean_month(self):
        month_value = self.cleaned_data['month']
        if not month_value:
            raise ValidationError('Укажите месяц.')
        if not re.match(r'^\d{4}-\d{2}$', month_value):
            raise ValidationError(
                'Введите месяц в формате ГГГГ-ММ (например, 2026-03).'
            )
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
    member = forms.ChoiceField(
        label='Пользователь',
        choices=[],
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'}),
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        choices = [('all', 'Все пользователи')]
        family = get_family_for_user(user)
        if family:
            for member in family.members.select_related('user').order_by('user__username'):
                choices.append((str(member.user.id), member.user.username))
        self.fields['member'].choices = choices


class FamilyCreateForm(forms.ModelForm):
    class Meta:
        model = Family
        fields = ['name']
        widgets = {
            'name': forms.TextInput(
                attrs={
                    'class': 'form-control',
                    'placeholder': 'Например: Семья Ивановых',
                }
            )
        }

    def clean_name(self):
        return self.cleaned_data['name'].strip()


class FamilyMemberAddForm(forms.Form):
    username = forms.CharField(
        label='Имя пользователя',
        max_length=150,
        widget=forms.TextInput(
            attrs={'class': 'form-control', 'placeholder': 'Логин пользователя'}
        ),
    )
    role = forms.ChoiceField(
        label='Роль в семье',
        choices=[
            ('head', 'Глава семьи'),
            ('member', 'Член семьи'),
            ('viewer', 'Наблюдатель'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def __init__(self, *args, **kwargs):
        self.request_user = kwargs.pop('request_user', None)
        self.target_user = None
        super().__init__(*args, **kwargs)
        if not (self.request_user and self.request_user.has_perm('core.can_manage_family')):
            self.fields['role'].choices = [
                ('member', 'Член семьи'),
                ('viewer', 'Наблюдатель'),
            ]

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        try:
            self.target_user = User.objects.get(username=username)
        except User.DoesNotExist as exc:
            raise ValidationError('Пользователь с таким именем не найден.') from exc

        target_member = FamilyMember.objects.filter(user=self.target_user).first()
        if not target_member:
            return username

        request_member = (
            FamilyMember.objects.filter(user=self.request_user).first()
            if self.request_user
            else None
        )
        if request_member and target_member.family_id == request_member.family_id:
            raise ValidationError('Этот пользователь уже состоит в вашей семье.')
        raise ValidationError('Пользователь уже состоит в другой семье.')

    def get_target_user(self):
        return self.target_user


class FamilyMemberRoleForm(forms.Form):
    role = forms.ChoiceField(
        label='Роль',
        choices=[
            ('head', 'Глава семьи'),
            ('member', 'Член семьи'),
            ('viewer', 'Наблюдатель'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )


class UserRegistrationForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
    )
    username = forms.CharField(
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Логин'}),
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Пароль'}),
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(
            attrs={'class': 'form-control', 'placeholder': 'Подтвердите пароль'}
        ),
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
    username = forms.CharField(
        label='Логин',
        max_length=150,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Придумайте логин'}),
    )
    email = forms.EmailField(
        label='Email',
        required=False,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
    )
    password1 = forms.CharField(
        label='Пароль',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
    password2 = forms.CharField(
        label='Подтверждение пароля',
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
    )
    role = forms.ChoiceField(
        label='Роль в семье',
        choices=[
            ('member', 'Член семьи'),
            ('viewer', 'Наблюдатель'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError('Пользователь с таким логином уже существует.')
        return username

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if email and User.objects.filter(email=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        if password1 and password2 and password1 != password2:
            raise forms.ValidationError('Пароли не совпадают.')
        if password1:
            validate_password(password1)
        return cleaned_data
