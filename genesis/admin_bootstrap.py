"""Create the initial NeoGen administrator from environment variables.

Usage:
    NEOGEN_ADMIN_EMAIL="admin@example.com" \
    NEOGEN_ADMIN_PASSWORD="use-a-secret-manager" \
    NEOGEN_ADMIN_NAME="NeoGen Admin" \
    python -m genesis.admin_bootstrap
"""

from __future__ import annotations

import os
from pathlib import Path

from genesis.services.events import EventBus
from genesis.services.identity import IdentityError, IdentityService
from genesis.services.storage import SQLiteStore


def main() -> None:
    email = os.environ.get("NEOGEN_ADMIN_EMAIL", "").strip()
    password = os.environ.get("NEOGEN_ADMIN_PASSWORD", "")
    display_name = os.environ.get("NEOGEN_ADMIN_NAME", "NeoGen Admin").strip()
    database = Path(os.environ.get("NEOGEN_DB", "neogen.db"))

    if not email or not password:
        raise SystemExit(
            "Set NEOGEN_ADMIN_EMAIL and NEOGEN_ADMIN_PASSWORD before running this command."
        )

    store = SQLiteStore(database)
    identity = IdentityService(store, EventBus())
    try:
        user = identity.register(
            email=email,
            password=password,
            display_name=display_name or "NeoGen Admin",
            roles=("user", "admin"),
        )
    except IdentityError as exc:
        raise SystemExit(f"Admin bootstrap failed: {exc}") from exc
    finally:
        store.close()

    print(f"Created NeoGen administrator: {user.email}")


if __name__ == "__main__":
    main()
