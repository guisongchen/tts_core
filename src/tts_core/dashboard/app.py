import os
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..client import TTSCoreClient
from ..config import MODEL_CHOICES, SOCKET_PATH
from .systemd import SystemdManager

SPEAKERS = ["Serena", "Vivian", "Uncle_Fu"]
DEFAULT_SPEAKER = "Serena"

app = FastAPI(title="TTSCore Dashboard")

static_dir = Path(__file__).parent / "static"
templates_dir = Path(__file__).parent / "templates"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
templates = Jinja2Templates(directory=str(templates_dir))

systemd = SystemdManager(user=True)


def _tts_status() -> dict:
    if not os.path.exists(SOCKET_PATH):
        return {"state": "unloaded", "model_name": None, "gpu_memory_mb": None}
    try:
        with TTSCoreClient(auto_start=False) as client:
            return client.status()
    except Exception as e:
        return {"state": "error", "model_name": None, "error_message": str(e)}


def _tts_stats() -> dict:
    if not os.path.exists(SOCKET_PATH):
        return {}
    try:
        with TTSCoreClient(auto_start=False) as client:
            return client.stats()
    except Exception:
        return {}


def _services() -> list[dict]:
    return [
        {"name": s.name, "active": s.active, "status": s.status, "uptime": s.uptime}
        for s in systemd.all_statuses()
    ]


def _full_status() -> dict:
    return {"tts": _tts_status(), "stats": _tts_stats(), "services": _services()}


# ── pages ────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {"tts": _tts_status(), "stats": _tts_stats(), "services": _services(),
         "models": MODEL_CHOICES, "speakers": SPEAKERS, "default_speaker": DEFAULT_SPEAKER, "htmx": False},
    )


# ── api ───────────────────────────────────────────────────────────

@app.get("/api/status")
def api_status():
    return _full_status()


@app.post("/api/load", response_class=HTMLResponse)
def api_load(request: Request, model_name: str = Form(...)):
    try:
        with TTSCoreClient(auto_start=False) as client:
            client.load_model(model_name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return partial_status(request)


@app.post("/api/unload", response_class=HTMLResponse)
def api_unload(request: Request):
    try:
        with TTSCoreClient(auto_start=False) as client:
            client.unload_model()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return partial_status(request)


@app.post("/api/synthesize", response_class=HTMLResponse)
def api_synthesize(
    request: Request,
    text: str = Form(...),
    language: str = Form("Chinese"),
    speaker: str = Form(DEFAULT_SPEAKER),
    instruct: str = Form(""),
):
    try:
        with TTSCoreClient(auto_start=False) as client:
            result = client.synthesize(
                text=text, language=language, speaker=speaker,
                instruct=instruct or None,
            )
        return templates.TemplateResponse(
            request,
            "partials/synthesize_result.html",
            {"result": result, "text": text, "speaker": speaker},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/services/{name}/start", response_class=HTMLResponse)
def api_service_start(request: Request, name: str):
    systemd.start(name)
    return _render_services(request)


@app.post("/api/services/{name}/stop", response_class=HTMLResponse)
def api_service_stop(request: Request, name: str):
    systemd.stop(name)
    return _render_services(request)


@app.post("/api/services/{name}/restart", response_class=HTMLResponse)
def api_service_restart(request: Request, name: str):
    systemd.restart(name)
    return _render_services(request)


@app.get("/api/services/{name}/logs")
def api_service_logs(name: str, lines: int = 50):
    return {"name": name, "logs": systemd.logs(name, lines)}


@app.post("/api/refresh")
def api_refresh():
    return Response(
        status_code=200,
        headers={"HX-Trigger": '{"refresh-status": "", "refresh-logs": ""}'},
    )


@app.get("/api/audio")
def api_audio(path: str = Query(...)):
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/wav")


# ── partials ──────────────────────────────────────────────────────

@app.get("/partials/status", response_class=HTMLResponse)
def partial_status(request: Request):
    return templates.TemplateResponse(
        request,
        "partials/status.html",
        {"tts": _tts_status(), "stats": _tts_stats(), "services": _services(),
         "models": MODEL_CHOICES, "speakers": SPEAKERS, "default_speaker": DEFAULT_SPEAKER,
         "htmx": request.headers.get("HX-Request") == "true"},
    )


@app.get("/partials/services", response_class=HTMLResponse)
def partial_services(request: Request):
    return _render_services(request)


def _render_services(request: Request):
    return templates.TemplateResponse(
        request,
        "partials/services.html",
        {"services": _services()},
    )


@app.get("/partials/logs/{name}", response_class=HTMLResponse)
def partial_logs(request: Request, name: str, lines: int = 50):
    return _render_logs(request, name, lines)


@app.get("/partials/logs", response_class=HTMLResponse)
def partial_logs_query(request: Request, name: str, lines: int = 50):
    return _render_logs(request, name, lines)


def _render_logs(request: Request, name: str, lines: int):
    return templates.TemplateResponse(
        request,
        "partials/logs.html",
        {"name": name, "logs": systemd.logs(name, lines)},
    )
