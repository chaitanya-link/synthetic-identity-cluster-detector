from datetime import datetime, timedelta

from engine.clustering import build_clusters
from engine.generator import generate
from engine.scoring import BLOCK_AT, REVIEW_AT, decide, score_all

BASE = datetime(2026, 9, 10, 12, 0, 0)


def scored_by_group(data, scored):
    group = {a["app_id"]: a["group"] for a in data}
    out = {}
    for s in scored:
        out.setdefault(group[s.members[0]], []).append(s)
    return out


def device_cluster(names, minutes_apart, **cluster_kw):
    """Small synthetic cluster: apps sharing one device, spaced `minutes_apart` minutes."""
    apps = [
        dict(app_id=f"X{i:03d}", name=name, phone=f"p{i}", device_id="shared",
             bank_account=f"b{i}", ip=f"ip{i}",
             timestamp=(BASE + timedelta(minutes=i * minutes_apart)).isoformat())
        for i, name in enumerate(names)
    ]
    result = build_clusters(apps, **cluster_kw)
    return score_all(apps, result)[0]


# ---- on the generated data ----
def test_flagged_applications_are_exactly_the_planted_fraud():
    data = generate()
    scored = score_all(data, build_clusters(data))
    flagged = {m for s in scored if s.decision != "approve" for m in s.members}
    fraud = {a["app_id"] for a in data if a["label"] == "fraud"}
    assert flagged == fraud


def test_mules_chains_and_device_farms_are_blocked():
    data = generate()
    groups = scored_by_group(data, score_all(data, build_clusters(data)))
    for name in ("mule-1", "mule-2", "chained-1", "chained-2", "device_farm-1", "device_farm-2"):
        assert [s.decision for s in groups[name]] == ["block"], name


def test_sim_farm_clusters_go_to_review():
    data = generate()
    groups = scored_by_group(data, score_all(data, build_clusters(data)))
    assert len(groups["sim_farm-1"]) == 2
    assert all(s.decision == "review" for s in groups["sim_farm-1"])


def test_families_are_approved_with_a_reason():
    data = generate()
    groups = scored_by_group(data, score_all(data, build_clusters(data)))
    for name in ("family-1", "family-2", "family-3"):
        (s,) = groups[name]
        assert s.decision == "approve"
        texts = " ".join(r["text"] for r in s.reasons)
        assert "share one surname" in texts and "no burst" in texts


def test_result_holds_across_several_seeds():
    for seed in range(1, 11):
        data = generate(seed=seed)
        scored = score_all(data, build_clusters(data))
        flagged = {m for s in scored if s.decision != "approve" for m in s.members}
        assert flagged == {a["app_id"] for a in data if a["label"] == "fraud"}, seed


def test_scores_are_sorted_highest_first():
    data = generate()
    scores = [s.score for s in score_all(data, build_clusters(data))]
    assert scores == sorted(scores, reverse=True)


def test_scoring_ignores_ground_truth_fields():
    data = generate()
    stripped = [{k: v for k, v in a.items() if k not in ("label", "group")} for a in data]
    a = [(s.cluster_id, s.score) for s in score_all(data, build_clusters(data))]
    b = [(s.cluster_id, s.score) for s in score_all(stripped, build_clusters(stripped))]
    assert a == b


# ---- explainability ----
def test_score_equals_sum_of_reason_points_capped_at_100():
    data = generate()
    for s in score_all(data, build_clusters(data)):
        assert s.score == min(100, sum(r["points"] for r in s.reasons))
        assert 0 <= s.score <= 100


def test_every_reason_has_text_and_a_known_signal():
    data = generate()
    for s in score_all(data, build_clusters(data)):
        assert len(s.reasons) >= 4
        for r in s.reasons:
            assert r["text"] and r["signal"] in {"size", "link", "names", "burst", "oversized"}


# ---- individual signals ----
def test_tight_burst_scores_higher_than_slow_spread():
    names = ["Aarav Sharma", "Priya Verma", "Rohan Reddy"]
    fast = device_cluster(names, minutes_apart=10)
    slow = device_cluster(names, minutes_apart=60 * 24 * 10)
    assert fast.score > slow.score
    assert any("all submitted within" in r["text"] for r in fast.reasons)
    assert any("no burst" in r["text"] for r in slow.reasons)


def test_different_surnames_score_higher_than_one_household():
    mixed = device_cluster(["Aarav Sharma", "Priya Verma", "Rohan Reddy"], minutes_apart=10)
    household = device_cluster(["Aarav Sharma", "Priya Sharma", "Rohan Sharma"], minutes_apart=10)
    assert mixed.score > household.score


def test_oversized_cluster_is_never_auto_approved():
    names = ["Aarav Sharma", "Priya Sharma", "Rohan Sharma"]
    s = device_cluster(names, minutes_apart=60 * 24 * 20, max_cluster_size=2)
    assert s.oversized is True
    assert s.score == REVIEW_AT and s.decision == "review"
    assert s.reasons[-1]["signal"] == "oversized"


def test_decision_thresholds():
    assert decide(REVIEW_AT - 1) == "approve"
    assert decide(REVIEW_AT) == "review"
    assert decide(BLOCK_AT - 1) == "review"
    assert decide(BLOCK_AT) == "block"