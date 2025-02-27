"""
Retesting Starlette StaticFile ASGIApp
"""
import os
import pathlib
import stat
import time

import anyio
import pytest
from ellar.core import AppFactory
from ellar.core.staticfiles import StaticFiles
from ellar.testing import TestClient
from starlette.exceptions import HTTPException
from starlette.routing import Mount


def test_staticfiles(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    app = StaticFiles(directories=[tmpdir])
    client = TestClient(app)
    response = client.get("/example.txt")
    assert response.status_code == 200
    assert response.text == "<file content>"


def test_staticfiles_with_pathlib(tmpdir):
    base_dir = pathlib.Path(tmpdir)
    path = base_dir / "example.txt"
    with open(path, "w") as file:
        file.write("<file content>")

    app = StaticFiles(directories=[base_dir])
    client = TestClient(app)
    response = client.get("/example.txt")
    assert response.status_code == 200
    assert response.text == "<file content>"


def test_staticfiles_head_with_middleware(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("x" * 100)

    routers = [Mount("/static", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)

    client = TestClient(app)
    response = client.head("/static/example.txt")
    assert response.status_code == 200
    assert response.headers.get("content-length") == "100"


def test_staticfiles_with_package():
    app = StaticFiles(packages=["tests"])
    client = TestClient(app)
    response = client.get("/example.txt")
    assert response.status_code == 200
    assert response.text == "123\n"

    app = StaticFiles(packages=[("tests", "statics")])
    client = TestClient(app)
    response = client.get("/example.txt")
    assert response.status_code == 200
    assert response.text == "123\n"


def test_staticfiles_post(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app)

    response = client.post("/example.txt")
    assert response.status_code == 405
    assert response.json() == {"detail": "Method Not Allowed", "status_code": 405}


def test_staticfiles_with_directory_returns_404(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app)

    response = client.get("/")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "status_code": 404}


def test_staticfiles_with_missing_file_returns_404(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app)

    response = client.get("/404.txt")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "status_code": 404}


def test_staticfiles_instantiated_with_missing_directory(tmpdir):
    with pytest.raises(RuntimeError) as exc_info:
        path = os.path.join(tmpdir, "no_such_directory")
        StaticFiles(directories=[path])
    assert "does not exist" in str(exc_info.value)


def test_staticfiles_configured_with_missing_directory(tmpdir):
    path = os.path.join(tmpdir, "no_such_directory")
    app = StaticFiles(directories=[path], check_dir=False)
    client = TestClient(app)
    with pytest.raises(RuntimeError) as exc_info:
        client.get("/example.txt")
    assert "does not exist" in str(exc_info.value)


def test_staticfiles_configured_with_file_instead_of_directory(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    app = StaticFiles(directories=[path], check_dir=False)
    client = TestClient(app)
    with pytest.raises(RuntimeError) as exc_info:
        client.get("/example.txt")
    assert "is not a directory" in str(exc_info.value)


def test_staticfiles_config_check_occurs_only_once(tmpdir):
    app = StaticFiles(directories=[tmpdir])
    client = TestClient(app)
    assert not app.config_checked

    with pytest.raises(HTTPException):
        client.get("/")

    assert app.config_checked

    with pytest.raises(HTTPException):
        client.get("/")


def test_staticfiles_prevents_breaking_out_of_directory(tmpdir):
    directory = os.path.join(tmpdir, "foo")
    os.mkdir(directory)

    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("outside root dir")

    app = StaticFiles(directories=[directory])
    # We can't test this with 'requests', so we test the app directly here.
    path = app.get_path({"path": "/../example.txt"})
    scope = {"method": "GET"}

    with pytest.raises(HTTPException) as exc_info:
        anyio.run(app.get_response, path, scope)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Not Found"


def test_staticfiles_never_read_file_for_head_method(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    app = StaticFiles(directories=[tmpdir])
    client = TestClient(app)
    response = client.head("/example.txt")
    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-length"] == "14"


def test_staticfiles_304_with_etag_match(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    app = StaticFiles(directories=[tmpdir])
    client = TestClient(app)
    first_resp = client.get("/example.txt")
    assert first_resp.status_code == 200
    last_etag = first_resp.headers["etag"]
    second_resp = client.get("/example.txt", headers={"if-none-match": last_etag})
    assert second_resp.status_code == 304
    assert second_resp.content == b""


def test_staticfiles_304_with_last_modified_compare_last_req(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    file_last_modified_time = time.mktime(
        time.strptime("2013-10-10 23:40:00", "%Y-%m-%d %H:%M:%S")
    )
    with open(path, "w") as file:
        file.write("<file content>")
    os.utime(path, (file_last_modified_time, file_last_modified_time))

    app = StaticFiles(directories=[tmpdir])
    client = TestClient(app)
    # last modified less than last request, 304
    response = client.get(
        "/example.txt", headers={"If-Modified-Since": "Thu, 11 Oct 2013 15:30:19 GMT"}
    )
    assert response.status_code == 304
    assert response.content == b""
    # last modified greater than last request, 200 with content
    response = client.get(
        "/example.txt", headers={"If-Modified-Since": "Thu, 20 Feb 2012 15:30:19 GMT"}
    )
    assert response.status_code == 200
    assert response.content == b"<file content>"


def test_staticfiles_html_normal(tmpdir):
    path = os.path.join(tmpdir, "404.html")
    with open(path, "w") as file:
        file.write("<h1>Custom not found page</h1>")
    path = os.path.join(tmpdir, "dir")
    os.mkdir(path)
    path = os.path.join(path, "index.html")
    with open(path, "w") as file:
        file.write("<h1>Hello</h1>")

    app = StaticFiles(directories=[tmpdir], html=True)
    client = TestClient(app)

    response = client.get("/dir/")
    assert response.url == "http://testserver/dir/"
    assert response.status_code == 200
    assert response.text == "<h1>Hello</h1>"

    response = client.get("/dir")
    assert response.url == "http://testserver/dir/"
    assert response.status_code == 200
    assert response.text == "<h1>Hello</h1>"

    response = client.get("/dir/index.html")
    assert response.url == "http://testserver/dir/index.html"
    assert response.status_code == 200
    assert response.text == "<h1>Hello</h1>"

    response = client.get("/missing")
    assert response.status_code == 404
    assert response.text == "<h1>Custom not found page</h1>"


def test_staticfiles_html_without_index(tmpdir):
    path = os.path.join(tmpdir, "404.html")
    with open(path, "w") as file:
        file.write("<h1>Custom not found page</h1>")
    path = os.path.join(tmpdir, "dir")
    os.mkdir(path)

    app = StaticFiles(directories=[tmpdir], html=True)
    client = TestClient(app)

    response = client.get("/dir/")
    assert response.url == "http://testserver/dir/"
    assert response.status_code == 404
    assert response.text == "<h1>Custom not found page</h1>"

    response = client.get("/dir")
    assert response.url == "http://testserver/dir"
    assert response.status_code == 404
    assert response.text == "<h1>Custom not found page</h1>"

    response = client.get("/missing")
    assert response.status_code == 404
    assert response.text == "<h1>Custom not found page</h1>"


def test_staticfiles_html_without_404(tmpdir):
    path = os.path.join(tmpdir, "dir")
    os.mkdir(path)
    path = os.path.join(path, "index.html")
    with open(path, "w") as file:
        file.write("<h1>Hello</h1>")

    app = StaticFiles(directories=[tmpdir], html=True)
    client = TestClient(app)

    response = client.get("/dir/")
    assert response.url == "http://testserver/dir/"
    assert response.status_code == 200
    assert response.text == "<h1>Hello</h1>"

    response = client.get("/dir")
    assert response.url == "http://testserver/dir/"
    assert response.status_code == 200
    assert response.text == "<h1>Hello</h1>"

    with pytest.raises(HTTPException) as exc_info:
        response = client.get("/missing")
    assert exc_info.value.status_code == 404


def test_staticfiles_html_only_files(tmpdir):
    path = os.path.join(tmpdir, "hello.html")
    with open(path, "w") as file:
        file.write("<h1>Hello</h1>")

    app = StaticFiles(directories=[tmpdir], html=True)
    client = TestClient(app)

    with pytest.raises(HTTPException) as exc_info:
        response = client.get("/")
    assert exc_info.value.status_code == 404

    response = client.get("/hello.html")
    assert response.status_code == 200
    assert response.text == "<h1>Hello</h1>"


def test_staticfiles_cache_invalidation_for_deleted_file_html_mode(tmpdir):
    path_404 = os.path.join(tmpdir, "404.html")
    with open(path_404, "w") as file:
        file.write("<p>404 file</p>")
    path_some = os.path.join(tmpdir, "some.html")
    with open(path_some, "w") as file:
        file.write("<p>some file</p>")

    common_modified_time = time.mktime(
        time.strptime("2013-10-10 23:40:00", "%Y-%m-%d %H:%M:%S")
    )
    os.utime(path_404, (common_modified_time, common_modified_time))
    os.utime(path_some, (common_modified_time, common_modified_time))

    app = StaticFiles(directories=[tmpdir], html=True)
    client = TestClient(app)

    resp_exists = client.get("/some.html")
    assert resp_exists.status_code == 200
    assert resp_exists.text == "<p>some file</p>"

    resp_cached = client.get(
        "/some.html",
        headers={"If-Modified-Since": resp_exists.headers["last-modified"]},
    )
    assert resp_cached.status_code == 304

    os.remove(path_some)

    resp_deleted = client.get(
        "/some.html",
        headers={"If-Modified-Since": resp_exists.headers["last-modified"]},
    )
    assert resp_deleted.status_code == 404
    assert resp_deleted.text == "<p>404 file</p>"


def test_staticfiles_with_invalid_dir_permissions_returns_401(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    os.chmod(tmpdir, stat.S_IRWXO)

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app)

    response = client.get("/example.txt")
    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized", "status_code": 401}


def test_staticfiles_with_missing_dir_returns_404(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app)

    response = client.get("/foo/example.txt")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "status_code": 404}


def test_staticfiles_access_file_as_dir_returns_404(tmpdir):
    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app)

    response = client.get("/example.txt/foo")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "status_code": 404}


def test_staticfiles_unhandled_os_error_returns_500(tmpdir, monkeypatch):
    def mock_timeout(*args, **kwargs):
        raise TimeoutError

    path = os.path.join(tmpdir, "example.txt")
    with open(path, "w") as file:
        file.write("<file content>")

    routers = [Mount("/", app=StaticFiles(directories=[tmpdir]), name="static")]
    app = AppFactory.create_app(routers=routers)
    client = TestClient(app, raise_server_exceptions=False)

    monkeypatch.setattr("starlette.staticfiles.StaticFiles.lookup_path", mock_timeout)

    response = client.get("/example.txt")
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "status_code": 500}
