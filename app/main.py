"""Thin web layer: routes requests to engine.service. No business logic here."""
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from engine.service import Store, ValidationError

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

app = FastAPI(
    title="Synthetic Identity Cluster Detector",
    version="1.0.0",
    description=(
        "Links loan applications that share a phone, device or bank account, "
        "scores each cluster and explains every decision. Synthetic data only."
    ),
)
store = Store()


@app.get("/api/health")
def health():
    return store.health()


@app.get("/api/overview")
def overview():
    return store.overview()


@app.get("/api/clusters")
def clusters():
    return store.clusters()


@app.get("/api/clusters/{cluster_id}")
def cluster_detail(cluster_id: str):
    detail = store.cluster_detail(cluster_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"cluster '{cluster_id}' not found")
    return detail


@app.get("/api/hubs")
def hubs():
    return store.hubs()


@app.get("/api/metrics")
def metrics():
    return store.metrics()


@app.get("/api/examples")
def examples():
    return store.examples()


@app.post("/api/score")
def score(payload: dict):
    """Dry run: score one new application against the dataset. Nothing is stored."""
    try:
        return store.score_candidate(payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(WEB_DIR / "index.html")


app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")