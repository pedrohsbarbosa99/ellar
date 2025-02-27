from typing import Union
from unittest.mock import patch

from ellar.common import Body, post
from ellar.common.serializer import serialize_object
from ellar.core import Request
from ellar.openapi import OpenAPIDocumentBuilder
from ellar.testing import Test

from .sample import Item, OtherItem

tm = Test.create_test_module()


@post("/items/")
def save_union_body_and_embedded_body(
    item: Union[OtherItem, Item], qty: Body[int, Body.P(default=12)]
):
    return {"item": item, "qty": qty}


@post("/items/embed")
def embed_qty(qty: Body[int, Body.P(12, embed=True)]):
    return {"qty": qty}


app = tm.create_application()
app.router.append(save_union_body_and_embedded_body)

client = tm.get_test_client()


item_openapi_schema = {
    "openapi": "3.0.2",
    "info": {"title": "Ellar API Docs", "version": "1.0.0"},
    "paths": {
        "/items/": {
            "post": {
                "operationId": "save_union_body_and_embedded_body_items__post",
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/body_save_union_body_and_embedded_body_items__post"
                            }
                        }
                    },
                    "required": True,
                },
                "responses": {
                    "200": {
                        "description": "Successful Response",
                        "content": {
                            "application/json": {
                                "schema": {"title": "Response Model", "type": "object"}
                            }
                        },
                    },
                    "422": {
                        "description": "Validation Error",
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/HTTPValidationError"
                                }
                            }
                        },
                    },
                },
            }
        }
    },
    "components": {
        "schemas": {
            "HTTPValidationError": {
                "title": "HTTPValidationError",
                "required": ["detail"],
                "type": "object",
                "properties": {
                    "detail": {
                        "title": "Details",
                        "type": "array",
                        "items": {"$ref": "#/components/schemas/ValidationError"},
                    }
                },
            },
            "Item": {
                "title": "Item",
                "type": "object",
                "properties": {"name": {"title": "Name", "type": "string"}},
            },
            "OtherItem": {
                "title": "OtherItem",
                "required": ["price"],
                "type": "object",
                "properties": {"price": {"title": "Price", "type": "integer"}},
            },
            "ValidationError": {
                "title": "ValidationError",
                "required": ["loc", "msg", "type"],
                "type": "object",
                "properties": {
                    "loc": {
                        "title": "Location",
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "msg": {"title": "Message", "type": "string"},
                    "type": {"title": "Error Type", "type": "string"},
                },
            },
            "body_save_union_body_and_embedded_body_items__post": {
                "title": "body_save_union_body_and_embedded_body_items__post",
                "required": ["item"],
                "type": "object",
                "properties": {
                    "item": {
                        "title": "Item",
                        "include_in_schema": True,
                        "anyOf": [
                            {"$ref": "#/components/schemas/OtherItem"},
                            {"$ref": "#/components/schemas/Item"},
                        ],
                    },
                    "qty": {
                        "title": "Qty",
                        "type": "integer",
                        "default": 12,
                        "include_in_schema": True,
                    },
                },
            },
        }
    },
    "tags": [],
}


def test_item_openapi_schema():
    document = serialize_object(OpenAPIDocumentBuilder().build_document(app))
    assert document == item_openapi_schema


def test_post_other_item():
    response = client.post("/items/", json={"item": {"price": 100}})
    assert response.status_code == 200, response.text
    assert response.json() == {"item": {"price": 100}, "qty": 12}


def test_post_item():
    response = client.post("/items/", json={"item": {"name": "Foo"}})
    assert response.status_code == 200, response.text
    assert response.json() == {"item": {"name": "Foo"}, "qty": 12}


def test_embed_body():
    _tm = Test.create_test_module()
    _app = _tm.create_application()
    _app.router.append(embed_qty)

    _client = _tm.get_test_client()
    response = _client.post("/items/embed", json={"qty": 232})
    assert response.status_code == 200, response.text
    assert response.json() == {"qty": 232}


@patch.object(Request, "body")
def test_body_resolution_fails(mock_form):
    async def raise_exception():
        raise Exception()

    mock_form.return_value = raise_exception
    response = client.post("/items/", json={"item": {"price": 100}})

    assert response.status_code == 400
    assert response.json() == {
        "detail": "There was an error parsing the body",
        "status_code": 400,
    }
