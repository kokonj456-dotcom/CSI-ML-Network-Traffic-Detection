"""Build the React dashboard and launch its FastAPI server."""
from pathlib import Path
import shutil
import subprocess
import sys


DASHBOARD = Path(__file__).resolve().parent
FRONTEND = DASHBOARD / "frontend"
PROJECT_ROOT = DASHBOARD.parents[1]


def project_python():
    venv = PROJECT_ROOT / ".venv"
    executable = venv / "Scripts" / "python.exe" if sys.platform == "win32" else venv / "bin" / "python"
    return executable if executable.is_file() else Path(sys.executable)


def build_frontend():
    npm = shutil.which("npm.cmd" if sys.platform == "win32" else "npm")
    if npm is None:
        raise SystemExit("Node.js and npm are required to build Flowwatch. Install them and try again.")

    node_modules = FRONTEND / "node_modules"
    vite = node_modules / "vite" / "package.json"
    lockfile = FRONTEND / "package-lock.json"
    installed_lockfile = node_modules / ".flowwatch-package-lock.json"

    if not vite.is_file() or not installed_lockfile.is_file() or installed_lockfile.read_bytes() != lockfile.read_bytes():
        print("Installing frontend dependencies...", flush=True)
        subprocess.run([npm, "ci"], cwd=FRONTEND, check=True)
        shutil.copyfile(lockfile, installed_lockfile)

    print("Building the Flowwatch frontend...", flush=True)
    subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)


def main():
    executable = project_python()
    if executable.absolute() != Path(sys.executable).absolute():
        return subprocess.call([str(executable), str(Path(__file__).resolve()), *sys.argv[1:]])

    try:
        from backend.main import main as run_backend
    except ModuleNotFoundError as error:
        raise SystemExit(f"Missing Python dependency: {error.name}. See Dashboard/README.md for setup.") from error

    if not {"-h", "--help"}.intersection(sys.argv[1:]):
        try:
            build_frontend()
        except subprocess.CalledProcessError as error:
            raise SystemExit(error.returncode) from error
        print("Starting Flowwatch. Open the URL printed by Uvicorn.", flush=True)
    run_backend()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
