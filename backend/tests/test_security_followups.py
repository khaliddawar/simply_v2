"""Security follow-ups from the 2026-10-24 review of the Google sign-in fix.

1. The dashboard catch-all served any readable file on the server ("../" escapes).
2. The Google code-exchange callback signed in to whatever record carried the Google
   id, even when that record's email differed (an id planted through the old
   /google/extension hole).
3. /register, with Authorizer configured, linked a new signup to an existing record
   with the same email and returned a login token for it.
"""
import os
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
os.environ["PINECONE_API_KEY"] = "test-api-key"

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.test_google_extension_login import (  # reuse the fakes of the Google sign-in tests
    FakeDB, make_user, env, google, reset_settings, GOOGLE_SUB, GOOGLE_EMAIL, OUR_CLIENT_ID,
)

VICTIM_EMAIL = "victim@example.com"


# ---------------------------------------------------------------- 1. static file escape
class TestSafeStaticFile:
    @pytest.fixture
    def tree(self, tmp_path):
        root = tmp_path / "static" / "dashboard"
        (root / "assets").mkdir(parents=True)
        (root / "index.html").write_text("<html></html>")
        (root / "assets" / "app.js").write_text("console.log(1)")
        (tmp_path / "secret.txt").write_text("outside")
        (tmp_path / "static" / "also_outside.txt").write_text("outside")
        return root

    def test_serves_files_inside_the_dashboard(self, tree):
        from app.main import safe_static_file
        assert safe_static_file(tree, "index.html") == (tree / "index.html").resolve()
        assert safe_static_file(tree, "assets/app.js") == (tree / "assets" / "app.js").resolve()

    @pytest.mark.parametrize("requested", [
        "../../secret.txt",
        "../also_outside.txt",
        "assets/../../../secret.txt",
        "..\\..\\secret.txt",
        "assets/../../also_outside.txt",
    ])
    def test_refuses_paths_that_climb_out(self, tree, requested):
        from app.main import safe_static_file
        assert safe_static_file(tree, requested) is None

    def test_refuses_absolute_paths(self, tree, tmp_path):
        from app.main import safe_static_file
        assert safe_static_file(tree, str(tmp_path / "secret.txt")) is None

    def test_refuses_directories_and_missing_files(self, tree):
        from app.main import safe_static_file
        assert safe_static_file(tree, "assets") is None
        assert safe_static_file(tree, "nope.js") is None


# ---------------------------------------------------------------- 2. planted Google id on the callback
@pytest.mark.asyncio
async def test_code_flow_refuses_a_google_id_planted_on_another_email(env, google):
    from app.services.auth_service import AuthService
    service = AuthService()
    service.google_client_id = OUR_CLIENT_ID
    service.google_client_secret = "test-client-secret"
    victim = make_user(VICTIM_EMAIL, google_id=GOOGLE_SUB)  # attacker's Google id planted on the victim's record
    service.db = FakeDB([victim])

    def handle(request):
        google.requests.append(request)
        url = str(request.url)
        if url == "https://oauth2.googleapis.com/token":
            return httpx.Response(200, json={"access_token": "attacker-google-token"})
        if url == "https://www.googleapis.com/oauth2/v2/userinfo":
            return httpx.Response(200, json={"id": GOOGLE_SUB, "email": GOOGLE_EMAIL, "verified_email": True})
        return httpx.Response(599)

    google.handle = handle
    result = await service.google_oauth_callback(code="attacker-code", redirect_uri="http://localhost/cb")
    assert result["success"] is False
    assert "access_token" not in result
    assert service.db.writes == []


# ---------------------------------------------------------------- 3. /register on an existing email
def test_register_refuses_an_existing_email_before_calling_authorizer(env, monkeypatch):
    from app.routes import auth as auth_routes
    from app.services.auth_service import get_auth_service
    from app.services.authorizer_service import get_authorizer_service

    env.setenv("AUTHORIZER_URL", "https://authorizer.invalid")
    reset_settings()
    victim = make_user(VICTIM_EMAIL, google_id="victim-google-sub")
    db = FakeDB([victim])
    calls = []

    async def link_authorizer_user(uid, aid):
        db.writes.append(("link_authorizer_user", uid, aid))
        return True

    db.link_authorizer_user = link_authorizer_user
    asvc = get_auth_service(); saved_a = asvc.db; asvc.db = db
    zsvc = get_authorizer_service(); saved_z = zsvc.db; zsvc.db = db
    real_client = httpx.AsyncClient

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(200, json={"data": {"signup": {"message": "ok", "user": {"id": "authz-new", "email": VICTIM_EMAIL}, "access_token": "x"}}})

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **k: real_client(transport=httpx.MockTransport(handler)))
    try:
        app = FastAPI()
        app.include_router(auth_routes.router, prefix="/api/auth")
        r = TestClient(app).post("/api/auth/register", json={"email": VICTIM_EMAIL, "password": "Attacker-chosen-pw-1"})
        assert r.status_code == 400, r.text
        assert "access_token" not in r.text
        assert calls == []          # Authorizer never contacted
        assert db.writes == []      # nothing linked or changed
    finally:
        asvc.db = saved_a
        zsvc.db = saved_z
