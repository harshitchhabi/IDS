"""FastAPI app for the demo: dashboard page, WebSocket snapshots, and control endpoints (HTMX posts)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dloop.demo.service import DemoService
from dloop.loop.live import DEFENSES

DASHBOARD = Path(__file__).resolve().parents[3] / "dashboard"


def create_app(service: DemoService) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await service.start()
        yield
        await service.stop()

    app = FastAPI(title="Deception Loop demo", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=DASHBOARD / "static"), name="static")
    templates = Jinja2Templates(directory=str(DASHBOARD / "templates"))

    @app.get("/")
    async def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {"recorded": service.recorded,
                                                                  "defenses": DEFENSES})

    @app.get("/api/state")
    async def state():
        return JSONResponse(service.snapshot())

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()

        async def send(snap: dict) -> None:
            await sock.send_json(snap)

        service.subscribers.add(send)
        try:
            await sock.send_json(service.snapshot())
            while True:
                await sock.receive_text()      # keepalive; the page sends nothing meaningful
        except WebSocketDisconnect:
            pass
        finally:
            service.subscribers.discard(send)

    def _ok() -> Response:
        return Response(status_code=204)

    @app.post("/api/feed/{feed}")
    async def feed(feed: str):
        try:
            service.set_feed(feed)
        except ValueError:
            raise HTTPException(400, "feed must be s0, a1 or off")
        return _ok()

    @app.post("/api/defense/{name}")
    async def defense(name: str):
        try:
            service.set_defense(name)
        except ValueError:
            raise HTTPException(400, f"defense must be one of {DEFENSES}")
        return _ok()

    @app.post("/api/mode/{mode}")
    async def mode(mode: str):
        try:
            service.set_mode(mode)
        except ValueError:
            raise HTTPException(400, "mode must be fixed or recalibrated")
        return _ok()

    @app.post("/api/step")
    async def step():
        service.step_once()
        return _ok()

    @app.post("/api/reset")
    async def reset():
        await service.reset()
        return _ok()

    @app.post("/api/rate/{rate}")
    async def rate(rate: int):
        if service.driver is not None:
            service.driver.set_rate(rate)
        return _ok()

    @app.post("/api/attack/{family}")
    async def attack(family: str):
        try:
            n = service.launch_attack(family)
        except (ValueError, RuntimeError) as e:
            raise HTTPException(400, str(e))
        return JSONResponse({"family": family, "flows": n})

    return app
