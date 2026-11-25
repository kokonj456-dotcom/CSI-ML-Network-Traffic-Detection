"""Compatibility entry point for the Flowwatch backend CLI."""
from backend.main import create_app, main
from backend.src.config import DEFAULT_BUNDLE

if __name__ == "__main__":
    main()
