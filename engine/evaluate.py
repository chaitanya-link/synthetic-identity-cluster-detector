"""Evaluation against ground truth, on an easy set and a hard set.

Ground truth (`label`, `group`) is read ONLY here, to grade the detector.
An application counts as "flagged" when its cluster is scored review or block.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from engine.clustering import build_clusters
from engine.generator import generate
from engine.hard_cases import build_hard_dataset
from engine.scoring import ScoredCluster, score_all


def _flagged_ids(scored: list[ScoredCluster]) -> set[str]:
    return {m for s in scored if s.decision != "approve" for m in s.members}


def metrics(data: list[dict], scored: list[ScoredCluster]) -> dict:
    flagged = _flagged_ids(scored)
    blocked = {m for s in scored if s.decision == "block" for m in s.members}
    ids = {a["app_id"] for a in data}
    fraud = {a["app_id"] for a in data if a["label"] == "fraud"}

    tp = len(flagged & fraud)
    fp = len(flagged - fraud)
    fn = len(fraud - flagged)
    tn = len(ids) - tp - fp - fn
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "applications": len(ids),
        "fraud_applications": len(fraud),
        "flagged": len(flagged),
        "blocked": len(blocked),
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def group_outcomes(data: list[dict], scored: list[ScoredCluster]) -> list[dict]:
    """One row per planted scenario: was it treated correctly?"""
    flagged = _flagged_ids(scored)
    decision_of = {m: s.decision for s in scored for m in s.members}
    groups: dict[str, list[dict]] = defaultdict(list)
    for a in data:
        if a["group"]:
            groups[a["group"]].append(a)

    rows = []
    for name, members in sorted(groups.items()):
        label = members[0]["label"]
        ids = [m["app_id"] for m in members]
        share = sum(1 for i in ids if i in flagged) / len(ids)
        top = Counter(decision_of.get(i, "not clustered") for i in ids).most_common(1)[0][0]
        rows.append({
            "group": name,
            "truth": label,
            "size": len(ids),
            "decision": top,
            "flagged_share": round(share, 2),
            "correct": (share >= 0.5) == (label == "fraud"),
        })
    return rows


def _run(data: list[dict]) -> dict:
    scored = score_all(data, build_clusters(data))
    return {"metrics": metrics(data, scored), "groups": group_outcomes(data, scored)}


def run_evaluation(seed: int = 42) -> dict:
    return {"easy": _run(generate(seed=seed)), "hard": _run(build_hard_dataset(seed=seed))}


def _print_report(name: str, result: dict) -> None:
    m = result["metrics"]
    print(f"\n== {name} ==")
    print(f"applications {m['applications']}  fraud {m['fraud_applications']}  "
          f"flagged {m['flagged']}  blocked {m['blocked']}")
    print(f"TP {m['tp']}  FP {m['fp']}  FN {m['fn']}  TN {m['tn']}   "
          f"precision {m['precision']:.3f}  recall {m['recall']:.3f}  F1 {m['f1']:.3f}")
    print(f"{'scenario':<28}{'truth':<9}{'size':<6}{'decision':<14}{'result'}")
    for g in result["groups"]:
        print(f"{g['group']:<28}{g['truth']:<9}{g['size']:<6}{g['decision']:<14}"
              f"{'ok' if g['correct'] else 'WRONG'}")


if __name__ == "__main__":
    report = run_evaluation()
    _print_report("easy set (planted patterns)", report["easy"])
    _print_report("hard set (adversarial cases added)", report["hard"])