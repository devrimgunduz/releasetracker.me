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
