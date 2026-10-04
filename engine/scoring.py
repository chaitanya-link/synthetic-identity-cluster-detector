"""Explainable risk scoring for clusters.

Each signal adds points and a plain-English reason, so every decision can be
explained to a human reviewer. The output is a RECOMMENDATION:
approve / review / block. A person confirms it.

Signals (max points): cluster size (30), strongest shared identifier plus any
extra identifier types in a chain (35), diversity of surnames (20), and how
tightly the applications were submitted in time (25). The total is capped at 100.

Never reads the ground-truth fields `label` or `group`.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime

from engine.clustering import Cluster, ClusterResult

BLOCK_AT = 80
REVIEW_AT = 50

LINK_POINTS = {"bank_account": 25, "device_id": 20, "phone": 15}
LINK_LABEL = {"bank_account": "bank account", "device_id": "device", "phone": "phone number"}
EXTRA_LINK_POINTS = 5
EXTRA_LINK_CAP = 10
MAX_SIZE_POINTS = 30
MAX_NAME_POINTS = 20


@dataclass
class ScoredCluster:
    cluster_id: str
    score: int
    decision: str
    members: list[str]
    link_fields: list[str]
    oversized: bool
    reasons: list[dict]          # {"signal", "points", "text"}

    def to_dict(self) -> dict:
        return asdict(self)


def decide(score: int) -> str:
    if score >= BLOCK_AT:
        return "block"
    if score >= REVIEW_AT:
        return "review"
    return "approve"


def _fmt_span(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return "under a minute"
    if minutes < 60:
        return f"{minutes} min"
    hours, mins = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {mins:02d}m"
    return f"{hours // 24} days"


def _reason(signal: str, points: int, text: str) -> dict:
    return {"signal": signal, "points": points, "text": text}


def score_cluster(cluster: Cluster, apps_by_id: dict[str, dict]) -> ScoredCluster:
    apps = [apps_by_id[m] for m in cluster.members]
    n = len(apps)
    reasons: list[dict] = []

    # 1. size
    size_pts = min(n - 1, 6) * 5
    reasons.append(_reason("size", size_pts, f"{n} applications are linked together"))

    # 2. strongest shared identifier (+ extra identifier types in a chain)
    fields = sorted(cluster.link_fields, key=lambda f: -LINK_POINTS[f])
    if fields:
        link_pts = LINK_POINTS[fields[0]]
        extra_pts = min(EXTRA_LINK_CAP, EXTRA_LINK_POINTS * (len(fields) - 1))
        labels = [LINK_LABEL[f] for f in fields]
        if len(fields) == 1:
            text = f"linked through a shared {labels[0]}"
        else:
            text = "linked in a chain through " + ", ".join(labels[:-1]) + f" and {labels[-1]}"
        reasons.append(_reason("link", link_pts + extra_pts, text))

    # 3. surname diversity: many different surnames on one identifier is suspicious
    surnames = {a["name"].split()[-1].lower() for a in apps}
    name_pts = round(MAX_NAME_POINTS * len(surnames) / n)
    if len(surnames) == 1:
        text = f"all {n} applicants share one surname (looks like a household)"
    else:
        text = f"{len(surnames)} different surnames across {n} applications"
    reasons.append(_reason("names", name_pts, text))

    # 4. time burst: fraud rings tend to submit in a short window
    times = [datetime.fromisoformat(a["timestamp"]) for a in apps]
    span = (max(times) - min(times)).total_seconds()
    hours = span / 3600
    if hours <= 6:
        burst_pts, text = 25, f"all submitted within {_fmt_span(span)}"
    elif hours <= 24:
        burst_pts, text = 12, f"submitted within {_fmt_span(span)}"
    elif hours <= 72:
        burst_pts, text = 5, f"submitted over {_fmt_span(span)}"
    else:
        burst_pts, text = 0, f"spread over {_fmt_span(span)}, no burst"
    reasons.append(_reason("burst", burst_pts, text))

    score = min(100, sum(r["points"] for r in reasons))

    # 5. a cluster this large may be unrelated people chained together
    if cluster.oversized and score < REVIEW_AT:
        reasons.append(_reason(
            "oversized", REVIEW_AT - score,
            f"unusually large cluster ({n}); may chain unrelated people, needs manual review",
        ))
        score = REVIEW_AT

    return ScoredCluster(
        cluster_id=cluster.cluster_id,
        score=score,
        decision=decide(score),
        members=list(cluster.members),
        link_fields=list(cluster.link_fields),
        oversized=cluster.oversized,
        reasons=reasons,
    )


def score_all(applications: list[dict], result: ClusterResult) -> list[ScoredCluster]:
    apps_by_id = {a["app_id"]: a for a in applications}
    scored = [score_cluster(c, apps_by_id) for c in result.clusters]
    scored.sort(key=lambda s: (-s.score, s.cluster_id))
    return scored