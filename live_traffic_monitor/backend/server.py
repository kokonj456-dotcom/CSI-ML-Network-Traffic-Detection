#!/usr/bin/env python3
"""FastAPI WebSocket & REST Server for Wireshark Live Defense Monitor V2.

Serves:
- Real-time WebSocket streaming at /ws/traffic with dynamic flow rate & threat intensity
- Hot-swap multi-environment controls: Home User, Enterprise LAN, Public Server
- Full 5 MITRE ATT&CK Injection Threats (Real PCAPs)
- Static Frontend at / on Port 8088
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from contextlib import asynccontextmanager
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

if str(BASE_DIR / "backend") not in sys.path:
    sys.path.insert(0, str(BASE_DIR / "backend"))

from traffic_generator import CORE_5_ATTACKS, ENV_CONFIG, TrafficGenerator


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(traffic_streaming_worker())
    print("V2 Dynamic Traffic streaming worker started.")
    yield
    task.cancel()


app = FastAPI(title="Live Defense Monitor V2 - Multi-Environment AI Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

generator = TrafficGenerator()


class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast_json(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(json.dumps(message))
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


class ControlRequest(BaseModel):
    action: str
    value: Any = None


@app.get("/api/status")
def get_status():
    return {
        "is_running": generator.is_running,
        "environment": generator.get_environment_info(),
        "stats": generator.get_live_metrics(),
        "core_attacks": CORE_5_ATTACKS,
    }


@app.get("/api/environments")
def get_environments():
    return {
        "current_environment": generator.current_env,
        "environments": {
            k: {
                "id": v["id"],
                "name": v["name"],
                "badge": v["badge"],
                "description": v["description"],
                "icon": v["icon"],
                "color": v["color"],
                "available_attacks": v["attacks"],
            }
            for k, v in ENV_CONFIG.items()
        },
    }


@app.post("/api/environment/{env_id}")
def set_environment(env_id: str):
    try:
        env_info = generator.set_environment(env_id)
        return {"status": "success", "environment": env_info, "metrics": generator.get_live_metrics()}
    except ValueError as e:
        return {"status": "error", "message": str(e)}


@app.post("/api/flow_rate")
def set_flow_rate(rate: float):
    generator.set_flow_rate(rate)
    return {"status": "success", "flow_rate": generator.flow_rate}


@app.post("/api/threat_intensity")
def set_threat_intensity(intensity: float):
    generator.set_threat_intensity(intensity)
    return {"status": "success", "threat_intensity": generator.threat_intensity}


@app.post("/api/inject/{attack_type}")
def inject_attack(attack_type: str, count: int = 15):
    generator.inject_attack(attack_type, count=count)
    return {
        "status": "success",
        "injected": attack_type,
        "environment": generator.current_env,
        "count": count,
        "queue_len": len(generator.injection_queue),
    }


@app.post("/api/control")
def handle_control(req: ControlRequest):
    action = req.action.lower()
    if action == "play":
        generator.is_running = True
    elif action == "pause":
        generator.is_running = False
    elif action == "toggle":
        generator.is_running = not generator.is_running
    elif action == "flow_rate":
        try:
            generator.set_flow_rate(float(req.value))
        except (ValueError, TypeError):
            pass
    elif action == "threat_intensity":
        try:
            generator.set_threat_intensity(float(req.value))
        except (ValueError, TypeError):
            pass
    elif action == "environment":
        if req.value in ENV_CONFIG:
            generator.set_environment(str(req.value))
    elif action == "reset":
        generator.stats = generator._init_stats_structure()
        generator.injection_queue.clear()

    return get_status()


@app.websocket("/ws/traffic")
async def websocket_traffic(websocket: WebSocket):
    await manager.connect(websocket)
    # Send initial status
    await websocket.send_text(json.dumps({"type": "init", "status": get_status()}))
    try:
        while True:
            data = await websocket.receive_text()
            try:
                cmd = json.loads(data)
                if "environment" in cmd or cmd.get("action") == "environment":
                    env_id = cmd.get("environment") or cmd.get("value")
                    if env_id in ENV_CONFIG:
                        env_info = generator.set_environment(str(env_id))
                        await websocket.send_text(
                            json.dumps({
                                "type": "env_change",
                                "environment": env_info,
                                "stats": generator.get_live_metrics(),
                            })
                        )
                elif "inject" in cmd:
                    generator.inject_attack(cmd["inject"], count=cmd.get("count", 15))
                elif "flow_rate" in cmd:
                    generator.set_flow_rate(float(cmd["flow_rate"]))
                elif "threat_intensity" in cmd:
                    generator.set_threat_intensity(float(cmd["threat_intensity"]))
                elif "action" in cmd:
                    handle_control(ControlRequest(action=cmd["action"], value=cmd.get("value")))
            except Exception:
                pass
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


async def traffic_streaming_worker():
    """Continuously streams single-flow dynamic inferences at the configured flow_rate."""
    while True:
        try:
            if generator.is_running and manager.active_connections:
                flow = generator.generate_next_flow()
                if flow:
                    payload = {
                        "type": "flow",
                        "packet": flow,
                        "stats": generator.get_live_metrics(),
                        "environment": generator.get_environment_info(),
                    }
                    await manager.broadcast_json(payload)

            # Delay inversely proportional to flow_rate (1 to 50+ flows/s)
            delay = 1.0 / max(1.0, min(100.0, generator.flow_rate))
            await asyncio.sleep(delay)
        except Exception as e:
            print(f"Error in traffic streaming worker: {e}", file=sys.stderr)
            await asyncio.sleep(0.5)


# Mount Static Files
DATA_DIR = BASE_DIR / "data"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if DATA_DIR.exists():
    app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")


@app.get("/")
def get_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Live Traffic Monitor Frontend is building...</h1>")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8088))
    print(f"Starting Live Defense Monitor V2 Server on http://localhost:{port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
