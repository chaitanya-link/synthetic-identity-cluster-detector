from engine.generator import generate


def test_deterministic_for_same_seed():
    assert generate(seed=7) == generate(seed=7)


def test_different_seed_differs():
    assert generate(seed=1) != generate(seed=2)


def test_total_and_unique_ids():
    data = generate()
    assert len(data) == 505
    assert len({a["app_id"] for a in data}) == len(data)


def test_device_farm_shares_device_but_not_names():
    farm = [a for a in generate() if a["group"] == "device_farm-1"]
    assert len({a["device_id"] for a in farm}) == 1
    assert len({a["name"] for a in farm}) > 1


def test_chained_ring_has_no_single_shared_identifier():
    ring = [a for a in generate() if a["group"] == "chained-1"]
    assert len(ring) == 5
    for field in ("phone", "device_id", "bank_account"):
        assert len({a[field] for a in ring}) > 1


def test_office_shares_ip_but_is_genuine():
    office = [a for a in generate() if a["group"] == "office-1"]
    assert len({a["ip"] for a in office}) == 1
    assert all(a["label"] == "genuine" for a in office)


def test_family_shares_device_and_surname_but_is_genuine():
    family = [a for a in generate() if a["group"] == "family-1"]
    assert len({a["device_id"] for a in family}) == 1
    assert len({a["name"].split()[-1] for a in family}) == 1
    assert all(a["label"] == "genuine" for a in family)