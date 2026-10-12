"""python -m studio [--host 127.0.0.1] [--port 8000]

Serves the API and, once `npm run build` has been run in web/, the UI.
The studio can start runs that spend your API quota, so by default it only
listens on this computer.
"""
from __future__ import annotations

import argparse


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    from .app import create_app

    p = argparse.ArgumentParser(prog="python -m studio", description="Stem Studio: API and UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(f"warning: listening on {args.host}; anyone who can reach it can start runs on your API key")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
