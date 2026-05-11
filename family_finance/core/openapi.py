from copy import deepcopy

from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

HTML_PAGE = {"$ref": "#/components/responses/HtmlPage"}
REDIRECT = {"$ref": "#/components/responses/Redirect"}
LOGIN_REDIRECT = {"$ref": "#/components/responses/LoginRedirect"}
FORBIDDEN = {"$ref": "#/components/responses/Forbidden"}
CSV_FILE = {"$ref": "#/components/responses/CsvFile"}

SESSION_SECURITY = [{"SessionAuth": []}]
SESSION_CSRF_SECURITY = [{"SessionAuth": [], "CSRFToken": []}]
CSRF_SECURITY = [{"CSRFToken": []}]


def _form_request_body(schema_ref, description="HTML-форма Django"):
    return {
        "required": True,
        "description": description,
        "content": {
            "application/x-www-form-urlencoded": {
                "schema": {"$ref": schema_ref},
            },
        },
    }


def _multipart_request_body(schema_ref, description="Multipart-форма Django"):
    return {
        "required": True,
        "description": description,
        "content": {
            "multipart/form-data": {
                "schema": {"$ref": schema_ref},
            },
        },
    }


def _query_parameter(name, schema, description, required=False):
    return {
        "name": name,
        "in": "query",
        "required": required,
        "schema": schema,
        "description": description,
    }


def _path_parameter(name, schema, description):
    return {
        "name": name,
        "in": "path",
        "required": True,
        "schema": schema,
        "description": description,
    }


def _html_get(
    tag,
    operation_id,
    summary,
    description,
    *,
    auth_required=True,
    parameters=None,
):
    responses = {"200": HTML_PAGE}
    if auth_required:
        responses["302"] = LOGIN_REDIRECT
    return {
        "tags": [tag],
        "operationId": operation_id,
        "summary": summary,
        "description": description,
        "parameters": parameters or [],
        "responses": responses,
        **({"security": SESSION_SECURITY} if auth_required else {}),
    }


def _html_post(
    tag,
    operation_id,
    summary,
    description,
    request_body,
    *,
    auth_required=True,
    parameters=None,
    forbidden=False,
):
    responses = {
        "200": HTML_PAGE,
        "302": REDIRECT,
    }
    if auth_required:
        responses["302"] = REDIRECT
    if forbidden:
        responses["403"] = FORBIDDEN

    if auth_required:
        security = SESSION_CSRF_SECURITY
    else:
        security = CSRF_SECURITY

    return {
        "tags": [tag],
        "operationId": operation_id,
        "summary": summary,
        "description": description,
        "parameters": parameters or [],
        "requestBody": request_body,
        "responses": responses,
        "security": security,
    }


OPENAPI_SCHEMA = {
    "openapi": "3.0.3",
    "info": {
        "title": "Family Finance Backend",
        "version": "1.0.0",
        "description": (
            "OpenAPI-схема серверной части приложения семейного бюджета. "
            "Основной интерфейс проекта построен на Django Templates: маршруты "
            "возвращают HTML-страницы, выполняют редиректы после успешных POST-запросов "
            "и используют стандартные sessionid-cookie и CSRF-защиту Django."
        ),
    },
    "tags": [
        {
            "name": "Документация",
            "description": "Swagger UI и машинно-читаемая OpenAPI-схема.",
        },
        {
            "name": "Аутентификация",
            "description": "Регистрация, вход и выход пользователей.",
        },
        {
            "name": "Семья",
            "description": "Создание семьи, участники и роли.",
        },
        {
            "name": "Транзакции",
            "description": "Список, создание и удаление доходов/расходов.",
        },
        {
            "name": "Категории",
            "description": "Создание и удаление категорий доходов/расходов.",
        },
        {
            "name": "Бюджеты",
            "description": "Месячные лимиты по расходным категориям.",
        },
        {
            "name": "Отчёты и CSV",
            "description": "Финансовые отчёты, импорт и экспорт транзакций.",
        },
    ],
    "paths": {
        "/openapi.json": {
            "get": {
                "tags": ["Документация"],
                "operationId": "getOpenApiSchema",
                "summary": "Получить OpenAPI-схему",
                "description": "Возвращает JSON-документ OpenAPI 3.0 для текущего Django-приложения.",
                "responses": {
                    "200": {
                        "description": "OpenAPI JSON",
                        "content": {
                            "application/json": {
                                "schema": {"type": "object"},
                            },
                        },
                    },
                },
            },
        },
        "/swagger/": {
            "get": {
                "tags": ["Документация"],
                "operationId": "getSwaggerUi",
                "summary": "Открыть Swagger UI",
                "description": "HTML-страница Swagger UI, которая загружает схему из /openapi.json.",
                "responses": {"200": HTML_PAGE},
            },
        },
        "/accounts/login/": {
            "get": _html_get(
                "Аутентификация",
                "getLoginPage",
                "Форма входа",
                "Возвращает стандартную HTML-страницу входа Django.",
                auth_required=False,
            ),
            "post": _html_post(
                "Аутентификация",
                "postLogin",
                "Войти в систему",
                "Проверяет логин и пароль, создаёт Django-сессию и выполняет редирект.",
                _form_request_body("#/components/schemas/LoginForm"),
                auth_required=False,
            ),
        },
        "/accounts/logout/": {
            "post": {
                "tags": ["Аутентификация"],
                "operationId": "postLogout",
                "summary": "Выйти из системы",
                "description": "Завершает текущую Django-сессию и перенаправляет на страницу входа.",
                "responses": {"302": REDIRECT},
                "security": SESSION_CSRF_SECURITY,
            },
        },
        "/register/": {
            "get": _html_get(
                "Аутентификация",
                "getRegisterPage",
                "Форма регистрации",
                "Возвращает HTML-форму регистрации нового пользователя.",
                auth_required=False,
            ),
            "post": _html_post(
                "Аутентификация",
                "postRegister",
                "Зарегистрировать пользователя",
                "Создаёт пользователя, выполняет вход и перенаправляет на семейную панель.",
                _form_request_body("#/components/schemas/RegisterForm"),
                auth_required=False,
            ),
        },
        "/": {
            "get": _html_get(
                "Семья",
                "getFamilyDashboard",
                "Семейная панель",
                "Показывает сводку по семье: участников, транзакции и бюджеты текущего месяца.",
            ),
        },
        "/family/create/": {
            "get": _html_get(
                "Семья",
                "getFamilyCreatePage",
                "Форма создания семьи",
                "Возвращает форму создания семьи для пользователя без текущей семьи.",
            ),
            "post": _html_post(
                "Семья",
                "postFamilyCreate",
                "Создать семью",
                "Создаёт семью, добавляет текущего пользователя и назначает ему роль главы семьи.",
                _form_request_body("#/components/schemas/FamilyCreateForm"),
            ),
        },
        "/family/members/": {
            "get": _html_get(
                "Семья",
                "getFamilyMembers",
                "Список участников семьи",
                "Показывает участников семьи и их роли.",
            ),
            "post": _html_post(
                "Семья",
                "postFamilyMemberAdd",
                "Добавить существующего пользователя в семью",
                "Добавляет пользователя по логину и назначает роль. Требуется право can_manage_family.",
                _form_request_body("#/components/schemas/FamilyMemberAddForm"),
            ),
        },
        "/family/invite/": {
            "get": _html_get(
                "Семья",
                "getFamilyInvitePage",
                "Форма приглашения участника",
                "Возвращает форму создания нового пользователя внутри текущей семьи.",
            ),
            "post": _html_post(
                "Семья",
                "postFamilyInvite",
                "Пригласить нового участника",
                "Создаёт нового пользователя, добавляет его в семью и назначает роль. Требуется право can_manage_family.",
                _form_request_body("#/components/schemas/FamilyMemberInviteForm"),
            ),
        },
        "/family/member/{member_id}/role/": {
            "get": _html_get(
                "Семья",
                "getFamilyMemberRolePage",
                "Форма смены роли",
                "Возвращает страницу изменения роли участника семьи.",
                parameters=[
                    _path_parameter(
                        "member_id",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор FamilyMember.",
                    ),
                ],
            ),
            "post": _html_post(
                "Семья",
                "postFamilyMemberRole",
                "Изменить роль участника",
                "Меняет роль участника семьи. Требуется право can_manage_family.",
                _form_request_body("#/components/schemas/FamilyMemberRoleForm"),
                parameters=[
                    _path_parameter(
                        "member_id",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор FamilyMember.",
                    ),
                ],
            ),
        },
        "/family/leave/": {
            "get": _html_get(
                "Семья",
                "getFamilyLeavePage",
                "Подтверждение выхода из семьи",
                "Показывает страницу подтверждения выхода. Глава семьи не может выйти до передачи роли.",
            ),
            "post": {
                "tags": ["Семья"],
                "operationId": "postFamilyLeave",
                "summary": "Покинуть семью",
                "description": "Удаляет текущего пользователя из семьи, если он не является главой.",
                "responses": {"302": REDIRECT},
                "security": SESSION_CSRF_SECURITY,
            },
        },
        "/transactions/": {
            "get": _html_get(
                "Транзакции",
                "getTransactions",
                "Список транзакций",
                "Показывает транзакции пользователя или семьи с фильтрами и пагинацией.",
                parameters=[
                    _query_parameter(
                        "start_date",
                        {"type": "string", "format": "date"},
                        "Начальная дата фильтра.",
                    ),
                    _query_parameter(
                        "end_date",
                        {"type": "string", "format": "date"},
                        "Конечная дата фильтра.",
                    ),
                    _query_parameter(
                        "category",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор категории.",
                    ),
                    _query_parameter(
                        "member",
                        {
                            "oneOf": [
                                {"type": "integer", "minimum": 1},
                                {"type": "string", "enum": ["all"]},
                            ]
                        },
                        "Идентификатор пользователя семьи или all.",
                    ),
                    _query_parameter(
                        "page",
                        {"type": "integer", "minimum": 1, "default": 1},
                        "Номер страницы.",
                    ),
                    _query_parameter(
                        "per_page",
                        {"type": "integer", "enum": [10, 20, 50, 100], "default": 20},
                        "Размер страницы.",
                    ),
                ],
            ),
        },
        "/transactions/create/": {
            "get": _html_get(
                "Транзакции",
                "getTransactionCreatePage",
                "Форма создания транзакции",
                "Возвращает форму создания дохода или расхода.",
            ),
            "post": _html_post(
                "Транзакции",
                "postTransactionCreate",
                "Создать транзакцию",
                "Создаёт транзакцию и предупреждает пользователя при приближении к лимиту бюджета.",
                _form_request_body("#/components/schemas/TransactionForm"),
            ),
        },
        "/transactions/{pk}/delete/": {
            "get": _html_get(
                "Транзакции",
                "getTransactionDeletePage",
                "Подтверждение удаления транзакции",
                "Возвращает страницу подтверждения удаления доступной транзакции.",
                parameters=[
                    _path_parameter(
                        "pk",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор Transaction.",
                    ),
                ],
            ),
            "post": {
                "tags": ["Транзакции"],
                "operationId": "postTransactionDelete",
                "summary": "Удалить транзакцию",
                "description": "Удаляет транзакцию с учётом личного режима и семейных прав.",
                "parameters": [
                    _path_parameter(
                        "pk",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор Transaction.",
                    ),
                ],
                "responses": {"302": REDIRECT},
                "security": SESSION_CSRF_SECURITY,
            },
        },
        "/categories/create/": {
            "get": _html_get(
                "Категории",
                "getCategoryCreatePage",
                "Форма создания категории",
                "Возвращает форму создания категории дохода или расхода.",
            ),
            "post": _html_post(
                "Категории",
                "postCategoryCreate",
                "Создать категорию",
                "Создаёт личную или семейную категорию. Для семейной категории требуется право add_category.",
                _form_request_body("#/components/schemas/CategoryForm"),
            ),
        },
        "/categories/{pk}/delete/": {
            "get": _html_get(
                "Категории",
                "getCategoryDeletePage",
                "Подтверждение удаления категории",
                "Возвращает страницу подтверждения удаления категории.",
                parameters=[
                    _path_parameter(
                        "pk",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор Category.",
                    ),
                ],
            ),
            "post": {
                "tags": ["Категории"],
                "operationId": "postCategoryDelete",
                "summary": "Удалить категорию",
                "description": "Удаляет категорию, если она принадлежит пользователю/семье и не используется транзакциями.",
                "parameters": [
                    _path_parameter(
                        "pk",
                        {"type": "integer", "minimum": 1},
                        "Идентификатор Category.",
                    ),
                ],
                "responses": {"302": REDIRECT},
                "security": SESSION_CSRF_SECURITY,
            },
        },
        "/budgets/": {
            "get": _html_get(
                "Бюджеты",
                "getBudgets",
                "Список бюджетов",
                "Показывает бюджеты текущего и предыдущего месяца.",
            ),
            "post": _html_post(
                "Бюджеты",
                "postBudgetUpsert",
                "Создать или обновить бюджет",
                "Создаёт или обновляет лимит по расходной категории и месяцу. Требуется право can_set_budget в семье.",
                _form_request_body("#/components/schemas/BudgetForm"),
            ),
        },
        "/budgets/{pk}/delete/": {
            "get": _html_get(
                "Бюджеты",
                "getBudgetDeletePage",
                "Подтверждение удаления бюджета",
                "Возвращает страницу подтверждения удаления бюджета.",
                parameters=[
                    _path_parameter(
                        "pk", {"type": "integer", "minimum": 1}, "Идентификатор Budget."
                    ),
                ],
            ),
            "post": {
                "tags": ["Бюджеты"],
                "operationId": "postBudgetDelete",
                "summary": "Удалить бюджет",
                "description": "Удаляет бюджет пользователя или семьи с проверкой прав.",
                "parameters": [
                    _path_parameter(
                        "pk", {"type": "integer", "minimum": 1}, "Идентификатор Budget."
                    ),
                ],
                "responses": {"302": REDIRECT},
                "security": SESSION_CSRF_SECURITY,
            },
        },
        "/reports/": {
            "get": _html_get(
                "Отчёты и CSV",
                "getReports",
                "Финансовые отчёты",
                "Показывает месячную сводку, расходы по категориям и сравнение бюджета с фактом.",
            ),
        },
        "/export/csv/": {
            "get": {
                "tags": ["Отчёты и CSV"],
                "operationId": "getCsvExport",
                "summary": "Экспортировать транзакции в CSV",
                "description": "Возвращает CSV-файл с транзакциями пользователя или семьи. Требуется право can_import_export в семье.",
                "responses": {
                    "200": CSV_FILE,
                    "302": REDIRECT,
                    "403": FORBIDDEN,
                },
                "security": SESSION_SECURITY,
            },
        },
        "/import/csv/": {
            "get": _html_get(
                "Отчёты и CSV",
                "getCsvImportPage",
                "Форма импорта CSV",
                "Возвращает страницу загрузки CSV-файла.",
            ),
            "post": _html_post(
                "Отчёты и CSV",
                "postCsvImport",
                "Импортировать транзакции из CSV",
                "Загружает CSV-файл, валидирует строки и создаёт транзакции. Требуется право can_import_export в семье.",
                _multipart_request_body("#/components/schemas/CsvImportForm"),
                forbidden=True,
            ),
        },
    },
    "components": {
        "securitySchemes": {
            "SessionAuth": {
                "type": "apiKey",
                "in": "cookie",
                "name": "sessionid",
                "description": "Стандартная cookie авторизованной Django-сессии.",
            },
            "CSRFToken": {
                "type": "apiKey",
                "in": "header",
                "name": "X-CSRFToken",
                "description": (
                    "CSRF-токен Django для небезопасных методов. "
                    "В HTML-формах также используется поле csrfmiddlewaretoken."
                ),
            },
        },
        "responses": {
            "HtmlPage": {
                "description": "HTML-страница Django.",
                "content": {
                    "text/html": {
                        "schema": {"type": "string"},
                    },
                },
            },
            "Redirect": {
                "description": "Редирект после успешной операции или проверки состояния.",
                "headers": {
                    "Location": {
                        "description": "URL назначения.",
                        "schema": {"type": "string"},
                    },
                },
            },
            "LoginRedirect": {
                "description": "Редирект на страницу входа для анонимного пользователя.",
                "headers": {
                    "Location": {
                        "description": "URL страницы входа.",
                        "schema": {"type": "string"},
                    },
                },
            },
            "Forbidden": {
                "description": "Доступ запрещён из-за отсутствия нужных прав.",
                "content": {
                    "text/html": {
                        "schema": {"type": "string"},
                    },
                },
            },
            "CsvFile": {
                "description": "CSV-файл транзакций.",
                "content": {
                    "text/csv": {
                        "schema": {
                            "type": "string",
                            "format": "binary",
                        },
                    },
                },
            },
        },
        "schemas": {
            "LoginForm": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string", "maxLength": 150, "example": "ivan"},
                    "password": {
                        "type": "string",
                        "format": "password",
                        "example": "StrongPass123!",
                    },
                },
            },
            "RegisterForm": {
                "type": "object",
                "required": ["username", "email", "password1", "password2"],
                "properties": {
                    "username": {
                        "type": "string",
                        "maxLength": 150,
                        "example": "new_user",
                    },
                    "email": {
                        "type": "string",
                        "format": "email",
                        "example": "user@example.com",
                    },
                    "password1": {"type": "string", "format": "password"},
                    "password2": {"type": "string", "format": "password"},
                },
            },
            "FamilyCreateForm": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": 100,
                        "example": "Семья Ивановых",
                    },
                },
            },
            "FamilyMemberAddForm": {
                "type": "object",
                "required": ["username", "role"],
                "properties": {
                    "username": {
                        "type": "string",
                        "maxLength": 150,
                        "example": "member_user",
                    },
                    "role": {"$ref": "#/components/schemas/FamilyRole"},
                },
            },
            "FamilyMemberInviteForm": {
                "type": "object",
                "required": ["username", "password1", "password2", "role"],
                "properties": {
                    "username": {
                        "type": "string",
                        "maxLength": 150,
                        "example": "invited_user",
                    },
                    "email": {
                        "type": "string",
                        "format": "email",
                        "example": "invited@example.com",
                    },
                    "password1": {"type": "string", "format": "password"},
                    "password2": {"type": "string", "format": "password"},
                    "role": {
                        "type": "string",
                        "enum": ["member", "viewer"],
                        "example": "member",
                    },
                },
            },
            "FamilyMemberRoleForm": {
                "type": "object",
                "required": ["role"],
                "properties": {
                    "role": {"$ref": "#/components/schemas/FamilyRole"},
                },
            },
            "FamilyRole": {
                "type": "string",
                "enum": ["head", "member", "viewer"],
                "description": "Роль участника семьи.",
                "example": "member",
            },
            "TransactionForm": {
                "type": "object",
                "required": ["amount", "category", "date"],
                "properties": {
                    "amount": {
                        "type": "string",
                        "format": "decimal",
                        "pattern": r"^\d+(\.\d{1,2})?$",
                        "example": "1500.00",
                    },
                    "category": {"type": "integer", "minimum": 1, "example": 1},
                    "description": {
                        "type": "string",
                        "maxLength": 255,
                        "example": "Покупка продуктов",
                    },
                    "date": {
                        "type": "string",
                        "format": "date",
                        "example": "2026-05-10",
                    },
                },
            },
            "CategoryForm": {
                "type": "object",
                "required": ["name", "type"],
                "properties": {
                    "name": {"type": "string", "maxLength": 100, "example": "Продукты"},
                    "type": {"$ref": "#/components/schemas/CategoryType"},
                },
            },
            "CategoryType": {
                "type": "string",
                "enum": ["income", "expense"],
                "example": "expense",
            },
            "BudgetForm": {
                "type": "object",
                "required": ["category", "amount", "month"],
                "properties": {
                    "category": {"type": "integer", "minimum": 1, "example": 1},
                    "amount": {
                        "type": "string",
                        "format": "decimal",
                        "pattern": r"^\d+(\.\d{1,2})?$",
                        "example": "25000.00",
                    },
                    "month": {
                        "type": "string",
                        "pattern": r"^\d{4}-\d{2}$",
                        "description": "Месяц в формате ГГГГ-ММ.",
                        "example": "2026-05",
                    },
                },
            },
            "CsvImportForm": {
                "type": "object",
                "required": ["csv_file"],
                "properties": {
                    "csv_file": {
                        "type": "string",
                        "format": "binary",
                        "description": "CSV-файл с транзакциями.",
                    },
                },
            },
        },
    },
}


def build_openapi_schema(request):
    schema = deepcopy(OPENAPI_SCHEMA)
    schema["servers"] = [
        {
            "url": request.build_absolute_uri("/").rstrip("/"),
            "description": "Текущий сервер Django",
        },
    ]
    return schema


@require_GET
def openapi_schema(request):
    return JsonResponse(
        build_openapi_schema(request),
        json_dumps_params={"ensure_ascii": False, "indent": 2},
    )


@require_GET
def swagger_ui(request):
    return render(
        request,
        "core/swagger_ui.html",
        {"schema_url": reverse("openapi_schema")},
    )
