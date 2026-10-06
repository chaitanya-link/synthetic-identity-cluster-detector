"""Service layer: runs the pipeline and builds API-ready views.

Pure Python with no web framework, so it is easy to test. The web layer
(app/main.py) only routes requests to this module.

The public demo is stateless: a submitted application is scored as a dry run
against the dataset and is never stored.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from engine.clustering import Cluster, ClusterResult, build_clusters
from engine.evaluate import run_evaluation
from engine.generator import generate
from engine.scoring import LINK_LABEL, ScoredCluster, score_all

CANDIDATE_ID = "NEW"
MAX_TEXT = 80
NODE_FIELDS = (
    "app_id", "name", "phone", "device_id", "bank_account",
    "ip", "email", "timestamp", "loan_amount",
)


class ValidationError(ValueError):
    """Raised when a submitted application is not valid."""


# ---------- input validation ----------
def _text(payload: dict, key: str, required: bool = True) -> str:
    value = payload.get(key)
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(f"'{key}' is required")
        return ""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValidationError(f"'{key}' must be text")
    text = str(value).strip()
    if len(text) > MAX_TEXT:
        raise ValidationError(f"'{key}' is too long (max {MAX_TEXT} characters)")
    return text


def _timestamp(value) -> datetime:
    if value in (None, ""):
        return datetime.now().replace(microsecond=0)
    if not isinstance(value, str):
        raise ValidationError("'timestamp' must be an ISO date-time string")
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError:
        raise ValidationError("'timestamp' must be an ISO date-time, e.g. 2026-09-20T14:30:00")
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _loan_amount(value) -> int:
    if value in (None, ""):
        return 100_000
    try:
        amount = int(value)
    except (TypeError, ValueError):
        raise ValidationError("'loan_amount' must be a whole number")
    if not 1_000 <= amount <= 10_000_000:
        raise ValidationError("'loan_amount' must be between 1,000 and 10,000,000")
    return amount


def build_candidate(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("request body must be a JSON object")
    return {
        "app_id": CANDIDATE_ID,
        "name": _text(payload, "name"),
        "phone": _text(payload, "phone"),
        "device_id": _text(payload, "device_id"),
        "bank_account": _text(payload, "bank_account"),
        "ip": _text(payload, "ip", required=False),
        "email": _text(payload, "email", required=False),
        "timestamp": _timestamp(payload.get("timestamp")).isoformat(),
        "loan_amount": _loan_amount(payload.get("loan_amount")),
        "label": "live",
        "group": "live",
    }


# ---------- analysis ----------
@dataclass
class Analysis:
    applications: list[dict]
    by_id: dict[str, dict]
    result: ClusterResult
    scored: list[ScoredCluster]
    clusters: dict[str, Cluster]


def analyze(applications: list[dict]) -> Analysis:
    result = build_clusters(applications)
    return Analysis(
        applications=applications,
        by_id={a["app_id"]: a for a in applications},
        result=result,
        scored=score_all(applications, result),
        clusters={c.cluster_id: c for c in result.clusters},
    )


# ---------- views ----------
def _node(app: dict, is_new: bool = False) -> dict:
    node = {key: app.get(key) for key in NODE_FIELDS}
    node["is_new"] = is_new
    return node


def _truth(members: list[str], by_id: dict[str, dict]) -> dict:
    """Synthetic ground truth, shown only as a demo annotation."""
    scenarios = sorted({by_id[m]["group"] for m in members if by_id[m].get("group") not in ("", "live", None)})
    labels = sorted({by_id[m]["label"] for m in members if by_id[m]["label"] != "live"})
    if len(labels) == 1:
        label = labels[0]
    else:
        label = "mixed" if labels else "unknown"
    return {"scenario": ", ".join(scenarios), "label": label}


def _summary(scored: ScoredCluster, by_id: dict[str, dict]) -> dict:
    headline = next((r["text"] for r in scored.reasons if r["signal"] == "link"), "")
    return {
        "cluster_id": scored.cluster_id,
        "score": scored.score,
        "decision": scored.decision,
        "size": len(scored.members),
        "link_fields": scored.link_fields,
        "headline": headline,
        "oversized": scored.oversized,
        "truth": _truth(scored.members, by_id),
    }


def _detail(scored: ScoredCluster, cluster: Cluster, by_id: dict[str, dict]) -> dict:
    return {
        "cluster_id": scored.cluster_id,
        "score": scored.score,
        "decision": scored.decision,
        "oversized": scored.oversized,
        "link_fields": scored.link_fields,
        "reasons": scored.reasons,
        "truth": _truth(scored.members, by_id),
        "nodes": [_node(by_id[m], is_new=(m == CANDIDATE_ID)) for m in scored.members],
        "edges": [
            {"source": l["a"], "target": l["b"], "field": l["field"], "value": l["value"]}
            for l in cluster.links
        ],
    }


class Store:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.analysis = analyze(generate(seed=seed))
        self._evaluation: dict | None = None

    def health(self) -> dict:
        return {"status": "ok", "applications": len(self.analysis.applications)}

    def overview(self) -> dict:
        a = self.analysis
        flagged = [s for s in a.scored if s.decision != "approve"]
        return {
            "applications": len(a.applications),
            "clusters": len(a.scored),
            "flagged_clusters": len(flagged),
            "blocked_clusters": sum(1 for s in a.scored if s.decision == "block"),
            "flagged_applications": sum(len(s.members) for s in flagged),
            "ignored_hubs": len(a.result.hubs),
            "seed": self.seed,
        }

    def clusters(self) -> list[dict]:
        a = self.analysis
        return [_summary(s, a.by_id) for s in a.scored]

    def cluster_detail(self, cluster_id: str) -> dict | None:
        a = self.analysis
        scored = next((s for s in a.scored if s.cluster_id == cluster_id), None)
        if scored is None:
            return None
        return _detail(scored, a.clusters[cluster_id], a.by_id)

    def hubs(self) -> list[dict]:
        return [
            {"field": h["field"], "value": h["value"], "count": h["count"]}
            for h in self.analysis.result.hubs
        ]

    def metrics(self) -> dict:
        if self._evaluation is None:
            self._evaluation = run_evaluation(self.seed)
        return self._evaluation

    def examples(self) -> list[dict]:
        """Ready-made demo payloads built from real identifiers in the dataset."""
        a = self.analysis

        def last_time(s: ScoredCluster) -> datetime:
            return max(datetime.fromisoformat(a.by_id[m]["timestamp"]) for m in s.members)

        def first_app(s: ScoredCluster) -> dict:
            return a.by_id[s.members[0]]

        def fresh(name: str, when: datetime) -> dict:
            return {
                "name": name, "phone": "5550000001", "device_id": "dev_demo000001",
                "bank_account": "999900000001", "ip": "203.0.113.7",
                "loan_amount": 150000, "timestamp": when.replace(microsecond=0).isoformat(),
            }

        blocked = [s for s in a.scored if s.decision == "block"]
        mule = next((s for s in blocked if s.link_fields == ["bank_account"]), None)
        farm = next((s for s in blocked if s.link_fields == ["device_id"]), None)
        family = next((s for s in a.scored if s.decision == "approve" and s.link_fields == ["device_id"]), None)

        out = []
        if mule:
            payload = fresh("Kiran Malhotra", last_time(mule) + timedelta(minutes=15))
            payload["bank_account"] = first_app(mule)["bank_account"]
            out.append({"id": "mule", "label": "Fraudster reuses a known mule account",
                        "expect": "block", "payload": payload})
        if farm:
            payload = fresh("Kiran Malhotra", last_time(farm) + timedelta(minutes=15))
            payload["device_id"] = first_app(farm)["device_id"]
            out.append({"id": "device", "label": "Fraudster reuses a device-farm device",
                        "expect": "block", "payload": payload})
        if family:
            surname = first_app(family)["name"].split()[-1]
            payload = fresh(f"Arjun {surname}", last_time(family) + timedelta(days=2))
            payload["device_id"] = first_app(family)["device_id"]
            out.append({"id": "family", "label": "New family member on the household device",
                        "expect": "approve", "payload": payload})
        out.append({"id": "clean", "label": "Brand-new clean applicant", "expect": "approve",
                    "payload": fresh("Meera Joshi", datetime.now())})
        return out

    def score_candidate(self, payload) -> dict:
        """Dry run: score one new application against the dataset. Nothing is stored."""
        candidate = build_candidate(payload)
        base = self.analysis
        analysis = analyze(base.applications + [candidate])
        scored = next((s for s in analysis.scored if CANDIDATE_ID in s.members), None)
        node = _node(candidate, is_new=True)

        if scored is None:
            return {
                "linked": False, "alone": "approve", "decision": "approve", "score": 0,
                "merged": [], "cluster": None, "candidate": node,
                "message": "No shared identifiers with any existing application, "
                           "so there is nothing to link. Looks like an independent applicant.",
            }

        others = set(scored.members) - {CANDIDATE_ID}
        merged = [
            {"cluster_id": s.cluster_id, "score": s.score, "decision": s.decision, "size": len(s.members)}
            for s in base.scored if others & set(s.members)
        ]
        cluster = analysis.clusters[scored.cluster_id]
        fields = sorted({l["field"] for l in cluster.links if CANDIDATE_ID in (l["a"], l["b"])})
        shared = " and ".join(LINK_LABEL[f] for f in fields) or "identifier"
        detail = _detail(scored, cluster, analysis.by_id)
        detail["cluster_id"] = "preview"
        return {
            "linked": True, "alone": "approve", "decision": scored.decision, "score": scored.score,
            "merged": merged, "cluster": detail, "candidate": node,
            "message": f"Shares a {shared} with {len(others)} existing application(s). "
                       f"On its own it looks clean; linked, the cluster scores {scored.score} "
                       f"and the recommendation is {scored.decision}.",
        }