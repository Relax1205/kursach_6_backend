import pytest
from django.urls import reverse
from datetime import date

@pytest.mark.django_db
@pytest.mark.integration
class TestFullScenarios:
    def test_full_family_workflow(self, anonymous_client):
        # 1. Регистрация
        anonymous_client.post(reverse('register'), {'username': 'ivanov', 'email': 'i@t.com', 'password1': 'Test1234!', 'password2': 'Test1234!'})
        
        # 2. Создание семьи и категории
        resp = anonymous_client.post(reverse('family_create'), {'name': 'Ивановы'})
        assert resp.status_code == 302
        
        resp = anonymous_client.post(reverse('category_create'), {'name': 'Еда', 'type': 'expense'})
        assert resp.status_code == 302
        
        # 3. Транзакция
        from core.models import Category
        cat = Category.objects.get(name='Еда')
        resp = anonymous_client.post(reverse('transaction_create'), {'amount': 500, 'category': cat.id, 'date': date.today()})
        assert resp.status_code == 302

    def test_csv_roundtrip(self, member_client, transactions_batch):
        # Экспорт
        exp = member_client.get(reverse('export_csv'))
        assert exp.status_code == 200
        data = exp.content
        
        # Очистка и импорт
        from core.models import Transaction
        Transaction.objects.all().delete()
        
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_f = SimpleUploadedFile("round.csv", data, content_type="text/csv")
        imp = member_client.post(reverse('import_csv'), {'csv_file': csv_f})
        assert imp.status_code == 302
        assert Transaction.objects.count() == 11