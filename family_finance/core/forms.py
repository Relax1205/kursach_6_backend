# core/forms.py
from django import forms
from django.contrib.auth.models import User
from .models import Transaction, Category, Budget, FamilyMember
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
    # Переопределяем поле как CharField для корректной обработки input type="month"
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
        
        # Проверяем формат YYYY-MM
        if not re.match(r'^\d{4}-\d{2}$', month_value):
            raise ValidationError('Введите месяц в формате ГГГГ-ММ (например, 2026-03).')
        
        try:
            year, month = map(int, month_value.split('-'))
            # Проверяем корректность месяца
            if month < 1 or month > 12:
                raise ValidationError('Месяц должен быть от 01 до 12.')
            # Возвращаем дату (первое число месяца)
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