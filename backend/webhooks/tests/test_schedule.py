from datetime import UTC, datetime, timedelta

import pytest
from django.conf import settings

from webhooks.schedule import next_attempt_at, retry_delay

EXPECTED = [
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=2),
    timedelta(hours=4),
    timedelta(hours=8),
]


@pytest.mark.parametrize(('retry', 'delay'), enumerate(EXPECTED, start=1))
def test_retry_delays_follow_the_schedule(retry: int, delay: timedelta) -> None:
    assert retry_delay(retry, jitter=False) == delay


@pytest.mark.parametrize('retry', [8, 9, 25])
def test_delays_cap_at_8_hours(retry: int) -> None:
    assert retry_delay(retry, jitter=False) == timedelta(hours=8)


def test_jitter_stays_within_10_percent() -> None:
    for _ in range(200):
        assert timedelta(minutes=54) <= retry_delay(4) <= timedelta(minutes=66)


def test_gives_up_after_7_days_and_about_27_attempts() -> None:
    first = datetime(2026, 1, 1, tzinfo=UTC)
    attempts = [first]
    while (later := next_attempt_at(first, attempts[-1], retry=len(attempts), jitter=False)) is not None:
        attempts.append(later)

    assert timedelta(days=7) == settings.WEBHOOK_GIVE_UP_AFTER
    assert attempts[-1] - first <= settings.WEBHOOK_GIVE_UP_AFTER
    assert len(attempts) == 27
