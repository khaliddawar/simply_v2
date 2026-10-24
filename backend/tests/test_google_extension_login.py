"""
Tests for Google sign-in at POST /api/auth/google/extension.

Before this fix the route believed whatever google_id and email the request
body claimed, so anyone could get a login token for any account by sending
its email. Now the client must send the Google OAuth access token, the
server asks Google who it belongs to, and the account id and email come only
from Google's answer.

Google is never called for real: httpx.AsyncClient is swapped for one that
answers from a MockTransport, and the database is an in-memory fake that
records every write.

The file also checks the routes removed alongside the fix, the DEBUG
default, and the verified-email check in the code-exchange callback.
"""
import os

# Same dummy values as tests/test_auth.py. Settings requires these; nothing
# here connects to a database or to Pinecone.
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-testing-only"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/test"
os.environ["PINECONE_API_KEY"] = "test-api-key"

import importlib
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# The public client ID built into the dashboard and the extension.
PUBLIC_CLIENT_ID = "1049678014825-r2sgcffbksmm2jb8ikkdvdpfv23j8v7a.apps.googleusercontent.com"
OUR_CLIENT_ID = "our-web-client.apps.googleusercontent.com"
OTHER_CLIENT_ID = "someone-elses-app.apps.googleusercontent.com"

GOOGLE_TOKEN = "ya29.test-google-access-token"
GOOGLE_SUB = "109876543210987654321"
GOOGLE_EMAIL = "owner@example.com"

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

ROUTE = "/api/auth/google/extension"
UPDATE_MESSAGE_START = "Google sign-in needs an update"

MISSING = object()  # marks a field left out of Google's answer


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

class FakeDB:
    """In-memory stand-in for DatabaseService. Records every write."""

    def __init__(self, users=None, fail_with=None):
        self.users = [dict(u) for u in (users or [])]
        self.writes = []
        self.fail_with = fail_with

    def _check(self):
        if self.fail_with:
            raise self.fail_with

    async def get_user_by_google_id(self, google_id):
        self._check()
        for user in self.users:
            if user.get("google_id") == google_id:
                return dict(user)
        return None

    async def get_user_by_email(self, email):
        self._check()
        for user in self.users:
            if user["email"].lower() == email.lower().strip():
                return dict(user)
        return None

    async def update_user(self, user_id, updates):
        self._check()
        self.writes.append(("update_user", user_id, dict(updates)))
        for user in self.users:
            if user["id"] == user_id:
                user.update(updates)
        return True

    async def create_user(self, email, password_hash=None, google_id=None,
                          first_name=None, last_name=None):
        self._check()
        user = make_user(email=email, google_id=google_id,
                         first_name=first_name, last_name=last_name)
        self.writes.append(("create_user", user["id"], dict(user)))
        self.users.append(user)
        return dict(user)


def make_user(email, google_id=None, first_name="", last_name=""):
    user_id = str(uuid.uuid4())
    return {
        "id": user_id,
        "email": email,
        "google_id": google_id,
        "first_name": first_name,
        "last_name": last_name,
        "plan_type": "free",
        "pinecone_namespace": f"user_{user_id}",
    }


def good_tokeninfo(**overrides):
    answer = {
        "aud": OUR_CLIENT_ID,
        "azp": OUR_CLIENT_ID,
        "sub": GOOGLE_SUB,
        "email": GOOGLE_EMAIL,
        "email_verified": "true",
        "scope": "openid https://www.googleapis.com/auth/userinfo.email",
        "expires_in": "3599",
    }
    return _apply(answer, overrides)


def good_userinfo(**overrides):
    answer = {
        "sub": GOOGLE_SUB,
        "email": GOOGLE_EMAIL,
        "email_verified": True,
        "name": "Olive Owner",
        "given_name": "Olive",
        "family_name": "Owner",
    }
    return _apply(answer, overrides)


def _apply(answer, overrides):
    for key, value in overrides.items():
        if value is MISSING:
            answer.pop(key, None)
        else:
            answer[key] = value
    return answer


class FakeGoogle:
    """Answers tokeninfo and userinfo requests and records them."""

    def __init__(self):
        self.answers = {
            "tokeninfo": (200, good_tokeninfo()),
            "userinfo": (200, good_userinfo()),
        }
        self.errors = {}
        self.requests = []
        self.client_kwargs = []

    def calls(self, kind):
        return [r for r in self.requests if self._kind(r) == kind]

    @staticmethod
    def _kind(request):
        base = str(request.url).split("?")[0]
        if base == TOKENINFO_URL:
            return "tokeninfo"
        if base == USERINFO_URL:
            return "userinfo"
        return "unexpected"

    def handle(self, request):
        self.requests.append(request)
        kind = self._kind(request)
        if kind == "unexpected":
            return httpx.Response(599, text="unexpected URL")
        if kind in self.errors:
            raise self.errors[kind]("simulated failure", request=request)
        status, body = self.answers[kind]
        if isinstance(body, (dict, list)):
            return httpx.Response(status, json=body)
        return httpx.Response(status, text=body)


class FakeEmailService:
    def __init__(self):
        self.sent = []

    async def send_welcome_email(self, recipient_email, first_name=None):
        self.sent.append(recipient_email)
        return {"success": True}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def reset_settings():
    from app.settings import get_settings
    get_settings.cache_clear()


@pytest.fixture
def env(monkeypatch, tmp_path):
    """Known Google client-ID settings, isolated from any developer .env."""
    workdir = tmp_path / "backend"
    workdir.mkdir()
    monkeypatch.chdir(workdir)  # Settings reads ../.env relative to the cwd
    for name in ("GOOGLE_CLIENT_ID", "EXTENSION_GOOGLE_CLIENT_ID",
                 "FIRST_PARTY_GOOGLE_CLIENT_ID", "DEBUG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GOOGLE_CLIENT_ID", OUR_CLIENT_ID)
    reset_settings()
    yield monkeypatch
    reset_settings()


class _HttpxWithFakeGoogle:
    """Stands in for the httpx module inside auth_service only, so other
    modules (openai subclasses httpx.AsyncClient at import) are untouched."""

    def __init__(self, fake):
        self._fake = fake

    def AsyncClient(self, *args, **kwargs):
        self._fake.client_kwargs.append(dict(kwargs))
        kwargs["transport"] = httpx.MockTransport(self._fake.handle)
        return httpx.AsyncClient(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(httpx, name)


@pytest.fixture
def google(monkeypatch):
    import app.services.auth_service as auth_service_module
    fake = FakeGoogle()
    monkeypatch.setattr(auth_service_module, "httpx", _HttpxWithFakeGoogle(fake))
    return fake


@pytest.fixture
def emails(monkeypatch):
    import app.services.email_service as email_module
    fake = FakeEmailService()
    monkeypatch.setattr(email_module, "get_email_service", lambda: fake)
    return fake


@pytest.fixture
def auth_service():
    from app.services.auth_service import get_auth_service
    service = get_auth_service()
    saved_db = service.db
    service.db = FakeDB()
    yield service
    service.db = saved_db


@pytest.fixture
def client(env, google, emails, auth_service):
    from app.routes import auth as auth_routes
    app = FastAPI()
    app.include_router(auth_routes.router, prefix="/api/auth")
    return TestClient(app)


def post(client, body=None):
    return client.post(ROUTE, json=body if body is not None else {"access_token": GOOGLE_TOKEN})


def assert_refused(response, db, status=401):
    assert response.status_code == status, response.text
    assert "access_token" not in response.json()
    assert db.writes == []


# ---------------------------------------------------------------------------
# POST /api/auth/google/extension
# ---------------------------------------------------------------------------

class TestGoogleExtensionLogin:

    def test_valid_token_signs_in_with_googles_own_email(self, client, auth_service, emails):
        response = post(client)

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["user"]["email"] == GOOGLE_EMAIL
        created = [w for w in auth_service.db.writes if w[0] == "create_user"]
        assert len(created) == 1
        assert created[0][2]["email"] == GOOGLE_EMAIL
        assert created[0][2]["google_id"] == GOOGLE_SUB
        assert auth_service.get_user_id_from_token(data["access_token"]) == created[0][1]
        assert emails.sent == [GOOGLE_EMAIL]

    def test_existing_google_user_signs_in_without_writes(self, client, auth_service):
        user = make_user(GOOGLE_EMAIL, google_id=GOOGLE_SUB)
        auth_service.db = FakeDB([user])

        response = post(client)

        assert response.status_code == 200, response.text
        assert auth_service.get_user_id_from_token(response.json()["access_token"]) == user["id"]
        assert auth_service.db.writes == []

    def test_existing_email_account_is_linked_to_googles_id(self, client, auth_service):
        user = make_user(GOOGLE_EMAIL)
        auth_service.db = FakeDB([user])

        response = post(client)

        assert response.status_code == 200, response.text
        assert auth_service.get_user_id_from_token(response.json()["access_token"]) == user["id"]
        assert auth_service.db.writes == [("update_user", user["id"], {"google_id": GOOGLE_SUB})]

    def test_body_fields_that_match_google_are_accepted(self, client):
        response = post(client, {
            "access_token": GOOGLE_TOKEN,
            "google_id": GOOGLE_SUB,
            "email": GOOGLE_EMAIL,
            "given_name": "Olive",
        })

        assert response.status_code == 200, response.text
        assert response.json()["user"]["email"] == GOOGLE_EMAIL

    def test_body_claiming_another_email_gets_401_and_no_writes(self, client, auth_service):
        victim = make_user("victim@example.com")
        auth_service.db = FakeDB([victim])

        response = post(client, {
            "access_token": GOOGLE_TOKEN,
            "google_id": GOOGLE_SUB,
            "email": "victim@example.com",
        })

        assert_refused(response, auth_service.db)

    def test_body_claiming_another_google_id_gets_401_and_no_writes(self, client, auth_service):
        victim = make_user("victim@example.com", google_id="victims-google-id")
        auth_service.db = FakeDB([victim])

        response = post(client, {
            "access_token": GOOGLE_TOKEN,
            "google_id": "victims-google-id",
            "email": GOOGLE_EMAIL,
        })

        assert_refused(response, auth_service.db)

    def test_tokeninfo_400_gets_401(self, client, google, auth_service):
        google.answers["tokeninfo"] = (400, {"error": "invalid_token", "error_description": "Invalid Value"})

        response = post(client)

        assert_refused(response, auth_service.db)
        assert google.calls("userinfo") == []

    def test_token_issued_to_another_app_gets_401(self, client, google, auth_service):
        google.answers["tokeninfo"] = (200, good_tokeninfo(aud=OTHER_CLIENT_ID, azp=OTHER_CLIENT_ID))

        response = post(client)

        assert_refused(response, auth_service.db)
        assert google.calls("userinfo") == []

    @pytest.mark.parametrize("verified", [False, "false", MISSING], ids=["false", "string-false", "missing"])
    def test_unverified_email_gets_401(self, client, google, auth_service, verified):
        auth_service.db = FakeDB([make_user(GOOGLE_EMAIL)])
        google.answers["userinfo"] = (200, good_userinfo(email_verified=verified))

        response = post(client)

        assert_refused(response, auth_service.db)

    @pytest.mark.parametrize("kind", ["tokeninfo", "userinfo"])
    def test_google_timeout_gets_401(self, client, google, auth_service, kind):
        google.errors[kind] = httpx.ReadTimeout

        response = post(client)

        assert_refused(response, auth_service.db)
        timeouts = [kw.get("timeout") for kw in google.client_kwargs]
        assert timeouts and all(t is not None for t in timeouts)

    def test_old_client_without_token_gets_readable_401(self, client, google, auth_service):
        response = post(client, {
            "google_id": GOOGLE_SUB,
            "email": GOOGLE_EMAIL,
            "name": "Olive Owner",
            "given_name": "Olive",
            "family_name": "Owner",
            "picture": "https://example.com/p.png",
        })

        assert_refused(response, auth_service.db)
        assert response.json()["detail"].startswith(UPDATE_MESSAGE_START)
        assert google.requests == []

    def test_blank_token_gets_401_without_calling_google(self, client, google, auth_service):
        response = post(client, {"access_token": "   ", "email": GOOGLE_EMAIL})

        assert_refused(response, auth_service.db)
        assert google.requests == []

    def test_planted_link_with_another_email_is_refused(self, client, auth_service):
        # Through the old hole, the Google account owner planted their own
        # Google id on the victim's record. Signing in with their real token
        # must not open the victim's account.
        victim = make_user("victim@example.com", google_id=GOOGLE_SUB)
        auth_service.db = FakeDB([victim])

        response = post(client)

        assert_refused(response, auth_service.db)

    def test_planted_google_id_is_replaced_when_owner_signs_in(self, client, auth_service):
        owner = make_user(GOOGLE_EMAIL, google_id="planted-by-someone-else")
        auth_service.db = FakeDB([owner])

        response = post(client)

        assert response.status_code == 200, response.text
        assert auth_service.get_user_id_from_token(response.json()["access_token"]) == owner["id"]
        assert auth_service.db.writes == [("update_user", owner["id"], {"google_id": GOOGLE_SUB})]

    def test_azp_accepted_when_it_is_ours(self, client, google):
        google.answers["tokeninfo"] = (200, good_tokeninfo(aud=OTHER_CLIENT_ID, azp=OUR_CLIENT_ID))

        response = post(client)

        assert response.status_code == 200, response.text

    def test_built_in_client_id_accepted_by_default(self, client, google, env):
        env.delenv("GOOGLE_CLIENT_ID", raising=False)
        reset_settings()
        google.answers["tokeninfo"] = (200, good_tokeninfo(aud=PUBLIC_CLIENT_ID, azp=PUBLIC_CLIENT_ID))

        response = post(client)

        assert response.status_code == 200, response.text

    def test_no_client_ids_configured_refuses_everything(self, client, google, env, auth_service):
        env.delenv("GOOGLE_CLIENT_ID", raising=False)
        env.setenv("FIRST_PARTY_GOOGLE_CLIENT_ID", "")
        reset_settings()
        google.answers["tokeninfo"] = (200, good_tokeninfo(aud=PUBLIC_CLIENT_ID, azp=PUBLIC_CLIENT_ID))

        response = post(client)

        assert_refused(response, auth_service.db)
        assert google.requests == []

    @pytest.mark.parametrize("kind,status", [("tokeninfo", 500), ("userinfo", 401)])
    def test_non_200_with_normal_looking_body_gets_401(self, client, google, auth_service, kind, status):
        normal_body = good_tokeninfo() if kind == "tokeninfo" else good_userinfo()
        google.answers[kind] = (status, normal_body)

        response = post(client)

        assert_refused(response, auth_service.db)

    def test_google_answers_disagree_on_sub_gets_401(self, client, google, auth_service):
        google.answers["userinfo"] = (200, good_userinfo(sub="a-different-google-account"))

        response = post(client)

        assert_refused(response, auth_service.db)

    def test_google_answers_disagree_on_email_gets_401(self, client, google, auth_service):
        google.answers["userinfo"] = (200, good_userinfo(email="someone-else@example.com"))

        response = post(client)

        assert_refused(response, auth_service.db)

    @pytest.mark.parametrize("kind", ["tokeninfo", "userinfo"])
    def test_non_json_answer_gets_401(self, client, google, auth_service, kind):
        google.answers[kind] = (200, "<html>Service temporarily unavailable</html>")

        response = post(client)

        assert_refused(response, auth_service.db)

    def test_token_never_appears_in_a_url(self, client, google):
        response = post(client)

        assert response.status_code == 200, response.text
        assert google.requests, "Google was not called"
        for request in google.requests:
            assert GOOGLE_TOKEN not in str(request.url)
        (tokeninfo,) = google.calls("tokeninfo")
        assert tokeninfo.method == "POST"
        assert GOOGLE_TOKEN in tokeninfo.content.decode()
        (userinfo,) = google.calls("userinfo")
        assert userinfo.headers["Authorization"] == f"Bearer {GOOGLE_TOKEN}"

    def test_database_error_gives_generic_500(self, client, auth_service):
        auth_service.db = FakeDB(fail_with=RuntimeError("connection to db-host-7 refused"))

        response = post(client)

        assert response.status_code == 500
        assert "db-host-7" not in response.text
        assert "RuntimeError" not in response.text

    @pytest.mark.parametrize("path", [
        "/admin/fix-test-user-videos",
        "/debug/authorizer-status",
        "/debug/validate-token",
    ])
    def test_removed_route_is_gone(self, path):
        from app.routes.auth import router

        assert path not in {route.path for route in router.routes}

    def test_debug_defaults_to_false(self, env):
        from app.settings import Settings, get_settings

        assert Settings.model_fields["debug"].default is False
        assert get_settings().debug is False


# ---------------------------------------------------------------------------
# Added after review
# ---------------------------------------------------------------------------

class TestReviewAdditions:

    def test_google_verify_route_is_gone(self, client):
        from app.routes.auth import router
        from app.services.auth_service import AuthService

        assert "/google/verify" not in {route.path for route in router.routes}
        response = client.post("/api/auth/google/verify", json={"id_token": "anything"})
        assert response.status_code in (404, 405)
        # Its helpers had no other caller and were removed with it.
        assert not hasattr(AuthService, "verify_google_id_token")
        assert not hasattr(AuthService, "authenticate_extension")

    def test_tokeninfo_saying_unverified_email_gets_401(self, client, google, auth_service):
        google.answers["tokeninfo"] = (200, good_tokeninfo(email_verified="false"))

        response = post(client)

        assert_refused(response, auth_service.db)

    @pytest.mark.parametrize("kind,overrides", [
        ("tokeninfo", {"aud": [OUR_CLIENT_ID], "azp": MISSING}),
        ("tokeninfo", {"sub": MISSING}),
        ("userinfo", {"sub": MISSING}),
        ("userinfo", {"email": MISSING}),
        ("userinfo", {"email_verified": 1}),
    ], ids=["aud-as-list", "tokeninfo-no-sub", "userinfo-no-sub", "userinfo-no-email", "verified-as-1"])
    def test_other_malformed_google_answers_get_401(self, client, google, auth_service, kind, overrides):
        build = good_tokeninfo if kind == "tokeninfo" else good_userinfo
        google.answers[kind] = (200, build(**overrides))

        response = post(client)

        assert_refused(response, auth_service.db)

    @pytest.mark.parametrize("kind", ["tokeninfo", "userinfo"])
    def test_answer_that_is_not_an_object_gets_401(self, client, google, auth_service, kind):
        google.answers[kind] = (200, ["not", "an", "object"])

        response = post(client)

        assert_refused(response, auth_service.db)

    @pytest.mark.parametrize("token", [None, "", "   "], ids=["none", "empty", "spaces"])
    @pytest.mark.asyncio
    async def test_verifier_refuses_blank_token_without_calling_google(self, env, google, token):
        # The route already refuses these; the verifier must too, on its own.
        from app.services.auth_service import AuthService

        result = await AuthService().verify_google_access_token(token)

        assert result["success"] is False
        assert google.requests == []

    def test_connection_error_gets_401(self, client, google, auth_service):
        google.errors["tokeninfo"] = httpx.ConnectError

        response = post(client)

        assert_refused(response, auth_service.db)

    @pytest.mark.parametrize("verified", [False, "false", MISSING], ids=["false", "string-false", "missing"])
    @pytest.mark.asyncio
    async def test_oauth_callback_refuses_unverified_email(self, env, google, verified):
        from app.services.auth_service import AuthService

        service = AuthService()
        service.google_client_id = OUR_CLIENT_ID
        service.google_client_secret = "test-client-secret"
        service.db = FakeDB([make_user(GOOGLE_EMAIL)])
        google_user = {"id": GOOGLE_SUB, "email": GOOGLE_EMAIL, "given_name": "Olive"}
        if verified is not MISSING:
            google_user["verified_email"] = verified
        self._answer_code_exchange(google, google_user)

        result = await service.google_oauth_callback(code="code", redirect_uri="http://localhost/cb")

        assert result["success"] is False
        assert "access_token" not in result
        assert service.db.writes == []

    @pytest.mark.asyncio
    async def test_oauth_callback_accepts_verified_email(self, env, google, emails):
        from app.services.auth_service import AuthService

        service = AuthService()
        service.google_client_id = OUR_CLIENT_ID
        service.google_client_secret = "test-client-secret"
        service.db = FakeDB([make_user(GOOGLE_EMAIL)])
        self._answer_code_exchange(google, {
            "id": GOOGLE_SUB, "email": GOOGLE_EMAIL, "verified_email": True,
        })

        result = await service.google_oauth_callback(code="code", redirect_uri="http://localhost/cb")

        assert result["success"] is True
        assert [w[2] for w in service.db.writes] == [{"google_id": GOOGLE_SUB}]

    @staticmethod
    def _answer_code_exchange(google, google_user):
        def handle(request):
            google.requests.append(request)
            url = str(request.url)
            if url == "https://oauth2.googleapis.com/token":
                return httpx.Response(200, json={"access_token": "google-access-token"})
            if url == "https://www.googleapis.com/oauth2/v2/userinfo":
                return httpx.Response(200, json=google_user)
            return httpx.Response(599, text="unexpected URL")
        google.handle = handle

    def test_schema_not_served_when_debug_off(self, env):
        import app.main as main_module

        try:
            env.setenv("DEBUG", "true")
            reset_settings()
            main_module = importlib.reload(main_module)
            on = TestClient(main_module.app).get("/openapi.json")
            assert on.status_code == 200 and "openapi" in on.json()
        finally:
            env.delenv("DEBUG", raising=False)
            reset_settings()
            main_module = importlib.reload(main_module)

        assert main_module.app.openapi_url is None
        assert main_module.app.docs_url is None
        assert main_module.app.redoc_url is None
        for path in ("/openapi.json", "/docs", "/redoc"):
            off = TestClient(main_module.app).get(path)
            # 404 without the dashboard; 200 with {"detail": "Not Found"}
            # from the dashboard's catch-all route when it is served.
            assert off.status_code == 404 or off.json() == {"detail": "Not Found"}
            assert "openapi" not in off.text and "swagger" not in off.text.lower()
