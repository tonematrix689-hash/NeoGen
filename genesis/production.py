"""Production entrypoint for the public NeoGen web application.

The public runtime deliberately disables legacy mutation endpoints. Device-local
operations remain available through the guarded /api/v1/guarded/* approval
contracts exposed by genesis.tablet_server.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from http import HTTPStatus
from urllib.parse import urlparse

from genesis.tablet_server import create_tablet_server


_BLOCKED_LEGACY_MUTATIONS = frozenset(
    {
        "/api/v1/workspace/write",
        "/api/v1/workspace/mkdir",
        "/api/v1/workspace/delete",
        "/api/v1/terminal/execute",
        "/api/v1/permissions/grant",
        "/api/v1/tools/execute",
        "/api/v1/checkpoints",
    }
)


def _positive_port(value: str) -> int:
    port = int(value)
    if not 1 <= port <= 65535:
        raise ValueError("PORT must be between 1 and 65535")
    return port


def _data_paths() -> tuple[Path, Path]:
    data_dir = Path(os.environ.get("NEOGEN_DATA_DIR", "/var/lib/neogen")).expanduser().resolve()
    workspace = Path(
        os.environ.get("GENESIS_WORKSPACE_DIR", str(data_dir / "workspace"))
    ).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    workspace.mkdir(parents=True, exist_ok=True)
    probe = data_dir / ".write-test"
    probe.write_text("ready", encoding="utf-8")
    probe.unlink()
    return data_dir / "neogen.db", workspace


def create_production_server():
    host = os.environ.get("HOST", "0.0.0.0")
    port = _positive_port(os.environ.get("PORT", "8080"))
    database, workspace = _data_paths()
    server = create_tablet_server(
        host=host,
        port=port,
        storage_path=database,
        workspace_path=workspace,
    )
    base_handler = server.RequestHandlerClass

    class ProductionHandler(base_handler):
        def do_POST(self) -> None:  # noqa: N802
            if urlparse(self.path).path in _BLOCKED_LEGACY_MUTATIONS:
                self._send(
                    HTTPStatus.FORBIDDEN,
                    {
                        "error": "Direct mutation is disabled in the public runtime",
                        "approval_required": True,
                    },
                )
                return
            super().do_POST()

        def end_headers(self) -> None:
            self.send_header(
                "Permissions-Policy",
                "camera=(self), microphone=(self), geolocation=(), payment=()",
            )
            self.send_header("Cross-Origin-Opener-Policy", "same-origin-allow-popups")
            if os.environ.get("NEOGEN_HTTPS", "1").lower() not in {"0", "false", "no"}:
                self.send_header(
                    "Strict-Transport-Security",
                    "max-age=31536000; includeSubDomains",
                )
            super().end_headers()

    server.RequestHandlerClass = ProductionHandler
    return server


def main() -> None:
    server = create_production_server()
    host, port = server.server_address
    print(f"NeoGen production server listening on {host}:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()
        server.server_close()
        server.RequestHandlerClass.kernel.close()
        asyncio.run(server.RequestHandlerClass.guarded_runtime.stop())


if __name__ == "__main__":
    main()
