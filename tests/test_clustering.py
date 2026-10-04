from engine.clustering import UnionFind, build_clusters
from engine.generator import generate


def ids_of(data, group):
    return sorted(a["app_id"] for a in data if a["group"] == group)


def cluster_of(result, app_id):
    for c in result.clusters:
        if app_id in c.members:
            return c
    return None


def make_app(i, **kw):
    base = dict(app_id=f"X{i:03d}", phone=f"p{i}", device_id=f"d{i}",
                bank_account=f"b{i}", ip=f"ip{i}")
    base.update(kw)
    return base


# ---- union-find ----
def test_union_find_basics():
    uf = UnionFind("abcde")
    assert uf.union("a", "b") is True
    assert uf.union("b", "a") is False          # already joined
    uf.union("c", "d")
    assert uf.find("a") == uf.find("b")
    assert uf.find("a") != uf.find("c")
    uf.union("b", "d")
    assert uf.find("a") == uf.find("c")
    assert uf.find("e") == "e"


def test_union_find_long_chain_is_flattened():
    uf = UnionFind(range(1000))
    for i in range(999):
        uf.union(i, i + 1)
    assert len({uf.find(i) for i in range(1000)}) == 1


# ---- clustering on generated data ----
def test_device_farms_and_mules_are_single_clusters():
    data = generate()
    result = build_clusters(data)
    for group in ("device_farm-1", "device_farm-2", "mule-1", "mule-2"):
        members = ids_of(data, group)
        c = cluster_of(result, members[0])
        assert c is not None and c.members == members, group


def test_chained_ring_is_found_through_the_chain():
    data = generate()
    result = build_clusters(data)
    for group in ("chained-1", "chained-2"):
        members = ids_of(data, group)
        c = cluster_of(result, members[0])
        assert c.members == members
        assert c.link_fields == ["bank_account", "device_id", "phone"]


def test_every_sim_farm_application_lands_in_some_cluster():
    data = generate()
    result = build_clusters(data)
    for app_id in ids_of(data, "sim_farm-1"):
        assert cluster_of(result, app_id) is not None


def test_family_is_clustered_but_only_with_each_other():
    data = generate()
    result = build_clusters(data)
    for group in ("family-1", "family-2", "family-3"):
        members = ids_of(data, group)
        assert cluster_of(result, members[0]).members == members


def test_office_ip_never_merges_and_is_reported_as_hub():
    data = generate()
    result = build_clusters(data)
    for group in ("office-1", "office-2"):
        members = set(ids_of(data, group))
        for c in result.clusters:
            assert len(members & set(c.members)) <= 1
    hub_counts = {h["count"] for h in result.hubs if h["field"] == "ip"}
    assert {28, 24} <= hub_counts


def test_no_cluster_mixes_genuine_and_fraud():
    data = generate()
    result = build_clusters(data)
    label = {a["app_id"]: a["label"] for a in data}
    for c in result.clusters:
        assert len({label[m] for m in c.members}) == 1


def test_genuine_singletons_stay_unclustered():
    data = generate()
    result = build_clusters(data)
    clustered = {m for c in result.clusters for m in c.members}
    singles = [a for a in data if a["group"] == "" and a["app_id"] not in clustered]
    assert len(singles) == 400


# ---- hub cap and giant-component protection ----
def test_hub_identifier_is_not_used_to_merge():
    apps = [make_app(i, device_id="shared_kiosk") for i in range(20)]
    result = build_clusters(apps, hub_cap=15)
    assert result.clusters == []
    assert result.hubs[0]["field"] == "device_id" and result.hubs[0]["count"] == 20


def test_identifier_at_the_cap_still_merges():
    apps = [make_app(i, device_id="shared") for i in range(15)]
    result = build_clusters(apps, hub_cap=15)
    assert len(result.clusters) == 1 and len(result.clusters[0].members) == 15


def test_long_chain_is_flagged_oversized():
    n = 40
    apps = [make_app(i, device_id=f"d{i // 2}", phone=f"p{(i + 1) // 2}") for i in range(n)]
    result = build_clusters(apps, max_cluster_size=25)
    assert len(result.clusters) == 1
    assert len(result.clusters[0].members) == n
    assert result.clusters[0].oversized is True


# ---- integrity ----
def test_detector_ignores_ground_truth_fields():
    data = generate()
    stripped = [{k: v for k, v in a.items() if k not in ("label", "group")} for a in data]
    a = build_clusters(data)
    b = build_clusters(stripped)
    assert [c.members for c in a.clusters] == [c.members for c in b.clusters]


def test_deterministic():
    data = generate()
    a, b = build_clusters(data), build_clusters(data)
    assert [(c.cluster_id, c.members) for c in a.clusters] == [(c.cluster_id, c.members) for c in b.clusters]