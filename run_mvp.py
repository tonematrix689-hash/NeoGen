"""Run the NeoGen API and web client with one command.

Usage:
    python run_mvp.py

Then open http://127.0.0.1:8081
"""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from genesis.api.server import create_server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the NeoGen MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--api-port", type=int, default=8080)
    parser.add_argument("--web-port", type=int, default=8081)
    parser.add_argument("--db", default="neogen.db")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--disable-puter", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    web_root = root / "web"
    web_root.mkdir(parents=True, exist_ok=True)
    Path(args.workspace).mkdir(parents=True, exist_ok=True)

    api = create_server(
        host=args.host,
        port=args.api_port,
        storage_path=args.db,
        workspace_path=args.workspace,
        enable_puter=not args.disable_puter,
    )
    api_thread = threading.Thread(target=api.serve_forever, name="neogen-api", daemon=True)
    api_thread.start()

    handler = partial(SimpleHTTPRequestHandler, directory=os.fspath(web_root))
    web = ThreadingHTTPServer((args.host, args.web_port), handler)
    web.daemon_threads = True
    url = f"http://{args.host}:{args.web_port}"

    print(f"NeoGen API: http://{args.host}:{args.api_port}/api/v1")
    print(f"NeoGen Web: {url}")
    print("Press Ctrl+C to stop.")

    if not args.no_browser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()

    try:
        web.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        web.shutdown()
        web.server_close()
        api.shutdown()
        api.server_close()
        api.RequestHandlerClass.kernel.close()


if __name__ == "__main__":
    main()
