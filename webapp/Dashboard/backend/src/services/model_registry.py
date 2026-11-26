"""Locate, validate, and name model bundles on disk."""
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import shutil
from tempfile import TemporaryDirectory
from time import sleep


class ModelRegistry:
    def __init__(self, backup_dir, predictor_class):
        self.backup_dir = backup_dir.resolve()
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.active_path = self.backup_dir/"active-version.txt"
        self.predictor_class = predictor_class

    def prepare_baseline(self, existing_bundle, legacy_baseline):
        destination = self.bundle_path("baseline")
        if not destination.exists():
            source = legacy_baseline if legacy_baseline.is_dir() else existing_bundle.resolve()
            self.copy_backup(source, destination)
        self.name_backup(destination, "baseline")

    def restore_backup(self, version, legacy_bundle):
        destination = self.bundle_path(version)
        if legacy_bundle.is_dir() and not destination.exists():
            self.copy_backup(legacy_bundle, destination)
        if destination.is_dir():
            self.name_backup(destination, version)

    def save_active_version(self, version):
        with TemporaryDirectory(dir=self.backup_dir) as temp:
            staged = Path(temp)/self.active_path.name
            staged.write_text(version+"\n", encoding="utf-8")
            staged.replace(self.active_path)

    def copy_backup(self, source, destination):
        with TemporaryDirectory(dir=self.backup_dir) as temp:
            staged = Path(temp)/"bundle"
            shutil.copytree(source, staged)
            self.predictor_class(staged)
            staged.rename(destination)

    def name_backup(self, directory, version):
        prefix = "Base" if version == "baseline" else "FW"
        if directory.name == version:
            manifest = json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
            finished = (manifest.get("training") or {}).get("finished_at")
            timestamp = datetime.fromisoformat(finished) if finished else datetime.now(timezone.utc)
            local_time = timestamp.astimezone(timezone(timedelta(hours=7)))
        else:
            old_stamp = re.search(r"__(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})_ICT(?:__.+|_\d+)?$", directory.name)
            if not old_stamp:
                return directory
            local_time = datetime.strptime(old_stamp[1], "%Y-%m-%d_%H-%M-%S")
        name = f"{prefix}-{local_time:%y%m%d-%H%M}"
        destination = self.backup_dir/name
        suffix = 2
        while destination.exists():
            destination = self.backup_dir/f"{name}_{suffix}"
            suffix += 1
        # Explorer and antivirus can briefly hold Windows directory handles.
        # The registry can still resolve a verified bundle from its version directory.
        for delay in (0, .25, .5, 1):
            if delay:
                sleep(delay)
            try:
                (directory/".registry-version").write_text(version, encoding="utf-8")
                return directory.rename(destination)
            except PermissionError:
                continue
        return directory

    def bundle_path(self, version):
        if version != "baseline" and not re.fullmatch(r"[0-9a-f]{32}", version):
            raise ValueError("Unknown model version.")
        for path in self.backup_dir.glob(f"*__{version}"):
            if path.is_dir():
                return path
        for marker in self.backup_dir.glob("*/.registry-version"):
            if marker.read_text(encoding="utf-8").strip() == version:
                return marker.parent
        return self.backup_dir/version

    def load_candidate(self, version):
        model = self.predictor_class(self.bundle_path(version))
        result = model.predict([{
            "duration":1, "bytes_forward":120, "bytes_backward":50,
            "protocol":"tcp", "service_group":"http", "conn_state_group":"established",
        }])
        if result[0]["status"] != "scored":
            raise ValueError("Inference smoke check failed.")
        return model

    def get_bundle(self, version):
        directory = self.bundle_path(version)
        with (directory/"manifest.json").open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        with (directory/"evaluation.json").open(encoding="utf-8") as stream:
            evaluation = json.load(stream)
        return {"version":version,"manifest":manifest,"evaluation":evaluation}
