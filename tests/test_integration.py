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
        # Экспорт (колонки с именем пользователя — формат представления)
        exp = member_client.get(reverse('export_csv'))
        assert exp.status_code == 200

        from core.models import Transaction
        Transaction.objects.all().delete()

        # Импорт ожидает формат: Дата, Тип, Категория, Сумма, Описание (см. import_transactions_from_csv)
        rows = ['Дата,Тип,Категория,Сумма,Описание']
        for i in range(11):
            rows.append(f'2025-10-15,Расход,Продукты,1000.00,Импорт {i + 1}')
        body = '\n'.join(rows).encode('utf-8')

        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_f = SimpleUploadedFile('round.csv', body, content_type='text/csv')
        imp = member_client.post(reverse('import_csv'), {'csv_file': csv_f})
        assert imp.status_code == 302
        assert Transaction.objects.count() == 11