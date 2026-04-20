from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Family(models.Model):
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
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь',
    )
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        verbose_name='Семья',
        related_name='members',
    )
    joined_at = models.DateTimeField(default=timezone.now)
    is_head = models.BooleanField('Глава семьи', default=False)

    class Meta:
        verbose_name = 'Член семьи'
        verbose_name_plural = 'Члены семьи'
        constraints = [
            models.UniqueConstraint(
                fields=['family'],
                condition=Q(is_head=True),
                name='unique_family_head',
            ),
        ]

    def clean(self):
        super().clean()
        if (
            self.is_head
            and self.family_id
            and FamilyMember.objects.filter(family=self.family, is_head=True)
            .exclude(pk=self.pk)
            .exists()
        ):
            raise ValidationError({'is_head': 'В семье уже назначен глава.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user.username} ({self.family.name})'


class Category(models.Model):
    INCOME = 'income'
    EXPENSE = 'expense'
    TYPE_CHOICES = [
        (INCOME, 'Доход'),
        (EXPENSE, 'Расход'),
    ]

    name = models.CharField('Название', max_length=100)
    type = models.CharField(
        'Тип',
        max_length=10,
        choices=TYPE_CHOICES,
        default=EXPENSE,
    )
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        verbose_name='Семья',
        related_name='categories',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь',
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(family__isnull=False) & Q(user__isnull=True))
                    | (Q(family__isnull=True) & Q(user__isnull=False))
                ),
                name='category_has_single_owner',
            ),
            models.UniqueConstraint(
                fields=['family', 'name', 'type'],
                condition=Q(family__isnull=False),
                name='unique_family_category',
            ),
            models.UniqueConstraint(
                fields=['user', 'name', 'type'],
                condition=Q(user__isnull=False),
                name='unique_user_category',
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.family_id) == bool(self.user_id):
            raise ValidationError(
                'Категория должна принадлежать либо семье, либо пользователю.'
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.name} ({self.get_type_display()})'


class Transaction(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь',
    )
    amount = models.DecimalField('Сумма', max_digits=12, decimal_places=2)
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        verbose_name='Категория',
    )
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

    def clean(self):
        super().clean()
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Сумма должна быть положительной.'})

        if not self.user_id or not self.category_id:
            return

        family_member = FamilyMember.objects.select_related('family').filter(
            user=self.user
        ).first()

        if family_member:
            if self.category.family_id != family_member.family_id:
                raise ValidationError(
                    {'category': 'Категория должна принадлежать семье пользователя.'}
                )
            return

        if self.category.user_id != self.user_id or self.category.family_id is not None:
            raise ValidationError(
                {'category': 'Личная транзакция может использовать только личную категорию.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.category} — {self.amount} ({self.user.username}, {self.date})'


class Budget(models.Model):
    family = models.ForeignKey(
        Family,
        on_delete=models.CASCADE,
        verbose_name='Семья',
        related_name='budgets',
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь',
        null=True,
        blank=True,
    )
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    amount = models.DecimalField('Лимит', max_digits=12, decimal_places=2)
    month = models.DateField(
        'Месяц',
        help_text='Укажите первый день месяца (напр., 2025-10-01)',
    )

    class Meta:
        verbose_name = 'Бюджет'
        verbose_name_plural = 'Бюджеты'
        permissions = [
            ('can_set_budget', 'Может устанавливать лимиты бюджета'),
        ]
        constraints = [
            models.CheckConstraint(
                check=(
                    (Q(family__isnull=False) & Q(user__isnull=True))
                    | (Q(family__isnull=True) & Q(user__isnull=False))
                ),
                name='budget_has_single_owner',
            ),
            models.UniqueConstraint(
                fields=['family', 'category', 'month'],
                condition=Q(family__isnull=False),
                name='unique_family_budget',
            ),
            models.UniqueConstraint(
                fields=['user', 'category', 'month'],
                condition=Q(user__isnull=False),
                name='unique_user_budget',
            ),
        ]

    def clean(self):
        super().clean()
        if bool(self.family_id) == bool(self.user_id):
            raise ValidationError(
                'Бюджет должен принадлежать либо семье, либо пользователю.'
            )
        if self.amount is not None and self.amount <= 0:
            raise ValidationError({'amount': 'Сумма должна быть положительной.'})
        if self.month and self.month.day != 1:
            raise ValidationError({'month': 'Месяц должен храниться первым днем месяца.'})
        if not self.category_id:
            return
        if self.category.type != Category.EXPENSE:
            raise ValidationError(
                {'category': 'Бюджет можно устанавливать только для расходных категорий.'}
            )
        if self.family_id and self.category.family_id != self.family_id:
            raise ValidationError(
                {'category': 'Категория бюджета должна принадлежать выбранной семье.'}
            )
        if self.user_id and (
            self.category.user_id != self.user_id or self.category.family_id is not None
        ):
            raise ValidationError(
                {'category': 'Личный бюджет может использовать только личную категорию.'}
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.category} — {self.amount} ({self.month.strftime("%Y-%m")})'
