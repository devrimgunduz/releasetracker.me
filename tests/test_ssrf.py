import pytest

from app.ssrf import SSRFError, validate_public_url


def test_rejects_loopback():
    with pytest.raises(SSRFError):
        validate_public_url("http://127.0.0.1/x")


def test_rejects_link_local_metadata_address():
    with pytest.raises(SSRFError):
        validate_public_url("http://169.254.169.254/latest/meta-data/")


def test_rejects_private_range():
    with pytest.raises(SSRFError):
        validate_public_url("http://10.0.0.5/x")


def test_rejects_non_http_scheme():
    with pytest.raises(SSRFError):
        validate_public_url("file:///etc/passwd")


def test_rejects_unresolvable_host():
    with pytest.raises(SSRFError):
        validate_public_url("http://this-host-should-not-resolve.invalid/x")


def test_allows_public_host():
    # api.github.com is public; this only exercises DNS resolution, no network I/O.
    validate_public_url("https://api.github.com/")


def test_pick_public_ip_rejects_private(monkeypatch):
    # DNS rebinding: the name resolves to a private address at connect time.
    monkeypatch.setattr("app.ssrf._resolve", lambda host: ["10.0.0.5"])
    with pytest.raises(SSRFError):
        from app.ssrf import pick_public_ip

        pick_public_ip("rebind.example.com")


def test_pick_public_ip_rejects_mixed_answers(monkeypatch):
    # A public answer padded alongside a private one must still be refused.
    monkeypatch.setattr("app.ssrf._resolve", lambda host: ["93.184.216.34", "127.0.0.1"])
    from app.ssrf import pick_public_ip

    with pytest.raises(SSRFError):
        pick_public_ip("mixed.example.com")


def test_pick_public_ip_returns_public(monkeypatch):
    monkeypatch.setattr("app.ssrf._resolve", lambda host: ["93.184.216.34"])
    from app.ssrf import pick_public_ip

    assert pick_public_ip("public.example.com") == "93.184.216.34"


@pytest.mark.asyncio
async def test_guard_transport_pins_to_validated_ip(monkeypatch):
    import httpx

    from app.ssrf import SSRFGuardTransport

    seen = {}

    def handler(req):
        seen["host"] = req.url.host
        seen["header_host"] = req.headers.get("host")
        seen["sni"] = req.extensions.get("sni_hostname")
        return httpx.Response(200, text="ok")

    monkeypatch.setattr("app.ssrf._resolve", lambda host: ["93.184.216.34"])
    transport = SSRFGuardTransport(httpx.MockTransport(handler))
    async with httpx.AsyncClient(transport=transport) as client:
        await client.get("https://public.example.com/path")

    assert seen["host"] == "93.184.216.34"          # connection pinned to the IP
    assert seen["header_host"] == "public.example.com"  # Host header preserved
    assert seen["sni"] == "public.example.com"          # TLS verified vs real host


@pytest.mark.asyncio
async def test_guard_transport_blocks_rebind(monkeypatch):
    import httpx

    from app.ssrf import SSRFGuardTransport

    monkeypatch.setattr("app.ssrf._resolve", lambda host: ["169.254.169.254"])
    transport = SSRFGuardTransport(httpx.MockTransport(lambda req: httpx.Response(200)))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(SSRFError):
            await client.get("https://metadata.example.com/latest/meta-data/")
