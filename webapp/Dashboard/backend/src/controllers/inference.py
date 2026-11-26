"""Handle inference operations requested by the API."""
try:
    from hashlib import file_digest
except ImportError:
    import hashlib
    def file_digest(stream, algo="sha256"):
        h = getattr(hashlib, algo)()
        for chunk in iter(lambda: stream.read(65536), b""):
            h.update(chunk)
        class _DigestWrapper:
            def hexdigest(self): return h.hexdigest()
            def digest(self): return h.digest()
        return _DigestWrapper()
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import HTTPException
from scapy.error import Scapy_Exception
from starlette.concurrency import run_in_threadpool

from ..config import CAPTURES, capture_files
from ..services.capture.pcap import capture_flows
from ..services.central_test import build_central_test_records
MAX_CAPTURE_BYTES = 32*1024*1024
CAPTURE_MAGIC = {bytes.fromhex(value) for value in ("d4c3b2a1","a1b2c3d4","4d3cb2a1","a1b23c4d","0a0d0d0a")}


class InferenceController:
    def __init__(self, manager, store):
        self.manager = manager
        self.store = store

    def require_store(self):
        if self.store is None:
            raise HTTPException(503, "Configure MySQL to use saved traffic.")
        return self.store

    @staticmethod
    def require_local_write(request):
        if request.headers.get("origin") not in (None, str(request.base_url).rstrip("/")):
            raise HTTPException(403, "Submit changes from the local Flowwatch dashboard.")

    @staticmethod
    def page(rows, limit):
        return rows[:limit], rows[limit-1]["id"] if len(rows)>limit else None

    def model(self):
        return self.manager.predictor.metadata()

    def predict(self, inputs):
        if not 1<=len(inputs)<=256:
            raise HTTPException(422,"Provide 1–256 flows.")
        return {"predictions":self.manager.predictor.predict(inputs)}

    def save_central_test(self, samples, request):
        self.require_local_write(request)
        store = self.require_store()
        records = build_central_test_records(samples)
        predictions = self.manager.predictor.predict([record["raw"] for record in records], explain=True)
        identifiers = store.save_central_test(records, predictions)
        return {"predictions": predictions, "records": identifiers}

    def analyze(self, name, persist=False):
        if name not in capture_files():
            raise HTTPException(404,"Capture is unavailable.")
        predictor = self.manager.predictor
        try:
            records=capture_flows(CAPTURES/name)
        except FileNotFoundError as error:
            raise HTTPException(404,"Capture is unavailable.") from error
        results=predictor.predict([row["raw"] for row in records], explain=True)
        capture_id, identifiers = self.store.save_capture(CAPTURES/name, records, results) if persist else (None, [{}]*len(records))
        return {
            "file":name,"capture_id":capture_id,"model":predictor.metadata(),
            "flows":[row | ids | {"prediction":result, "receipt":self.manager.capture_receipt(row,name,result,ids.get("alert_id"))}
                     for row,result,ids in zip(records,results,identifiers)],
        }

    def preview(self, name):
        return self.analyze(name)

    def import_capture(self, name, request):
        self.require_local_write(request)
        self.require_store()
        return self.analyze(name, persist=True)

    def save_upload(self, path, uploads, name):
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
        predictor = self.manager.predictor
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
        capture_id, identifiers = self.store.save_capture(destination, records, results, original_name=name)
        return {"capture_id":capture_id,"file":name,"flow_count":len(identifiers),
                "alert_count":sum(row["alert_id"] is not None for row in identifiers)}

    async def upload_capture(self, request, name):
        if request.headers.get("origin") != str(request.base_url).rstrip("/"):
            raise HTTPException(403, "Import captures from the local Flowwatch dashboard.")
        self.require_store()
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
            return await run_in_threadpool(self.save_upload,path,uploads,name)

    def traffic_flows(self, limit, before_id, capture_id, alerts_only=False):
        store = self.require_store()
        rows, next_id = self.page(store.flows(limit+1, before_id, capture_id, alerts_only), limit)
        return {"flows": rows, "next_before_id": next_id,
                "total_flows": store.flow_count(capture_id, alerts_only)}

    def protocol_events(self, flow_id):
        rows = self.require_store().protocol_events(flow_id)
        if rows is None:
            raise HTTPException(404, "Flow does not exist.")
        return {"events": rows}

    def alerts(self, limit, before_id):
        rows, next_id = self.page(self.require_store().alerts(limit+1, before_id), limit)
        return {"alerts": rows, "next_before_id": next_id}

    def update_alert(self, alert_id, status, request):
        self.require_local_write(request)
        if not self.require_store().set_alert_status(alert_id, status):
            raise HTTPException(404, "Alert does not exist.")
        return {"status": status}
