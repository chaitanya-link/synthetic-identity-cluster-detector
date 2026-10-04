"""Synthetic loan-application generator.

Everything here is fake and random. The `label` and `group` fields are ground
truth used ONLY by evaluate.py and the UI explanations. The detector must
never read them.
"""
from __future__ import annotations

import random
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Arjun", "Rohan", "Karan", "Rahul", "Sneha",
    "Priya", "Ananya", "Kavya", "Isha", "Neha", "Pooja", "Meera", "Riya",
    "Sanjay", "Vikram", "Deepak", "Manoj",
]
LAST_NAMES = [
    "Sharma", "Verma", "Reddy", "Nair", "Iyer", "Patel", "Gupta", "Singh",
    "Rao", "Kulkarni", "Shetty", "Mehta", "Das", "Bose", "Menon", "Kapoor",
    "Naidu", "Pillai", "Gowda", "Hegde",
]
EMAIL_DOMAINS = ["mailbox.test", "example.org", "inbox.test"]

BASE_TIME = datetime(2026, 9, 1, 9, 0, 0)
WINDOW_DAYS = 30


@dataclass
class Application:
    name: str
    phone: str
    device_id: str
    ip: str
    bank_account: str
    email: str
    timestamp: datetime
    loan_amount: int
    label: str = "genuine"  # ground truth: "genuine" | "fraud"
    group: str = ""         # ground truth: e.g. "device_farm-1", "family-2"
    app_id: str = ""


# ---------- identifier factories (all random, all fake) ----------
def _phone(rng): return rng.choice("6789") + "".join(rng.choices("0123456789", k=9))
def _device(rng): return "dev_" + "".join(rng.choices("0123456789abcdef", k=10))
def _bank(rng): return "".join(rng.choices("0123456789", k=12))
def _name(rng): return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
def _amount(rng): return rng.randrange(20, 501, 5) * 1000


def _ip(rng):
    return ".".join(str(rng.randint(a, b)) for a, b in ((11, 223), (0, 255), (0, 255), (1, 254)))


def _email(rng, name):
    return f"{name.lower().replace(' ', '.')}{rng.randint(1, 99)}@{rng.choice(EMAIL_DOMAINS)}"


def _time(rng):
    return BASE_TIME + timedelta(minutes=rng.randint(0, WINDOW_DAYS * 24 * 60))


def _base_app(rng, **overrides) -> Application:
    name = overrides.pop("name", None) or _name(rng)
    app = Application(
        name=name, phone=_phone(rng), device_id=_device(rng), ip=_ip(rng),
        bank_account=_bank(rng), email=_email(rng, name),
        timestamp=_time(rng), loan_amount=_amount(rng),
    )
    for key, value in overrides.items():
        setattr(app, key, value)
    return app


# ---------- fraud patterns ----------
def _device_farm(rng, idx, size):
    """Many applicants, one physical device, submitted in a short burst."""
    device, at = _device(rng), _time(rng)
    return [
        _base_app(rng, device_id=device, label="fraud", group=f"device_farm-{idx}",
                  timestamp=at + timedelta(minutes=rng.randint(0, 90)))
        for _ in range(size)
    ]


def _mule_account(rng, idx, size):
    """Many applications paying out to the same bank account."""
    bank, at = _bank(rng), _time(rng)
    return [
        _base_app(rng, bank_account=bank, label="fraud", group=f"mule-{idx}",
                  timestamp=at + timedelta(minutes=rng.randint(0, 180)))
        for _ in range(size)
    ]


def _chained_ring(rng, idx):
    """No single identifier links everyone; only the chain does."""
    phone1, device1, bank1, phone2 = _phone(rng), _device(rng), _bank(rng), _phone(rng)
    at = _time(rng)
    links = [
        dict(phone=phone1),
        dict(phone=phone1, device_id=device1),
        dict(device_id=device1, bank_account=bank1),
        dict(bank_account=bank1, phone=phone2),
        dict(phone=phone2),
    ]
    return [
        _base_app(rng, label="fraud", group=f"chained-{idx}",
                  timestamp=at + timedelta(minutes=rng.randint(0, 240)), **link)
        for link in links
    ]


def _sim_farm(rng, idx, size):
    """A couple of phone numbers reused across many applications, very fast."""
    phones, at = [_phone(rng), _phone(rng)], _time(rng)
    return [
        _base_app(rng, phone=phones[i % 2], label="fraud", group=f"sim_farm-{idx}",
                  timestamp=at + timedelta(minutes=rng.randint(0, 45)))
        for i in range(size)
    ]


# ---------- innocent lookalikes (must NOT be flagged) ----------
def _family(rng, idx):
    """Same surname, shared home device and IP, applications spread over weeks."""
    surname, device, ip = rng.choice(LAST_NAMES), _device(rng), _ip(rng)
    return [
        _base_app(rng, name=f"{first} {surname}", device_id=device, ip=ip,
                  group=f"family-{idx}")
        for first in rng.sample(FIRST_NAMES, 4)
    ]


def _office_nat(rng, idx, size):
    """Unrelated people behind one office or college IP address."""
    ip = _ip(rng)
    return [_base_app(rng, ip=ip, group=f"office-{idx}") for _ in range(size)]


# ---------- public API ----------
def generate(seed: int = 42, n_genuine: int = 400) -> list[dict]:
    rng = random.Random(seed)
    apps = [_base_app(rng) for _ in range(n_genuine)]

    for i, size in enumerate((5, 6), 1):
        apps += _device_farm(rng, i, size)
    for i, size in enumerate((6, 7), 1):
        apps += _mule_account(rng, i, size)
    for i in (1, 2):
        apps += _chained_ring(rng, i)
    apps += _sim_farm(rng, 1, 7)
    for i in (1, 2, 3):
        apps += _family(rng, i)
    for i, size in enumerate((28, 24), 1):
        apps += _office_nat(rng, i, size)

    apps.sort(key=lambda a: a.timestamp)
    for n, app in enumerate(apps, 1):
        app.app_id = f"A{n:04d}"

    rows = []
    for app in apps:
        row = asdict(app)
        row["timestamp"] = app.timestamp.isoformat()
        rows.append(row)
    return rows


if __name__ == "__main__":
    from collections import Counter

    data = generate()
    print(f"{len(data)} applications")
    print(Counter(a["label"] for a in data))
    print("groups:", ", ".join(sorted({a["group"] for a in data if a["group"]})))