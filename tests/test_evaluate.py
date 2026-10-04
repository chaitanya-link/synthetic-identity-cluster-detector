from engine.clustering import build_clusters
from engine.evaluate import group_outcomes, metrics, run_evaluation
from engine.generator import generate
from engine.hard_cases import build_hard_dataset, hard_cases
from engine.scoring import score_all

HARD_GROUPS = {
    "hard-slow-household-ring",
    "hard-household-same-day",
    "hard-cyber-cafe",
    "hard-invisible-ring",
}


def evaluate(data):
    scored = score_all(data, build_clusters(data))
    return metrics(data, scored), {g["group"]: g for g in group_outcomes(data, scored)}


# ---- easy set ----
def test_easy_set_scores_perfectly_and_every_scenario_is_correct():
    m, groups = evaluate(generate())
    assert m["precision"] == 1.0 and m["recall"] == 1.0 and m["f1"] == 1.0
    assert all(g["correct"] for g in groups.values())


def test_confusion_matrix_adds_up():
    for data in (generate(), build_hard_dataset()):
        m, _ = evaluate(data)
        assert m["tp"] + m["fp"] + m["fn"] + m["tn"] == m["applications"]
        assert m["tp"] + m["fn"] == m["fraud_applications"]
        assert m["tp"] + m["fp"] == m["flagged"]


def test_blocked_is_a_subset_of_flagged():
    m, _ = evaluate(generate())
    assert m["blocked"] <= m["flagged"]


# ---- hard set: the honest limits ----
def test_hard_cases_are_labelled_and_have_unique_ids():
    rows = hard_cases()
    assert {r["group"] for r in rows} == HARD_GROUPS
    assert len({r["app_id"] for r in rows}) == len(rows)
    base_ids = {a["app_id"] for a in generate()}
    assert base_ids.isdisjoint(r["app_id"] for r in rows)


def test_detector_misses_a_slow_ring_that_looks_like_a_household():
    _, groups = evaluate(build_hard_dataset())
    g = groups["hard-slow-household-ring"]
    assert g["truth"] == "fraud" and g["decision"] == "approve" and not g["correct"]


def test_detector_cannot_see_a_ring_with_no_shared_identifier():
    _, groups = evaluate(build_hard_dataset())
    g = groups["hard-invisible-ring"]
    assert g["truth"] == "fraud" and g["decision"] == "not clustered" and not g["correct"]


def test_detector_wrongly_blocks_a_same_day_household_with_different_surnames():
    _, groups = evaluate(build_hard_dataset())
    g = groups["hard-household-same-day"]
    assert g["truth"] == "genuine" and g["decision"] == "block" and not g["correct"]


def test_detector_wrongly_flags_a_cyber_cafe_device():
    _, groups = evaluate(build_hard_dataset())
    g = groups["hard-cyber-cafe"]
    assert g["truth"] == "genuine" and g["decision"] in ("review", "block") and not g["correct"]


def test_hard_set_lowers_both_precision_and_recall_but_easy_scenarios_stay_correct():
    m, groups = evaluate(build_hard_dataset())
    assert m["precision"] < 1.0 and m["recall"] < 1.0
    for name, g in groups.items():
        if name not in HARD_GROUPS:
            assert g["correct"], name


# ---- plumbing ----
def test_run_evaluation_shape_and_determinism():
    a, b = run_evaluation(), run_evaluation()
    assert a == b
    assert set(a) == {"easy", "hard"}
    assert set(a["easy"]) == {"metrics", "groups"}