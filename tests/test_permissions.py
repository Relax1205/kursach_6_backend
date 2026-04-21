import pytest
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.models import Budget, Category, FamilyMember, Transaction

@pytest.mark.django_db
class TestRolePermissions:
    def test_head_can_manage_family(self, head_client):
        assert head_client.get(reverse('family_members')).status_code == 200
        assert head_client.get(reverse('family_members')).context['is_head'] is True

    def test_member_cannot_manage_family(self, member_client, family):
        resp = member_client.post(reverse('family_members'), {'username': 'fake', 'role': 'member'})
        assert resp.status_code == 302  # Редирект с ошибкой

    def test_transfer_head_strips_old_head_permissions(self, head_client, family_head, family_member):
        """После назначения другого главы бывший глава теряет can_manage_family и группу главы."""
        fm_new = FamilyMember.objects.get(user=family_member)
        resp = head_client.post(
            reverse('family_member_role', kwargs={'member_id': fm_new.pk}),
            {'role': 'head'},
        )
        assert resp.status_code == 302
        family_head.refresh_from_db()
        assert not family_head.has_perm('core.can_manage_family')
        assert not family_head.groups.filter(name='Глава семьи').exists()
        assert family_head.groups.filter(name='Наблюдатель').exists()
        fm_new.refresh_from_db()
        assert fm_new.is_head is True

    def test_viewer_cannot_export(self, viewer_client):
        assert viewer_client.get(reverse('export_csv')).status_code == 403

    def test_viewer_cannot_set_budget(self, viewer_client):
        resp = viewer_client.get(reverse('budget_list'))
        assert resp.context['no_permission'] is True

    def test_member_cannot_set_budget(self, member_client):
        """У «Член семьи» в миграции нет can_set_budget — только add/view budget."""
        resp = member_client.get(reverse('budget_list'))
        assert resp.context['no_permission'] is True

    def test_head_cannot_demote_self(self, head_client, family_head):
        head_member = FamilyMember.objects.get(user=family_head)

        resp = head_client.post(
            reverse('family_member_role', kwargs={'member_id': head_member.pk}),
            {'role': 'member'},
        )

        assert resp.status_code == 302
        head_member.refresh_from_db()
        family_head.refresh_from_db()
        assert head_member.is_head is True
        assert FamilyMember.objects.filter(family=head_member.family, is_head=True).count() == 1
        assert family_head.has_perm('core.can_manage_family')

    def test_member_cannot_open_family_invite_page(self, member_client):
        resp = member_client.get(reverse('family_invite'))

        assert resp.status_code == 302
        assert resp.url == reverse('family_members')

    def test_member_cannot_open_role_update_page(self, member_client, family_member):
        member = FamilyMember.objects.get(user=family_member)

        resp = member_client.get(
            reverse('family_member_role', kwargs={'member_id': member.pk})
        )

        assert resp.status_code == 302
        assert resp.url == reverse('family_members')

    def test_member_cannot_view_family_reports(self, member_client):
        resp = member_client.get(reverse('reports'))

        assert resp.status_code == 302
        assert resp.url == reverse('family_dashboard')

    def test_viewer_cannot_import_csv(self, viewer_client):
        assert viewer_client.get(reverse('import_csv')).status_code == 403

    def test_viewer_cannot_create_transaction(self, viewer_client, expense_category):
        resp = viewer_client.post(
            reverse('transaction_create'),
            {
                'amount': '200.00',
                'category': expense_category.pk,
                'description': 'Нельзя создать',
                'date': '2025-10-05',
            },
        )

        assert resp.status_code == 302
        assert not Transaction.objects.filter(description='Нельзя создать').exists()

    def test_viewer_cannot_create_category(self, viewer_client):
        resp = viewer_client.post(
            reverse('category_create'),
            {'name': 'Новая категория', 'type': 'expense'},
        )

        assert resp.status_code == 302
        assert not Category.objects.filter(name='Новая категория').exists()

    def test_member_cannot_delete_budget(self, member_client, budget):
        resp = member_client.post(reverse('budget_delete', kwargs={'pk': budget.pk}))

        assert resp.status_code == 302
        assert Budget.objects.filter(pk=budget.pk).exists()

    def test_member_cannot_delete_other_users_transaction(
        self, member_client, family_head, expense_category
    ):
        transaction = Transaction.objects.create(
            user=family_head,
            category=expense_category,
            amount=Decimal('700.00'),
            description='Чужая для удаления',
            date=date(2025, 10, 3),
        )

        resp = member_client.post(
            reverse('transaction_delete', kwargs={'pk': transaction.pk})
        )

        assert resp.status_code == 302
        assert Transaction.objects.filter(pk=transaction.pk).exists()

    def test_member_cannot_delete_category(self, member_client, family):
        category = Category.objects.create(
            name='Недоступная категория',
            type=Category.EXPENSE,
            family=family,
        )

        resp = member_client.post(reverse('category_delete', kwargs={'pk': category.pk}))

        assert resp.status_code == 302
        assert Category.objects.filter(pk=category.pk).exists()

    def test_head_cannot_leave_family(self, head_client, family_head):
        resp = head_client.post(reverse('family_leave'))

        assert resp.status_code == 302
        assert resp.url == reverse('family_members')
        assert FamilyMember.objects.filter(user=family_head, is_head=True).exists()

    def test_viewer_cannot_import_other_file_types_even_with_upload(self, viewer_client):
        invalid_file = SimpleUploadedFile(
            'budget.csv',
            b'Date,Type,Category,Amount\n2025-10-01,expense,Food,100',
            content_type='text/csv',
        )

        assert viewer_client.post(
            reverse('import_csv'),
            {'csv_file': invalid_file},
        ).status_code == 403
