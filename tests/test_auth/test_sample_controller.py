import base64
import pickle

import pytest
from ellar.testing import Test

from .app import AppModule, SimpleHeaderAuthHandler


class TestArticleController:
    test_module = Test.create_test_module(modules=[AppModule])
    test_module.create_application().add_authentication_schemes(SimpleHeaderAuthHandler)
    client = test_module.get_test_client()

    @pytest.mark.parametrize(
        "roles, path, status",
        [
            (["admin", "staff"], "staff-only", 200),
            (
                [
                    "admin",
                ],
                "staff-only",
                403,
            ),
            (
                [
                    "staff",
                ],
                "staff-only",
                200,
            ),
            (["admin", "staff"], "admin-only", 200),
            (
                [
                    "admin",
                ],
                "admin-only",
                200,
            ),
            (
                [
                    "staff",
                ],
                "admin-only",
                403,
            ),
        ],
    )
    def test_admin_and_staff_only_works(self, roles, path, status):
        with self.client as client:
            auth = base64.b64encode(pickle.dumps({"roles": roles, "id": 23}))
            res = client.get(f"/article/{path}", headers={"key": auth})
            assert res.status_code == status

    @pytest.mark.parametrize(
        "claim_value", [["create"], ["publish"], ["create", "publish"]]
    )
    def test_create_and_publish_works(self, claim_value):
        with self.client as client:
            auth = base64.b64encode(pickle.dumps({"article": claim_value, "id": 23}))
            res = client.get("/article/create", headers={"key": auth})
            assert res.status_code == 200
            assert res.text == '"fast and furious 10 Article"'

    @pytest.mark.parametrize(
        "age, route, status",
        [
            # 'at-least-21'
            (19, "at-least-21", 403),
            (20, "at-least-21", 403),
            (21, "at-least-21", 200),
            (22, "at-least-21", 200),
            # 'at-least-21-case-2'
            (19, "at-least-21-case-2", 403),
            (20, "at-least-21-case-2", 403),
            (21, "at-least-21-case-2", 200),
            (22, "at-least-21-case-2", 200),
        ],
    )
    def test_at_least_21_works(self, age, route, status):
        with self.client as client:
            auth = base64.b64encode(pickle.dumps({"age": age, "id": 23}))
            res = client.get(f"/article/{route}", headers={"key": auth})

            assert res.status_code == status
            if status == 200:
                assert res.text == '"Only for Age of 21 or more"'

    def test_authorization_guard_without_policy_checks_for_authentication(self):
        res = self.client.get("/article/list")

        assert res.status_code == 401
        auth = base64.b64encode(pickle.dumps({"age": 19, "id": 23}))

        res = self.client.get("/article/list", headers={"key": auth})
        assert res.status_code == 200
        assert res.text == '"List of articles"'


class TestMovieController:
    test_module = Test.create_test_module(modules=[AppModule])
    test_module.create_application().add_authentication_schemes(
        SimpleHeaderAuthHandler()
    )
    client = test_module.get_test_client()

    def test_get_fast_x_fails_for_anonymous_users(self):
        with self.client as client:
            res = client.get("/movies/")
            assert res.status_code == 401

    @pytest.mark.parametrize(
        "age, status",
        [
            (17, 403),
            (16, 403),
            (18, 200),
            (22, 200),
        ],
    )
    def test_get_fast_x_works(self, age, status):
        with self.client as client:
            auth = base64.b64encode(pickle.dumps({"age": age, "id": 23}))
            res = client.get("/movies/", headers={"key": auth})
            assert res.status_code == status
