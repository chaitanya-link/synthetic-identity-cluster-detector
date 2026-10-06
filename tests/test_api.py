from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def example(example_id):
    return next(e for e in client.get("/api/examples").json() if e["id"] == example_id)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "applications": 505}


def test_overview():
    body = client.get("/api/overview").json()
    assert body["clusters"] == 11 and body["flagged_clusters"] == 8


def test_clusters_list_is_sorted_by_score():
    rows = client.get("/api/clusters").json()
    assert len(rows) == 11
    scores = [row["score"] for row in rows]
    assert scores == sorted(scores, reverse=True)


def test_cluster_detail_and_404():
    ok = client.get("/api/clusters/C007")
    assert ok.status_code == 200
    body = ok.json()
    assert body["cluster_id"] == "C007" and body["nodes"] and body["edges"]
    assert client.get("/api/clusters/C999").status_code == 404


def test_node_data_has_no_ground_truth_fields():
    body = client.get("/api/clusters/C007").json()
    for node in body["nodes"]:
        assert "label" not in node and "group" not in node


def test_hubs_and_metrics():
    assert sorted(h["count"] for h in client.get("/api/hubs").json()) == [24, 28]
    m = client.get("/api/metrics").json()
    assert m["easy"]["metrics"]["f1"] == 1.0
    assert m["hard"]["metrics"]["f1"] < 1.0


def test_examples_score_as_expected_through_the_api():
    examples = client.get("/api/examples").json()
    assert [e["id"] for e in examples] == ["mule", "device", "family", "clean"]
    for e in examples:
        r = client.post("/api/score", json=e["payload"])
        assert r.status_code == 200
        assert r.json()["decision"] == e["expect"], e["id"]


def test_score_is_a_dry_run():
    before = client.get("/api/health").json()["applications"]
    client.post("/api/score", json=example("mule")["payload"])
    assert client.get("/api/health").json()["applications"] == before


def test_score_validation_errors_are_422():
    assert client.post("/api/score", json={"name": "x"}).status_code == 422
    assert client.post("/api/score", json=[1, 2]).status_code == 422
    broken = client.post("/api/score", content="not json", headers={"Content-Type": "application/json"})
    assert broken.status_code == 422
    bad_time = client.post("/api/score", json={
        "name": "x", "phone": "1", "device_id": "d", "bank_account": "b", "timestamp": "nope",
    })
    assert bad_time.status_code == 422 and "timestamp" in bad_time.json()["detail"]


def test_index_and_static_files_are_served():
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "Synthetic Identity Cluster Detector" in page.text
    assert client.get("/static/style.css").status_code == 200
    js = client.get("/static/app.js")
    assert js.status_code == 200 and "api/score" in js.text


def test_openapi_docs_are_available():
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/score" in paths and "/" not in paths