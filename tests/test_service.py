import pytest

from engine.service import Store, ValidationError, build_candidate

STORE = Store()
GOOD = dict(name="Test User", phone="5551112222", device_id="dev_x1", bank_account="123456789012")


def example(example_id):
    return next(e for e in STORE.examples() if e["id"] == example_id)


# ---- views ----
def test_health_and_overview():
    assert STORE.health() == {"status": "ok", "applications": 505}
    o = STORE.overview()
    assert o["applications"] == 505 and o["clusters"] == 11
    assert o["flagged_clusters"] == 8 and o["blocked_clusters"] == 6
    assert o["flagged_applications"] == 41 and o["ignored_hubs"] == 2


def test_clusters_sorted_by_score_and_headlined():
    rows = STORE.clusters()
    assert [r["score"] for r in rows] == sorted((r["score"] for r in rows), reverse=True)
    assert all(r["headline"] for r in rows)


def test_cluster_detail_graph_and_missing():
    row = next(r for r in STORE.clusters() if r["truth"]["scenario"] == "device_farm-1")
    d = STORE.cluster_detail(row["cluster_id"])
    assert len(d["nodes"]) == row["size"] == 5
    assert len(d["edges"]) == 4 and {e["field"] for e in d["edges"]} == {"device_id"}
    assert STORE.cluster_detail("C999") is None


def test_api_views_never_leak_ground_truth_fields_on_nodes():
    d = STORE.cluster_detail(STORE.clusters()[0]["cluster_id"])
    for node in d["nodes"]:
        assert "label" not in node and "group" not in node


def test_hubs_report_the_office_ips():
    assert sorted(h["count"] for h in STORE.hubs()) == [24, 28]


def test_metrics_shape():
    m = STORE.metrics()
    assert m["easy"]["metrics"]["recall"] == 1.0
    assert m["hard"]["metrics"]["precision"] < 1.0


# ---- demo examples through the dry-run scorer ----
def test_four_examples_with_expected_outcomes():
    ids = [e["id"] for e in STORE.examples()]
    assert ids == ["mule", "device", "family", "clean"]
    for e in STORE.examples():
        r = STORE.score_candidate(e["payload"])
        assert r["decision"] == e["expect"], e["id"]


def test_reused_mule_account_flips_from_approve_to_block_with_graph():
    r = STORE.score_candidate(example("mule")["payload"])
    assert r["alone"] == "approve" and r["decision"] == "block" and r["linked"]
    assert r["cluster"]["cluster_id"] == "preview"
    new_nodes = [n for n in r["cluster"]["nodes"] if n["is_new"]]
    assert len(new_nodes) == 1 and new_nodes[0]["app_id"] == "NEW"
    assert len(r["merged"]) == 1 and r["merged"][0]["decision"] == "block"
    assert "bank account" in r["message"]


def test_family_member_joins_household_and_stays_approved():
    r = STORE.score_candidate(example("family")["payload"])
    assert r["linked"] and r["decision"] == "approve"
    texts = " ".join(x["text"] for x in r["cluster"]["reasons"])
    assert "share one surname" in texts


def test_clean_applicant_is_not_linked():
    r = STORE.score_candidate(example("clean")["payload"])
    assert r["linked"] is False and r["cluster"] is None and r["decision"] == "approve"


def test_scoring_is_a_dry_run_and_stores_nothing():
    before = STORE.health()["applications"]
    for _ in range(3):
        STORE.score_candidate(example("mule")["payload"])
    assert STORE.health()["applications"] == before
    assert STORE.overview()["flagged_clusters"] == 8


def test_office_ip_alone_does_not_link_a_candidate():
    office_ip = STORE.hubs()[0]["value"]
    payload = dict(GOOD, ip=office_ip)
    assert STORE.score_candidate(payload)["linked"] is False


# ---- validation ----
@pytest.mark.parametrize("missing", ["name", "phone", "device_id", "bank_account"])
def test_required_fields(missing):
    payload = {k: v for k, v in GOOD.items() if k != missing}
    with pytest.raises(ValidationError, match=missing):
        build_candidate(payload)


def test_blank_required_field_rejected():
    with pytest.raises(ValidationError):
        build_candidate(dict(GOOD, name="   "))


@pytest.mark.parametrize("payload", [[], "text", 5, None])
def test_body_must_be_an_object(payload):
    with pytest.raises(ValidationError):
        build_candidate(payload)


@pytest.mark.parametrize("bad", [
    dict(timestamp="not-a-date"),
    dict(timestamp=12345),
    dict(loan_amount="abc"),
    dict(loan_amount=5),
    dict(name="x" * 200),
    dict(phone=True),
])
def test_bad_values_rejected(bad):
    with pytest.raises(ValidationError):
        build_candidate(dict(GOOD, **bad))


def test_timezone_aware_timestamp_is_normalised():
    c = build_candidate(dict(GOOD, timestamp="2026-09-20T10:00:00+05:30"))
    assert c["timestamp"] == "2026-09-20T04:30:00"
    STORE.score_candidate(dict(GOOD, timestamp="2026-09-20T10:00:00Z"))   # must not crash


def test_numeric_phone_is_accepted_as_text():
    assert build_candidate(dict(GOOD, phone=9876543210))["phone"] == "9876543210"