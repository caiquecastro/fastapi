import pytest
from fastapi import APIRouter, FastAPI
from fastapi.openapi.models import Operation, PathItem, RequestBody
from fastapi.testclient import TestClient
from pydantic import BaseModel


class Search(BaseModel):
    text: str


@pytest.fixture(params=[False, True], ids=["app", "included-router"])
def client(request: pytest.FixtureRequest):
    app = FastAPI()
    app.openapi_version = "3.2.0"
    router = APIRouter() if request.param else app

    @router.api_route("/search", methods=["QUERY"])
    def search(body: Search) -> Search:
        return body

    @router.api_route("/optional", methods=["QUERY"])
    def optional(body: Search | None = None) -> Search | None:
        return body

    @router.api_route("/no-body", methods=["QUERY"])
    def no_body() -> dict[str, bool]:
        return {"ok": True}

    if isinstance(router, APIRouter):
        app.include_router(router)

    with TestClient(app) as test_client:
        yield test_client


def test_query_with_body(client: TestClient):
    response = client.request("QUERY", "/search", json={"text": "FastAPI"})
    assert response.status_code == 200, response.text
    assert response.json() == {"text": "FastAPI"}

    response = client.request("QUERY", "/search")
    assert response.status_code == 422, response.text
    assert response.json()["detail"][0]["loc"] == ["body"]


def test_query_openapi_request_body(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200, response.text
    schema = response.json()
    assert schema["openapi"] == "3.2.0"
    operation = schema["paths"]["/search"]["query"]
    assert operation["requestBody"] == {
        "content": {
            "application/json": {"schema": {"$ref": "#/components/schemas/Search"}}
        },
        "required": True,
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/Search"
    }
    assert "422" in operation["responses"]
    assert schema["components"]["schemas"]["Search"]["required"] == ["text"]


def test_query_optional_body(client: TestClient):
    response = client.request("QUERY", "/optional")
    assert response.status_code == 200, response.text
    assert response.json() is None

    schema = client.get("/openapi.json").json()
    request_body = schema["paths"]["/optional"]["query"]["requestBody"]
    assert not request_body.get("required", False)
    assert request_body["content"]["application/json"]["schema"]["anyOf"] == [
        {"$ref": "#/components/schemas/Search"},
        {"type": "null"},
    ]


def test_query_without_body(client: TestClient):
    response = client.request("QUERY", "/no-body")
    assert response.status_code == 200, response.text
    assert response.json() == {"ok": True}
    schema = client.get("/openapi.json").json()
    assert "requestBody" not in schema["paths"]["/no-body"]["query"]


def test_query_path_item_model(client: TestClient):
    schema = client.get("/openapi.json").json()
    path_item = PathItem.model_validate(schema["paths"]["/search"])
    assert isinstance(path_item.query, Operation)
    assert isinstance(path_item.query.requestBody, RequestBody)
    assert path_item.query.requestBody.required is True
