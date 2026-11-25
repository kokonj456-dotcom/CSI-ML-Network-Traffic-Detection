"""HTTP endpoints for model scoring and data sources."""
from hashlib import file_digest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal

from fastapi import HTTPException, Query, Request
from scapy.error import Scapy_Exception
from starlette.concurrency import run_in_threadpool

from ..config import CAPTURES, capture_files
from ..services.captures import capture_flows

MAX_CAPTURE_BYTES = 32*1024*1024
CAPTURE_MAGIC = {bytes.fromhex(value) for value in ("d4c3b2a1","a1b2c3d4","4d3cb2a1","a1b23c4d","0a0d0d0a")}


def mount_inference(app, manager, store):
    def require_store():
        if store is None:
            raise HTTPException(503, "Configure MySQL to use saved traffic.")
        return store

    def require_local_write(request):
        if request.headers.get("origin") not in (None, str(request.base_url).rstrip("/")):
            raise HTTPException(403, "Submit changes from the local Flowwatch dashboard.")

    def page(rows, limit):
        return rows[:limit], rows[limit-1]["id"] if len(rows)>limit else None

    @app.get("/api/model")
    def model():
        return manager.predictor.metadata()

    @app.post("/api/predict")
    def predict(inputs: list[dict]):
        if not 1<=len(inputs)<=256:
            raise HTTPException(422,"Provide 1–256 flows.")
        return {"predictions":manager.predictor.predict(inputs)}

    def analyze(name, persist=False):
        if name not in capture_files():
            raise HTTPException(404,"Capture is unavailable.")
        predictor = manager.predictor
        try:
            records=capture_flows(CAPTURES/name)
        except FileNotFoundError as error:
            raise HTTPException(404,"Capture is unavailable.") from error
        results=predictor.predict([row["raw"] for row in records], explain=True)
        capture_id, identifiers = store.save_capture(CAPTURES/name, records, results) if persist else (None, [{}]*len(records))
        return {
            "file":name,"capture_id":capture_id,"model":predictor.metadata(),
            "flows":[row | ids | {"prediction":result, "receipt":manager.capture_receipt(row,name,result,ids.get("alert_id"))}
                     for row,result,ids in zip(records,results,identifiers)],
        }

    @app.get("/api/captures/{name}")
    def preview(name: str):
        return analyze(name)

    @app.post("/api/captures/{name}")
    def import_capture(name: str, request: Request):
        require_local_write(request)
        require_store()
        return analyze(name, persist=True)

    def save_upload(path, uploads, name):
        try:
            with path.open("rb") as stream:
                if stream.read(4) not in CAPTURE_MAGIC:
                    raise ValueError("Choose a valid PCAP or PCAPNG file.")
                stream.seek(0)
                digest = file_digest(stream,"sha256").hexdigest()
            records = capture_flows(path, packet_limit=250_000)
            if not records:
                raise ValueError("No supported TCP, UDP or ICMP flows found in this capture.")
            if len(records)>10_000:
                raise ValueError("Capture exceeds the 10,000 flow import limit.")
        except (Scapy_Exception, ValueError, OSError) as error:
            raise HTTPException(422, str(error) if isinstance(error, ValueError) else "Capture could not be read.") from error
        predictor = manager.predictor
        results = []
        for start in range(0,len(records),256):
            results.extend(predictor.predict([row["raw"] for row in records[start:start+256]], explain=True))
        directory = uploads/digest
        directory.mkdir(exist_ok=True)
        destination = directory/"capture.pcap"
        try:
            # Re-imports keep the immutable capture already stored at this hash.
            path.rename(destination)
        except FileExistsError:
            pass
        capture_id, identifiers = store.save_capture(destination, records, results, original_name=name)
        return {"capture_id":capture_id,"file":name,"flow_count":len(identifiers),
                "alert_count":sum(row["alert_id"] is not None for row in identifiers)}

    @app.post("/api/capture-uploads")
    async def upload_capture(request: Request, name: str = Query(min_length=1, max_length=180)):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Import captures from the local Flowwatch dashboard.")
        require_store()
        if (Path(name).suffix.lower() not in {".pcap",".pcapng"} or
                any(char in '<>:"/\\|?*' or ord(char)<32 for char in name)):
            raise HTTPException(422, "Choose a PCAP or PCAPNG file with a valid file name.")
        uploads = CAPTURES/"uploads"
        uploads.mkdir(parents=True,exist_ok=True)
        with TemporaryDirectory(dir=uploads) as temporary:
            path = Path(temporary)/"capture"
            size = 0
            with path.open("wb") as stream:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size>MAX_CAPTURE_BYTES:
                        raise HTTPException(413, "Capture exceeds 32 MiB.")
                    stream.write(chunk)
            return await run_in_threadpool(save_upload,path,uploads,name)

    @app.get("/api/traffic/flows")
    def traffic_flows(limit: int = Query(50, ge=1, le=250), before_id: int | None = Query(None, ge=1),
                      capture_id: int | None = Query(None, ge=1)):
        rows, next_id = page(require_store().flows(limit+1, before_id, capture_id), limit)
        return {"flows": rows, "next_before_id": next_id}

    @app.get("/api/traffic/flows/{flow_id}/events")
    def protocol_events(flow_id: int):
        rows = require_store().protocol_events(flow_id)
        if rows is None:
            raise HTTPException(404, "Flow does not exist.")
        return {"events": rows}

    @app.get("/api/traffic/alerts")
    def alerts(limit: int = Query(50, ge=1, le=250), before_id: int | None = Query(None, ge=1)):
        rows, next_id = page(require_store().alerts(limit+1, before_id), limit)
        return {"alerts": rows, "next_before_id": next_id}

    @app.patch("/api/traffic/alerts/{alert_id}")
    def update_alert(alert_id: int, status: Literal["new", "acknowledged", "resolved"], request: Request):
        require_local_write(request)
        if not require_store().set_alert_status(alert_id, status):
            raise HTTPException(404, "Alert does not exist.")
        return {"status": status}
