"""Serve the NeoGen web client and API from one local tablet process.

Run in Termux:
    python -m genesis.tablet_server

Then open:
    http://127.0.0.1:8080/
"""

from __future__ import annotations

import argparse
import mimetypes
from http import HTTPStatus
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from genesis.api.server import NeoGenApiHandler
from genesis.services.kernel import NeoGenKernel


class TabletHandler(NeoGenApiHandler):
    web_root: Path

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/"):
            super().do_GET()
            return
        self._serve_static(path)

    def _serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        target = (self.web_root / relative).resolve()
        try:
            target.relative_to(self.web_root)
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            target = self.web_root / "index.html"
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_type = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache" if target.name == "index.html" else "public, max-age=3600")
        self.end_headers()
        self.wfile.write(body)


def create_tablet_server(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    storage_path: str | Path = "neogen.db",
    workspace_path: str | Path = "workspace",
    web_path: str | Path | None = None,
) -> ThreadingHTTPServer:
    kernel = NeoGenKernel.build(
        storage_path=storage_path,
        workspace_path=workspace_path,
        enable_puter=True,
    )
    root = Path(web_path) if web_path else Path(__file__).resolve().parent.parent / "web"
    root = root.resolve()
    handler = type(
        "ConfiguredTabletHandler",
        (TabletHandler,),
        {"kernel": kernel, "web_root": root},
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run NeoGen locally on an Android tablet")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--db", default="neogen.db")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--web", default=None)
    args = parser.parse_args()

    server = create_tablet_server(
        host=args.host,
        port=args.port,
        storage_path=args.db,
        workspace_path=args.workspace,
        web_path=args.web,
    )
    try:
        print(f"NeoGen tablet server: http://{args.host}:{args.port}/")
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.kernel.close()


if __name__ == "__main__":
    main()
