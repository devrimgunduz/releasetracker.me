import pytest
from fastapi import HTTPException

from app.csrf import SESSION_KEY, csrf_context, get_csrf_token, verify_csrf


class FakeRequest:
    """Minimal stand-in for Starlette's Request: only `.session` is used by
    the code under test, so we avoid spinning up a full ASGI request."""

    def __init__(self, session: dict | None = None):
        self.session = session if session is not None else {}


def test_get_csrf_token_creates_and_persists():
    req = FakeRequest()
    token = get_csrf_token(req)
    assert token and len(token) > 20
    assert req.session[SESSION_KEY] == token
    # Calling again returns the same token rather than rotating it.
    assert get_csrf_token(req) == token


def test_csrf_context_exposes_token_for_templates():
    req = FakeRequest()
    ctx = csrf_context(req)
    assert ctx == {"csrf_token": req.session[SESSION_KEY]}


@pytest.mark.asyncio
async def test_verify_csrf_accepts_matching_token():
    req = FakeRequest({SESSION_KEY: "abc123"})
    await verify_csrf(req, csrf_token="abc123")  # should not raise


@pytest.mark.asyncio
async def test_verify_csrf_rejects_mismatched_token():
    req = FakeRequest({SESSION_KEY: "abc123"})
    with pytest.raises(HTTPException) as exc:
        await verify_csrf(req, csrf_token="wrong")
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_verify_csrf_rejects_when_no_session_token():
    req = FakeRequest({})  # e.g. session expired or was cleared
    with pytest.raises(HTTPException) as exc:
        await verify_csrf(req, csrf_token="anything")
    assert exc.value.status_code == 403
