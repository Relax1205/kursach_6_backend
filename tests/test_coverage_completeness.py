import importlib
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.apps import apps as django_apps
from django.contrib.auth.models import Group, Permission, User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.paginator import EmptyPage, Paginator as DjangoPaginator
from django.urls import reverse

from core import admin as core_admin
from core.context_processors import family_context
from core.forms import (
    BudgetForm,
    CategoryForm,
    FamilyCreateForm,
    FamilyMemberAddForm,
    FamilyMemberInviteForm,
    UserRegistrationForm,
)
from core.models import Budget, Category, Family, FamilyMember, Transaction
from core.roles import ROLE_GROUP_NAMES, assign_family_role
from core.services import (
    export_transactions_to_csv,
    get_budget_status,
    get_budget_vs_actual,
    import_transactions_from_csv,
)


def _csv_upload(content, name="transactions.csv"):
    return SimpleUploadedFile(name, content.encode("utf-8"), content_type="text/csv")


@pytest.mark.django_db
class TestCoverageSupportCode:
    def test_admin_default_groups_are_created_with_permissions(self):
        Group.objects.filter(name__in=ROLE_GROUP_NAMES.values()).delete()

        core_admin.create_default_groups()

        head_group = Group.objects.get(name=ROLE_GROUP_NAMES["head"])
        member_group = Group.objects.get(name=ROLE_GROUP_NAMES["member"])
        viewer_group = Group.objects.get(name=ROLE_GROUP_NAMES["viewer"])
        assert head_group.permissions.filter(codename="can_manage_family").exists()
        assert member_group.permissions.filter(codename="can_import_export").exists()
        assert viewer_group.permissions.filter(
            codename="can_view_family_reports"
        ).exists()

    def test_migration_remove_default_groups(self):
        Group.objects.get_or_create(name=ROLE_GROUP_NAMES["head"])
        Group.objects.get_or_create(name=ROLE_GROUP_NAMES["member"])
        Group.objects.get_or_create(name=ROLE_GROUP_NAMES["viewer"])

        migration_module = importlib.import_module(
            "core.migrations.0004_create_default_groups"
        )

        class AppsProxy:
            def get_model(self, app_label, model_name):
                return django_apps.get_model(app_label, model_name)

        migration_module.remove_default_groups(AppsProxy(), None)

        assert not Group.objects.filter(name__in=ROLE_GROUP_NAMES.values()).exists()

    def test_context_processor_for_authenticated_user_without_family(self, user):
        request = type("Request", (), {"user": user})()

        context = family_context(request)

        assert context == {
            "is_family": False,
            "family": None,
            "is_head": False,
            "can_manage": False,
            "family_role": None,
        }

    def test_unknown_family_role_is_rejected(self, family_member):
        member = FamilyMember.objects.get(user=family_member)

        with pytest.raises(ValueError):
            assign_family_role(member, "unknown")


@pytest.mark.django_db
class TestCoverageForms:
    def test_personal_transaction_form_uses_personal_categories(
        self, user, personal_category
    ):
        form = __import__("core.forms", fromlist=["TransactionForm"]).TransactionForm(
            {
                "amount": "10.00",
                "category": personal_category.id,
                "description": "",
                "date": "2026-05-10",
            },
            user=user,
        )

        assert form.is_valid(), form.errors

    def test_personal_category_form_sets_user_and_detects_duplicate(
        self, user, personal_category
    ):
        form = CategoryForm(
            {"name": "  New personal  ", "type": Category.INCOME}, user=user
        )
        assert form.is_valid(), form.errors
        category = form.save(commit=False)
        assert category.user == user
        assert category.family is None
        assert form.cleaned_data["name"] == "New personal"

        duplicate = CategoryForm(
            {"name": personal_category.name, "type": personal_category.type},
            user=user,
        )
        assert not duplicate.is_valid()

    def test_category_form_returns_early_when_required_fields_missing(self, user):
        form = CategoryForm({"name": "", "type": Category.EXPENSE}, user=user)

        assert not form.is_valid()
        assert "name" in form.errors

    def test_personal_budget_form_sets_user_and_validates_edge_cases(
        self, user, personal_category
    ):
        valid = BudgetForm(
            {"category": personal_category.id, "amount": "42.00", "month": "2026-05"},
            user=user,
        )
        assert valid.is_valid(), valid.errors
        budget = valid.save(commit=False)
        assert budget.user == user
        assert budget.family is None

        empty_month = BudgetForm(
            {"category": personal_category.id, "amount": "42.00", "month": ""},
            user=user,
        )
        assert not empty_month.is_valid()

        bad_month_number = BudgetForm(
            {"category": personal_category.id, "amount": "42.00", "month": "2026-13"},
            user=user,
        )
        assert not bad_month_number.is_valid()

        bad_year = BudgetForm(
            {"category": personal_category.id, "amount": "42.00", "month": "0000-01"},
            user=user,
        )
        assert not bad_year.is_valid()

        bad_amount = BudgetForm(
            {"category": personal_category.id, "amount": "-1.00", "month": "2026-05"},
            user=user,
        )
        assert not bad_amount.is_valid()

        valid.cleaned_data = {"month": ""}
        with pytest.raises(ValidationError):
            valid.clean_month()

    def test_family_create_form_strips_name(self):
        form = FamilyCreateForm({"name": "  Smiths  "})

        assert form.is_valid(), form.errors
        assert form.cleaned_data["name"] == "Smiths"

    def test_family_member_add_form_allows_user_without_family(self, family_head):
        target = User.objects.create_user(username="outside_user", password="pass12345")
        form = FamilyMemberAddForm(
            {"username": target.username, "role": "member"},
            request_user=family_head,
        )

        assert form.is_valid(), form.errors
        assert form.get_target_user() == target

    def test_family_member_add_form_limits_roles_and_validates_missing_user(
        self, family_member
    ):
        form = FamilyMemberAddForm(
            {"username": "missing_user", "role": "member"},
            request_user=family_member,
        )

        assert [choice[0] for choice in form.fields["role"].choices] == [
            "member",
            "viewer",
        ]
        assert not form.is_valid()

    def test_family_member_add_form_rejects_user_from_another_family(self, family_head):
        other_family = Family.objects.create(name="Other")
        other_user = User.objects.create_user(
            username="other_member", password="pass12345"
        )
        FamilyMember.objects.create(user=other_user, family=other_family)

        form = FamilyMemberAddForm(
            {"username": other_user.username, "role": "member"},
            request_user=family_head,
        )

        assert not form.is_valid()

    def test_registration_and_invite_forms_detect_duplicates_and_password_mismatch(
        self, user
    ):
        registration = UserRegistrationForm(
            {
                "username": "another_user",
                "email": user.email,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
            }
        )
        assert not registration.is_valid()

        duplicate_invite = FamilyMemberInviteForm(
            {
                "username": user.username,
                "email": "unique@example.com",
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "role": "member",
            }
        )
        assert not duplicate_invite.is_valid()

        email_invite = FamilyMemberInviteForm(
            {
                "username": "unique_invite",
                "email": user.email,
                "password1": "StrongPass123!",
                "password2": "StrongPass123!",
                "role": "member",
            }
        )
        assert not email_invite.is_valid()

        mismatch_invite = FamilyMemberInviteForm(
            {
                "username": "mismatch_invite",
                "email": "mismatch@example.com",
                "password1": "StrongPass123!",
                "password2": "OtherPass123!",
                "role": "member",
            }
        )
        assert not mismatch_invite.is_valid()


@pytest.mark.django_db
class TestCoverageModels:
    def test_family_member_rejects_second_head_and_stringifies(self, family):
        first = User.objects.create_user(username="first_head", password="pass12345")
        second = User.objects.create_user(username="second_head", password="pass12345")
        FamilyMember.objects.create(user=first, family=family, is_head=True)

        with pytest.raises(ValidationError):
            FamilyMember.objects.create(user=second, family=family, is_head=True)

        member = FamilyMember.objects.create(user=second, family=family)
        assert str(member) == f"{second.username} ({family.name})"

    def test_category_requires_exactly_one_owner(self, user, family):
        with pytest.raises(ValidationError):
            Category.objects.create(name="Invalid", type=Category.EXPENSE)

        with pytest.raises(ValidationError):
            Category.objects.create(
                name="Invalid",
                type=Category.EXPENSE,
                user=user,
                family=family,
            )

    def test_transaction_validation_branches(
        self, user, family, expense_category, personal_category
    ):
        FamilyMember.objects.create(user=user, family=family)

        with pytest.raises(ValidationError):
            Transaction.objects.create(
                user=user,
                category=expense_category,
                amount=Decimal("-1.00"),
                date=date(2026, 5, 10),
            )

        other_family = Family.objects.create(name="Other")
        other_category = Category.objects.create(
            name="Other food",
            type=Category.EXPENSE,
            family=other_family,
        )
        with pytest.raises(ValidationError):
            Transaction.objects.create(
                user=user,
                category=other_category,
                amount=Decimal("1.00"),
                date=date(2026, 5, 10),
            )

        personal_user = User.objects.create_user(
            username="personal_model_user",
            password="pass12345",
        )
        with pytest.raises(ValidationError):
            Transaction.objects.create(
                user=personal_user,
                category=personal_category,
                amount=Decimal("1.00"),
                date=date(2026, 5, 10),
            )

        transaction = Transaction.objects.create(
            user=user,
            category=expense_category,
            amount=Decimal("2.00"),
            date=date(2026, 5, 10),
        )
        assert str(transaction) == (
            f"{expense_category} - {transaction.amount} ({user.username}, {transaction.date})"
        ).replace(" - ", " — ")

    def test_budget_validation_branches(self, user, family, expense_category):
        income = Category.objects.create(
            name="Salary", type=Category.INCOME, family=family
        )
        personal_expense = Category.objects.create(
            name="Personal expense",
            type=Category.EXPENSE,
            user=user,
        )

        with pytest.raises(ValidationError):
            Budget.objects.create(
                category=expense_category,
                amount=Decimal("1.00"),
                month=date(2026, 5, 1),
            )

        with pytest.raises(ValidationError):
            Budget.objects.create(
                family=family,
                user=user,
                category=expense_category,
                amount=Decimal("1.00"),
                month=date(2026, 5, 1),
            )

        with pytest.raises(ValidationError):
            Budget.objects.create(
                family=family,
                category=expense_category,
                amount=Decimal("-1.00"),
                month=date(2026, 5, 1),
            )

        with pytest.raises(ValidationError):
            Budget.objects.create(
                family=family,
                category=expense_category,
                amount=Decimal("1.00"),
                month=date(2026, 5, 2),
            )

        no_category_budget = Budget(
            family=family,
            amount=Decimal("1.00"),
            month=date(2026, 5, 1),
        )
        no_category_budget.clean()

        with pytest.raises(ValidationError):
            Budget.objects.create(
                family=family,
                category=income,
                amount=Decimal("1.00"),
                month=date(2026, 5, 1),
            )

        other_family = Family.objects.create(name="Budget other")
        with pytest.raises(ValidationError):
            Budget.objects.create(
                family=other_family,
                category=expense_category,
                amount=Decimal("1.00"),
                month=date(2026, 5, 1),
            )

        with pytest.raises(ValidationError):
            Budget.objects.create(
                user=user,
                category=expense_category,
                amount=Decimal("1.00"),
                month=date(2026, 5, 1),
            )

        valid = Budget.objects.create(
            user=user,
            category=personal_expense,
            amount=Decimal("1.00"),
            month=date(2026, 5, 1),
        )
        assert "2026-05" in str(valid)


@pytest.mark.django_db
class TestCoverageServices:
    def test_personal_export_budget_comparison_and_status(
        self, user, personal_category
    ):
        Budget.objects.create(
            user=user,
            category=personal_category,
            amount=Decimal("100.00"),
            month=date(2026, 5, 1),
        )
        Transaction.objects.create(
            user=user,
            category=personal_category,
            amount=Decimal("80.00"),
            date=date(2026, 5, 10),
        )

        comparison = get_budget_vs_actual(user=user, year=2026, month=5)
        assert comparison[0]["actual_amount"] == Decimal("80")
        assert comparison[0]["difference"] == Decimal("20.00")

        status = get_budget_status(
            personal_category,
            user=user,
            target_date=date(2026, 5, 15),
        )
        assert status["warning_type"] == "warning"
        assert status["percent_used"] == Decimal("80")

        output = StringIO()
        export_transactions_to_csv(output, user, include_user=False)
        assert "Date" not in output.getvalue()

    def test_import_csv_validation_edges(self, user, family_head):
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload("", "empty.csv"), user)

        missing_headers = "Date,Type,Category\n2026-05-10,expense,Food"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(missing_headers), user)

        missing_required = "Date,Type,Category,Amount\n,expense,Food,1"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(missing_required), user)

        invalid_type = "Date,Type,Category,Amount\n2026-05-10,wrong,Food,1"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(invalid_type), user)

        invalid_amount = "Date,Type,Category,Amount\n2026-05-10,expense,Food,abc"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(invalid_amount), user)

        negative_amount = "Date,Type,Category,Amount\n2026-05-10,expense,Food,-1"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(negative_amount), user)

        invalid_date = "Date,Type,Category,Amount\nbad-date,expense,Food,1"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(invalid_date), user)

        unknown_user = "Date,User,Type,Category,Amount\n2026-05-10,nope,expense,Food,1"
        with pytest.raises(ValidationError):
            import_transactions_from_csv(_csv_upload(unknown_user), family_head)

        with_blank_line = (
            "Date,Type,Category,Amount\n" ",,,\n" "2026-05-10,expense,Food,1"
        )
        assert import_transactions_from_csv(_csv_upload(with_blank_line), user) == 1

        income_row = "Date,Type,Category,Amount\n2026-05-11,income,Salary,100"
        assert import_transactions_from_csv(_csv_upload(income_row), user) == 1


@pytest.mark.django_db
class TestCoverageViews:
    def test_register_authenticated_redirects(self, authenticated_client):
        response = authenticated_client.get(reverse("register"))

        assert response.status_code == 302

    def test_register_get_renders(self, anonymous_client):
        response = anonymous_client.get(reverse("register"))

        assert response.status_code == 200

    def test_register_invalid_post_rerenders(self, anonymous_client):
        response = anonymous_client.post(
            reverse("register"),
            {
                "username": "",
                "email": "bad",
                "password1": "short",
                "password2": "different",
            },
        )

        assert response.status_code == 200

    def test_family_invite_invalid_form_rerenders(self, head_client):
        response = head_client.post(
            reverse("family_invite"),
            {
                "username": "",
                "email": "bad",
                "password1": "StrongPass123!",
                "password2": "OtherPass123!",
                "role": "member",
            },
        )

        assert response.status_code == 200

    def test_family_create_get_and_existing_family_redirect(
        self, authenticated_client, head_client
    ):
        assert authenticated_client.get(reverse("family_create")).status_code == 200
        assert head_client.get(reverse("family_create")).status_code == 302

    def test_family_members_without_family_redirects(self, authenticated_client):
        response = authenticated_client.get(reverse("family_members"))

        assert response.status_code == 302

    def test_family_members_post_adds_and_rejects_members(self, head_client):
        target = User.objects.create_user(
            username="new_family_member", password="pass12345"
        )
        valid = head_client.post(
            reverse("family_members"),
            {"username": target.username, "role": "member"},
        )
        assert valid.status_code == 302
        assert FamilyMember.objects.filter(user=target).exists()

        invalid = head_client.post(
            reverse("family_members"),
            {"username": "missing_member", "role": "member"},
        )
        assert invalid.status_code == 200

    def test_family_member_role_invalid_form_rerenders(
        self, head_client, family_member
    ):
        member = FamilyMember.objects.get(user=family_member)

        response = head_client.post(
            reverse("family_member_role", kwargs={"member_id": member.pk}),
            {"role": "wrong"},
        )

        assert response.status_code == 200

    def test_family_leave_without_family_redirects(self, authenticated_client):
        response = authenticated_client.get(reverse("family_leave"))

        assert response.status_code == 302

    def test_transaction_list_filters_and_invalid_pagination(
        self, head_client, family_head, family_member, expense_category
    ):
        Transaction.objects.create(
            user=family_head,
            category=expense_category,
            amount=Decimal("10.00"),
            date=date(2026, 5, 10),
        )
        Transaction.objects.create(
            user=family_member,
            category=expense_category,
            amount=Decimal("15.00"),
            date=date(2026, 5, 11),
        )

        response = head_client.get(
            reverse("transaction_list"),
            {
                "start_date": "2026-05-01",
                "end_date": "2026-05-31",
                "category": expense_category.id,
                "member": family_member.id,
                "per_page": "999",
            },
        )
        assert response.status_code == 200
        assert response.context["per_page"] == 20

        response = head_client.get(reverse("transaction_list"), {"per_page": "bad"})
        assert response.status_code == 200
        assert response.context["per_page"] == 20

    def test_transaction_list_handles_paginator_exception(
        self, monkeypatch, head_client
    ):
        class RaisingPaginator(DjangoPaginator):
            def get_page(self, number):
                if number == "bad":
                    raise EmptyPage("bad")
                return super().get_page(number)

        monkeypatch.setattr("core.views.Paginator", RaisingPaginator)

        response = head_client.get(reverse("transaction_list"), {"page": "bad"})

        assert response.status_code == 200

    def test_transaction_create_warns_at_eighty_percent(
        self, head_client, family_head, expense_category
    ):
        Budget.objects.create(
            family=FamilyMember.objects.get(user=family_head).family,
            category=expense_category,
            amount=Decimal("100.00"),
            month=date(2026, 5, 1),
        )
        Transaction.objects.create(
            user=family_head,
            category=expense_category,
            amount=Decimal("70.00"),
            date=date(2026, 5, 1),
        )

        response = head_client.post(
            reverse("transaction_create"),
            {
                "amount": "10.00",
                "category": expense_category.id,
                "date": "2026-05-10",
            },
        )

        assert response.status_code == 302

    def test_personal_category_budget_reports_export_and_delete(
        self, authenticated_client, user, personal_category
    ):
        created_category = authenticated_client.post(
            reverse("category_create"),
            {"name": "Personal income", "type": Category.INCOME},
        )
        assert created_category.status_code == 302

        budget_create = authenticated_client.post(
            reverse("budget_list"),
            {
                "category": personal_category.id,
                "amount": "100.00",
                "month": "2026-05",
            },
        )
        assert budget_create.status_code == 302

        budget_update = authenticated_client.post(
            reverse("budget_list"),
            {
                "category": personal_category.id,
                "amount": "120.00",
                "month": "2026-05",
            },
        )
        assert budget_update.status_code == 302

        invalid_budget = authenticated_client.post(
            reverse("budget_list"),
            {"category": personal_category.id, "amount": "-1", "month": "2026-05"},
        )
        assert invalid_budget.status_code == 200

        assert authenticated_client.get(reverse("budget_list")).status_code == 200
        assert authenticated_client.get(reverse("reports")).status_code == 200

        Transaction.objects.create(
            user=user,
            category=personal_category,
            amount=Decimal("1.00"),
            date=date(2026, 5, 10),
        )
        export = authenticated_client.get(reverse("export_csv"))
        assert export.status_code == 200
        assert export["Content-Type"].startswith("text/csv")

        transaction = Transaction.objects.get(user=user, category=personal_category)
        assert (
            authenticated_client.get(
                reverse("transaction_delete", kwargs={"pk": transaction.pk})
            ).status_code
            == 200
        )
        assert (
            authenticated_client.post(
                reverse("transaction_delete", kwargs={"pk": transaction.pk})
            ).status_code
            == 302
        )

    def test_family_budget_post_uses_family_scope(
        self, head_client, family, expense_category
    ):
        response = head_client.post(
            reverse("budget_list"),
            {
                "category": expense_category.id,
                "amount": "55.00",
                "month": "2026-05",
            },
        )

        assert response.status_code == 302
        assert Budget.objects.filter(
            family=family,
            category=expense_category,
            month=date(2026, 5, 1),
            amount=Decimal("55.00"),
        ).exists()

    def test_budget_delete_rejects_wrong_scope_and_missing_permission(
        self,
        head_client,
        member_client,
        authenticated_client,
        user,
        family,
        expense_category,
    ):
        other_family = Family.objects.create(name="Other budget family")
        other_category = Category.objects.create(
            name="Other budget category",
            type=Category.EXPENSE,
            family=other_family,
        )
        other_budget = Budget.objects.create(
            family=other_family,
            category=other_category,
            amount=Decimal("1.00"),
            month=date(2026, 5, 1),
        )
        assert (
            head_client.get(
                reverse("budget_delete", kwargs={"pk": other_budget.pk})
            ).status_code
            == 302
        )

        family_budget = Budget.objects.create(
            family=family,
            category=expense_category,
            amount=Decimal("2.00"),
            month=date(2026, 5, 1),
        )
        assert (
            member_client.get(
                reverse("budget_delete", kwargs={"pk": family_budget.pk})
            ).status_code
            == 302
        )

        owner = User.objects.create_user(username="budget_owner", password="pass12345")
        owner_category = Category.objects.create(
            name="Owner category",
            type=Category.EXPENSE,
            user=owner,
        )
        personal_budget = Budget.objects.create(
            user=owner,
            category=owner_category,
            amount=Decimal("3.00"),
            month=date(2026, 5, 1),
        )
        assert (
            authenticated_client.get(
                reverse("budget_delete", kwargs={"pk": personal_budget.pk})
            ).status_code
            == 302
        )

    def test_import_csv_view_validation_generic_exception_and_zero_count(
        self, monkeypatch, member_client
    ):
        invalid = member_client.post(
            reverse("import_csv"),
            {"csv_file": _csv_upload("Date,Type,Category,Amount\nbad,expense,Food,1")},
        )
        assert invalid.status_code == 200

        def raise_runtime_error(file, user):
            raise RuntimeError("boom")

        monkeypatch.setattr(
            "core.views.import_transactions_from_csv", raise_runtime_error
        )
        generic = member_client.post(
            reverse("import_csv"),
            {
                "csv_file": _csv_upload(
                    "Date,Type,Category,Amount\n2026-05-10,expense,Food,1"
                )
            },
        )
        assert generic.status_code == 200

        monkeypatch.setattr(
            "core.views.import_transactions_from_csv", lambda file, user: 0
        )
        empty = member_client.post(
            reverse("import_csv"),
            {"csv_file": _csv_upload("Date,Type,Category,Amount\n,,,,")},
        )
        assert empty.status_code == 302

    def test_transaction_and_category_delete_reject_wrong_scope(
        self, head_client, authenticated_client, user, family, expense_category
    ):
        other_family = Family.objects.create(name="Other transaction family")
        other_user = User.objects.create_user(
            username="other_tx_user", password="pass12345"
        )
        FamilyMember.objects.create(user=other_user, family=other_family)
        other_category = Category.objects.create(
            name="Other category",
            type=Category.EXPENSE,
            family=other_family,
        )
        other_transaction = Transaction.objects.create(
            user=other_user,
            category=other_category,
            amount=Decimal("1.00"),
            date=date(2026, 5, 10),
        )
        assert (
            head_client.get(
                reverse("transaction_delete", kwargs={"pk": other_transaction.pk})
            ).status_code
            == 302
        )

        other_family_category = Category.objects.create(
            name="Foreign category",
            type=Category.EXPENSE,
            family=other_family,
        )
        assert (
            head_client.get(
                reverse("category_delete", kwargs={"pk": other_family_category.pk})
            ).status_code
            == 302
        )

        owner = User.objects.create_user(
            username="category_owner", password="pass12345"
        )
        owner_category = Category.objects.create(
            name="Owner category",
            type=Category.EXPENSE,
            user=owner,
        )
        assert (
            authenticated_client.get(
                reverse("category_delete", kwargs={"pk": owner_category.pk})
            ).status_code
            == 302
        )
