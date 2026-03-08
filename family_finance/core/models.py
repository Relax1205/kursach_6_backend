from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone

class Family(models.Model):
    """Семья/Домохозяйство для объединения пользователей."""
    name = models.CharField('Название семьи', max_length=100, default='Моя семья')
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        verbose_name = 'Семья'
        verbose_name_plural = 'Семьи'
        permissions = [
            ('can_manage_family', 'Может управлять составом семьи'),
            ('can_view_family_reports', 'Может просматривать общие отчеты семьи'),
        ]
    
    def __str__(self):
        return self.name

class FamilyMember(models.Model):
    """Связь пользователя с семьей."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    family = models.ForeignKey(Family, on_delete=models.CASCADE, verbose_name='Семья', related_name='members')
    joined_at = models.DateTimeField(default=timezone.now)
    is_head = models.BooleanField('Глава семьи', default=False)
    
    class Meta:
        verbose_name = 'Член семьи'
        verbose_name_plural = 'Члены семьи'
    
    def __str__(self):
        return f"{self.user.username} ({self.family.name})"

class Category(models.Model):
    """Категория дохода или расхода."""
    INCOME = 'income'
    EXPENSE = 'expense'
    TYPE_CHOICES = [
        (INCOME, 'Доход'),
        (EXPENSE, 'Расход'),
    ]
    name = models.CharField('Название', max_length=100)
    type = models.CharField('Тип', max_length=10, choices=TYPE_CHOICES, default=EXPENSE)
    family = models.ForeignKey(Family, on_delete=models.CASCADE, verbose_name='Семья', related_name='categories', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь', null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    
    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
    
    def __str__(self):
        return f"{self.name} ({self.get_type_display()})"

class Transaction(models.Model):
    """Финансовая транзакция: доход или расход."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь')
    amount = models.DecimalField('Сумма', max_digits=12, decimal_places=2)
    category = models.ForeignKey(Category, on_delete=models.PROTECT, verbose_name='Категория')
    description = models.CharField('Описание', max_length=255, blank=True)
    date = models.DateField('Дата', default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = 'Транзакция'
        verbose_name_plural = 'Транзакции'
        ordering = ['-date', '-created_at']
        permissions = [
            ('can_delete_any_transaction', 'Может удалять чужие транзакции'),
            ('can_import_export', 'Может импортировать и экспортировать данные'),
        ]
    
    def __str__(self):
        return f"{self.category} — {self.amount} ({self.user.username}, {self.date})"

class Budget(models.Model):
    """Ежемесячный бюджет по категории."""
    family = models.ForeignKey(Family, on_delete=models.CASCADE, verbose_name='Семья', related_name='budgets', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='Пользователь', null=True, blank=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField('Лимит', max_digits=12, decimal_places=2)
    month = models.DateField('Месяц', help_text='Укажите первый день месяца (напр., 2025-10-01)')
    
    class Meta:
        verbose_name = 'Бюджет'
        verbose_name_plural = 'Бюджеты'
        permissions = [
            ('can_set_budget', 'Может устанавливать лимиты бюджета'),
        ]
    
    def __str__(self):
        return f"{self.category} — {self.amount} ({self.month.strftime('%Y-%m')})"