"""Identity clustering with union-find.

Applications that share a STRONG identifier (phone, device, bank account) are
merged into one cluster. An identifier shared by more than `hub_cap`
applications is a "hub" (shared line, kiosk, agent) and is NOT used to merge,
because it would glue unrelated people into one giant cluster. IP addresses
are context only: they are shared by design (offices, colleges, carrier NAT),
so they never merge anything, but over-shared ones are reported as hubs.

This module never reads the ground-truth fields `label` or `group`.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

STRONG_FIELDS = ("phone", "device_id", "bank_account")
CONTEXT_FIELDS = ("ip",)
HUB_CAP = 15
MAX_CLUSTER_SIZE = 25


class UnionFind:
    """Disjoint sets with path compression and union by rank."""

    def __init__(self, items=()):
        self.parent: dict = {}
        self.rank: dict = {}
        for item in items:
            self.add(item)

    def add(self, x) -> None:
        if x not in self.parent:
            self.parent[x] = x
            self.rank[x] = 0

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # path compression
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b) -> bool:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


@dataclass
class Cluster:
    cluster_id: str
    members: list[str]                       # application ids
    links: list[dict]                        # {"a", "b", "field", "value"}
    link_fields: list[str]                   # distinct strong fields that linked members
    oversized: bool = False                  # bigger than max_cluster_size


@dataclass
class ClusterResult:
    clusters: list[Cluster] = field(default_factory=list)
    hubs: list[dict] = field(default_factory=list)   # identifiers skipped as too shared


def build_clusters(
    applications: list[dict],
    hub_cap: int = HUB_CAP,
    max_cluster_size: int = MAX_CLUSTER_SIZE,
) -> ClusterResult:
    by_id = {a["app_id"]: a for a in applications}

    # identifier value -> application ids that used it
    index: dict[tuple[str, str], list[str]] = defaultdict(list)
    for app in applications:
        for fld in STRONG_FIELDS + CONTEXT_FIELDS:
            value = app.get(fld)
            if value:
                index[(fld, value)].append(app["app_id"])

    uf = UnionFind(by_id)
    links: list[dict] = []
    hubs: list[dict] = []

    for (fld, value), ids in index.items():
        if len(ids) < 2:
            continue
        if len(ids) > hub_cap:
            hubs.append({"field": fld, "value": value, "count": len(ids), "app_ids": ids})
            continue
        if fld not in STRONG_FIELDS:
            continue
        anchor = ids[0]
        for other in ids[1:]:
            uf.union(anchor, other)
            links.append({"a": anchor, "b": other, "field": fld, "value": value})

    groups: dict[str, list[str]] = defaultdict(list)
    for app_id in by_id:
        groups[uf.find(app_id)].append(app_id)

    links_by_root: dict[str, list[dict]] = defaultdict(list)
    for link in links:
        links_by_root[uf.find(link["a"])].append(link)

    multi = sorted((sorted(m) for m in groups.values() if len(m) >= 2), key=lambda m: m[0])
    clusters = []
    for n, members in enumerate(multi, 1):
        cluster_links = links_by_root[uf.find(members[0])]
        clusters.append(
            Cluster(
                cluster_id=f"C{n:03d}",
                members=members,
                links=cluster_links,
                link_fields=sorted({l["field"] for l in cluster_links}),
                oversized=len(members) > max_cluster_size,
            )
        )
    hubs.sort(key=lambda h: -h["count"])
    return ClusterResult(clusters=clusters, hubs=hubs)