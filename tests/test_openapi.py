from django.urls import reverse


def test_openapi_schema_is_public_and_describes_core_routes(anonymous_client):
    response = anonymous_client.get(reverse("openapi_schema"))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("application/json")

    schema = response.json()
    assert schema["openapi"] == "3.0.3"
    assert schema["info"]["title"] == "Family Finance Backend"
    assert "/transactions/" in schema["paths"]
    assert "/import/csv/" in schema["paths"]
    assert "SessionAuth" in schema["components"]["securitySchemes"]
    assert "CSRFToken" in schema["components"]["securitySchemes"]


def test_swagger_ui_is_public_and_loads_openapi_schema(anonymous_client):
    response = anonymous_client.get(reverse("swagger_ui"))

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "SwaggerUIBundle" in content
    assert reverse("openapi_schema") in content
