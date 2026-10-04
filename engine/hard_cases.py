"""Adversarial cases the detector is EXPECTED to get wrong.

Two are fraud the detector misses, two are innocent people it wrongly flags.
They exist so the evaluation reports honest limits, not just a perfect score
on easy synthetic data. Ground truth (`label`, `group`) is used only by
evaluate.py, never by the detector.
"""
from __future__ import annotations

import random
from dataclasses import asdict
from datetime import timedelta

from engine.generator import FIRST_NAMES, LAST_NAMES, _base_app, _device, _ip, _time, generate


def _row(app, app_id: str) -> dict:
    row = asdict(app)
    row["timestamp"] = app.timestamp.isoformat()
    row["app_id"] = app_id
    return row


def hard_cases(seed: int = 42) -> list[dict]:
    rng = random.Random(seed + 1000)
    apps = []

    # 1. MISS: a ring that slows down and reuses one surname, so it looks like a household
    surname, device, start = rng.choice(LAST_NAMES), _device(rng), _time(rng)
    for i, first in enumerate(rng.sample(FIRST_NAMES, 4)):
        apps.append(_base_app(
            rng, name=f"{first} {surname}", device_id=device, label="fraud",
            group="hard-slow-household-ring", timestamp=start + timedelta(days=6 * i)))

    # 2. FALSE ALARM: a real household with different surnames applying on the same day
    device, ip, start = _device(rng), _ip(rng), _time(rng)
    for first, last in zip(rng.sample(FIRST_NAMES, 4), rng.sample(LAST_NAMES, 4)):
        apps.append(_base_app(
            rng, name=f"{first} {last}", device_id=device, ip=ip,
            group="hard-household-same-day",
            timestamp=start + timedelta(minutes=rng.randint(0, 120))))

    # 3. FALSE ALARM: a cyber cafe device used by 10 strangers over several days
    device, start = _device(rng), _time(rng)
    for _ in range(10):
        apps.append(_base_app(
            rng, device_id=device, group="hard-cyber-cafe",
            timestamp=start + timedelta(hours=rng.randint(0, 6 * 24))))

    # 4. MISS: a ring that shares no identifier at all (fresh phone, device, bank each time)
    start = _time(rng)
    for _ in range(6):
        apps.append(_base_app(
            rng, label="fraud", group="hard-invisible-ring",
            timestamp=start + timedelta(minutes=rng.randint(0, 60))))

    return [_row(app, f"H{n:03d}") for n, app in enumerate(apps, 1)]


def build_hard_dataset(seed: int = 42) -> list[dict]:
    return generate(seed=seed) + hard_cases(seed=seed)