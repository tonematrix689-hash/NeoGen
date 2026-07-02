"""Command-line entry point for the Genesis kernel."""

from __future__ import annotations

import asyncio
import signal

from genesis.app.kernel.runtime import GenesisRuntime


async def run() -> int:
    """Start Genesis until interrupted."""

    stop_event = asyncio.Event()
    runtime = GenesisRuntime()

    def request_shutdown() -> None:
        runtime.logger.info("Shutdown requested")
        stop_event.set()

    loop = asyncio.get_running_loop()
    for signal_name in ("SIGINT", "SIGTERM"):
        signum = getattr(signal, signal_name, None)
        if signum is not None:
            try:
                loop.add_signal_handler(signum, request_shutdown)
            except NotImplementedError:
                signal.signal(signum, lambda *_: request_shutdown())

    async with runtime:
        runtime.logger.info("Genesis kernel is ready")
        await stop_event.wait()
    return 0


def main() -> int:
    """Synchronous console-script wrapper."""

    return asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(main())
