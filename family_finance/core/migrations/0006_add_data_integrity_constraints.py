# Generated manually to restore data integrity constraints.

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_auto_20260328_1451'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='familymember',
            constraint=models.UniqueConstraint(
                fields=('family',),
                condition=Q(is_head=True),
                name='unique_family_head',
            ),
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.CheckConstraint(
                check=(
                    (Q(family__isnull=False) & Q(user__isnull=True))
                    | (Q(family__isnull=True) & Q(user__isnull=False))
                ),
                name='category_has_single_owner',
            ),
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                fields=('family', 'name', 'type'),
                condition=Q(family__isnull=False),
                name='unique_family_category',
            ),
        ),
        migrations.AddConstraint(
            model_name='category',
            constraint=models.UniqueConstraint(
                fields=('user', 'name', 'type'),
                condition=Q(user__isnull=False),
                name='unique_user_category',
            ),
        ),
        migrations.AddConstraint(
            model_name='budget',
            constraint=models.CheckConstraint(
                check=(
                    (Q(family__isnull=False) & Q(user__isnull=True))
                    | (Q(family__isnull=True) & Q(user__isnull=False))
                ),
                name='budget_has_single_owner',
            ),
        ),
        migrations.AddConstraint(
            model_name='budget',
            constraint=models.UniqueConstraint(
                fields=('family', 'category', 'month'),
                condition=Q(family__isnull=False),
                name='unique_family_budget',
            ),
        ),
        migrations.AddConstraint(
            model_name='budget',
            constraint=models.UniqueConstraint(
                fields=('user', 'category', 'month'),
                condition=Q(user__isnull=False),
                name='unique_user_budget',
            ),
        ),
    ]
