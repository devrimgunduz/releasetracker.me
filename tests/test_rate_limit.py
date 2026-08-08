from app.rate_limit import SlidingWindowRateLimiter


def test_allows_up_to_max_attempts_then_blocks():
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False  # 4th within the window is blocked


def test_keys_are_independent():
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False
    assert limiter.allow("5.6.7.8") is True  # different key, unaffected


def test_reset_clears_history():
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=60)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False
    limiter.reset("1.2.3.4")
    assert limiter.allow("1.2.3.4") is True


def test_old_attempts_age_out_of_the_window():
    limiter = SlidingWindowRateLimiter(max_attempts=1, window_seconds=0.05)
    assert limiter.allow("1.2.3.4") is True
    assert limiter.allow("1.2.3.4") is False
    import time

    time.sleep(0.1)
    assert limiter.allow("1.2.3.4") is True  # window has expired
