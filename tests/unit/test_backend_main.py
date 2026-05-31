import asyncio

from fastapi.testclient import TestClient

from backend.main import app, cancel_background_tasks
from src.utils.config import get_config


def test_cancel_background_tasks_cancels_pending_tasks():
    async def _runner():
        async def _sleep_forever():
            await asyncio.sleep(60)

        task = asyncio.create_task(_sleep_forever(), name="test-sleeper")
        await cancel_background_tasks([task])
        assert task.cancelled()

    asyncio.run(_runner())


def test_cors_origins_are_an_explicit_allow_list_never_wildcard():
    """Security invariant: CORS is mounted with allow_credentials=True, so the
    resolved origins must stay an explicit allow-list and never become "*"
    (a wildcard + credentials combo is rejected by browsers and is unsafe)."""
    origins = get_config()["cors_origins"]
    assert isinstance(origins, list) and origins, "cors_origins must be a non-empty list"
    assert "*" not in origins, f"wildcard origin is unsafe with credentials: {origins}"
    assert all(o.startswith(("http://", "https://")) for o in origins), origins
    assert "http://localhost:3000" in origins


def test_cors_preflight_reflects_allowed_origin_and_rejects_others():
    """An allowed localhost origin is reflected on a CORS preflight; an
    arbitrary origin is not -- proving the allow-list is not a wildcard."""
    client = TestClient(app)

    allowed = client.options(
        "/",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:3000"
    # With credentials enabled the server must echo the exact origin, never "*".
    assert allowed.headers.get("access-control-allow-credentials") == "true"

    rejected = client.options(
        "/",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert rejected.headers.get("access-control-allow-origin") != "*"
    assert rejected.headers.get("access-control-allow-origin") != "https://evil.example.com"
