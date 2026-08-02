"""Dependency-free Afterlife Neogenesis MVP web application."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass(frozen=True, slots=True)
class PlayerSnapshot:
    name: str = "Founder"
    companion: str = "VERA"
    avatar_level: int = 1
    rarity_tier: int = 1
    neo_balance: int = 1250
    essence_balance: int = 80
    inventory_items: int = 4
    pending_approvals: int = 1


PLAYER = PlayerSnapshot()


def vera_reply(message: str) -> str:
    """Return a deterministic MVP response without claiming external AI access."""

    cleaned = " ".join(message.strip().split())
    if not cleaned:
        return "Tell me what you want to build, explore, organize, or understand."

    lowered = cleaned.lower()
    if "avatar" in lowered or "forge" in lowered:
        return (
            "I can help shape your avatar concept. Start with identity, silhouette, materials, "
            "equipment role, and an evolution path. Minting and marketplace actions will always "
            "require explicit approval."
        )
    if "wallet" in lowered or "coin" in lowered or "neo" in lowered:
        return (
            "Your MVP wallet shows local demonstration balances only. The production wallet will "
            "use the separate ACoin double-entry ledger and authenticated settlement events."
        )
    if "quest" in lowered:
        return (
            "Recommended first quest: define your avatar origin, select one companion capability, "
            "and complete the governance tutorial before entering the wider universe."
        )
    if "permission" in lowered or "governance" in lowered:
        return (
            "NeoGen follows permission-first operation. Read-only actions may be automatic, while "
            "spending, deployment, minting, trading, deletion, and system changes require approval."
        )
    return (
        f"I received: '{cleaned}'. In this MVP I provide deterministic guidance while the full "
        "NeoGen model router, memory engine, and agent system are being connected."
    )


LANDING_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Afterlife Neogenesis</title>
<style>
:root{color-scheme:dark;--bg:#070914;--panel:#10152b;--line:#28325e;--text:#f4f6ff;--muted:#aab3d6;--accent:#8f7cff;--accent2:#35d7ff}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,sans-serif;background:radial-gradient(circle at 50% 10%,#1a1642 0,#070914 48%);color:var(--text)}
a{color:inherit;text-decoration:none}.nav{height:72px;display:flex;align-items:center;justify-content:space-between;padding:0 5vw;border-bottom:1px solid #24294a;background:#080b18cc;backdrop-filter:blur(16px);position:sticky;top:0}.brand{font-weight:900;letter-spacing:.13em}.navlinks{display:flex;gap:18px;color:var(--muted)}
.hero{min-height:72vh;display:grid;place-items:center;text-align:center;padding:64px 20px}.hero h1{font-size:clamp(3rem,8vw,7rem);margin:0;line-height:.9;background:linear-gradient(90deg,#fff,#a89cff,#51dcff);-webkit-background-clip:text;color:transparent}.hero p{font-size:clamp(1.1rem,2vw,1.5rem);color:var(--muted);margin:28px auto;max-width:760px}.actions{display:flex;gap:14px;justify-content:center;flex-wrap:wrap}.btn{padding:14px 22px;border-radius:12px;border:1px solid var(--line);font-weight:800}.primary{background:linear-gradient(90deg,var(--accent),var(--accent2));color:#050711;border:0}.features{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;padding:0 5vw 70px}.card{background:linear-gradient(180deg,#121831,#0d1124);border:1px solid var(--line);border-radius:18px;padding:24px;min-height:160px}.card h3{margin-top:0}.card p{color:var(--muted);line-height:1.6}.status{display:inline-flex;gap:8px;align-items:center;color:#8df0c5;font-size:.9rem}.dot{width:9px;height:9px;border-radius:50%;background:#48e09e;box-shadow:0 0 14px #48e09e}footer{padding:30px 5vw;color:var(--muted);border-top:1px solid #202647}
</style>
</head>
<body>
<nav class="nav"><div class="brand">AFTERLIFE NEOGENESIS</div><div class="navlinks"><a href="#features">Explore</a><a href="/dashboard">Launch App</a></div></nav>
<main>
<section class="hero"><div><div class="status"><span class="dot"></span>Runnable MVP</div><h1>AFTERLIFE<br>NEOGENESIS</h1><p>The Persistent Digital Universe, powered by the NeoGen AI operating system. Build identity, companions, assets, memory, and legacy through a permission-first platform.</p><div class="actions"><a class="btn primary" href="/dashboard">Launch App</a><a class="btn" href="#features">Explore Universe</a></div></div></section>
<section id="features" class="features"><article class="card"><h3>VERA AI Companion</h3><p>Guidance, lore, avatar design, quests, inventory organization, and transparent approval boundaries.</p></article><article class="card"><h3>Avatar Forge</h3><p>Design records, rarity progression, equipment concepts, evolution paths, and future 3D and collectible integrations.</p></article><article class="card"><h3>Marketplace + Wallet</h3><p>A governed commerce layer prepared for the independent ACoin ledger and settlement service.</p></article><article class="card"><h3>NeoGen Governance</h3><p>Permissions, audit events, agent status, model routing, workflows, and human approval for high-risk actions.</p></article></section>
</main><footer>Afterlife Neogenesis MVP • No unverified live-hosting claims • Local-first demonstration</footer>
</body></html>"""


DASHBOARD_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Afterlife Dashboard</title>
<style>
:root{color-scheme:dark;--bg:#080a13;--panel:#111629;--panel2:#171d35;--line:#29345f;--text:#f6f7ff;--muted:#aab3d0;--accent:#927dff;--cyan:#4edcff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:Inter,system-ui,sans-serif}.top{height:64px;padding:0 22px;display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--line);background:#0b0e1b}.logo{font-weight:900;letter-spacing:.1em}.pill{padding:7px 11px;border:1px solid var(--line);border-radius:999px;color:var(--muted)}.layout{display:grid;grid-template-columns:220px 1fr 360px;min-height:calc(100vh - 64px)}.side,.assistant{padding:18px;background:#0c101f}.side{border-right:1px solid var(--line)}.assistant{border-left:1px solid var(--line);display:flex;flex-direction:column}.menu{display:grid;gap:7px}.menu button{border:0;background:transparent;color:var(--muted);text-align:left;padding:12px;border-radius:10px;font-size:1rem}.menu button:hover,.menu button.active{background:var(--panel2);color:var(--text)}.main{padding:22px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:18px}.hero{grid-column:1/-1;min-height:260px;display:grid;grid-template-columns:1.2fr 1fr;align-items:center}.avatar{height:220px;border-radius:20px;background:radial-gradient(circle at 50% 35%,#8f7cff55,transparent 42%),linear-gradient(135deg,#171d39,#0a0d19);display:grid;place-items:center;font-size:5rem;border:1px solid #394579}.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.stat{background:#0c1123;border:1px solid var(--line);border-radius:12px;padding:14px}.stat strong{font-size:1.5rem;display:block}.muted{color:var(--muted)}.chat{flex:1;overflow:auto;display:flex;flex-direction:column;gap:10px;padding:12px 0}.msg{padding:11px 13px;border-radius:12px;line-height:1.45}.vera{background:#171e3b}.user{background:#2d2757;align-self:flex-end}.composer{display:flex;gap:8px}.composer input{flex:1;background:#0a0e1c;border:1px solid var(--line);color:white;padding:12px;border-radius:10px}.composer button{border:0;border-radius:10px;padding:0 15px;font-weight:800;background:linear-gradient(90deg,var(--accent),var(--cyan));color:#070914}@media(max-width:1050px){.layout{grid-template-columns:180px 1fr}.assistant{grid-column:1/-1;border-left:0;border-top:1px solid var(--line);min-height:420px}}@media(max-width:720px){.layout{display:block}.side{border-right:0;border-bottom:1px solid var(--line)}.menu{grid-template-columns:repeat(4,1fr)}.menu button{font-size:.82rem}.grid{grid-template-columns:1fr}.hero{grid-template-columns:1fr}.stats{grid-template-columns:1fr}}
</style></head>
<body><header class="top"><a class="logo" href="/">AFTERLIFE NEOGENESIS</a><div class="pill">VERA Online • Local MVP</div></header>
<div class="layout"><aside class="side"><div class="menu"><button class="active">Dashboard</button><button>Avatar</button><button>Pets</button><button>Collection</button><button>Marketplace</button><button>Wallet</button><button>Guilds</button><button>Quests</button><button>Governance</button><button>Settings</button></div></aside>
<main class="main"><div class="grid"><section class="card hero"><div><div class="muted">Current identity</div><h1 id="playerName">Founder</h1><p class="muted">Shape your persistent identity, companion, assets, memory, and legacy.</p><div class="stats"><div class="stat"><strong id="neo">—</strong><span class="muted">NEO</span></div><div class="stat"><strong id="essence">—</strong><span class="muted">Essence</span></div><div class="stat"><strong id="items">—</strong><span class="muted">Items</span></div></div></div><div class="avatar">◈</div></section>
<section class="card"><h2>Avatar Forge</h2><p class="muted">Level <span id="level">1</span> • Rarity tier <span id="rarity">1</span>/100</p><p>Create identity, equipment concepts, and evolution paths. 3D editing and minting arrive after the governed MVP foundation.</p></section>
<section class="card"><h2>Governance</h2><p><strong id="approvals">—</strong> pending approval</p><p class="muted">Spending, minting, trading, deployment, deletion, and privileged system actions require explicit approval.</p></section>
<section class="card"><h2>Inventory</h2><p>Genesis Sigil • VERA Core • Origin Mantle • Founder Key</p><p class="muted">Demonstration inventory stored in the MVP snapshot.</p></section>
<section class="card"><h2>World Status</h2><p>Universe seed initialized.</p><p class="muted">Guilds, quests, events, persistent world state, and procedural expansion are staged behind later service milestones.</p></section></div></main>
<aside class="assistant"><h2>VERA</h2><div class="muted">Your permission-aware AI companion</div><div id="chat" class="chat"><div class="msg vera">How can I help today?</div></div><form id="form" class="composer"><input id="message" autocomplete="off" placeholder="Ask about avatars, quests, wallet, or governance"><button>Send</button></form></aside></div>
<script>
async function load(){const r=await fetch('/api/state');const s=await r.json();playerName.textContent=s.name;neo.textContent=s.neo_balance;essence.textContent=s.essence_balance;items.textContent=s.inventory_items;level.textContent=s.avatar_level;rarity.textContent=s.rarity_tier;approvals.textContent=s.pending_approvals}
form.addEventListener('submit',async e=>{e.preventDefault();const value=message.value.trim();if(!value)return;chat.insertAdjacentHTML('beforeend',`<div class="msg user"></div>`);chat.lastElementChild.textContent=value;message.value='';const r=await fetch('/api/vera',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({message:value})});const data=await r.json();chat.insertAdjacentHTML('beforeend','<div class="msg vera"></div>');chat.lastElementChild.textContent=data.reply;chat.scrollTop=chat.scrollHeight});load();
</script></body></html>"""


class AfterlifeHandler(BaseHTTPRequestHandler):
    """Serve the MVP pages and JSON endpoints."""

    server_version = "AfterlifeMVP/0.1"

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/":
            self._send_html(LANDING_HTML)
            return
        if self.path == "/dashboard":
            self._send_html(DASHBOARD_HTML)
            return
        if self.path == "/health":
            self._send_json({"status": "healthy", "service": "afterlife-mvp", "version": "0.1.0"})
            return
        if self.path == "/api/state":
            self._send_json(asdict(PLAYER))
            return
        self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/vera":
            self._send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("content-length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            message = payload.get("message", "")
            if not isinstance(message, str):
                raise ValueError("message must be a string")
        except (ValueError, json.JSONDecodeError) as exc:
            self._send_json({"error": "invalid_request", "detail": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        self._send_json({"reply": vera_reply(message), "mode": "deterministic-mvp"})

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(encoded)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)


def build_server(host: str = "127.0.0.1", port: int = 4173) -> ThreadingHTTPServer:
    """Build the local MVP HTTP server."""

    return ThreadingHTTPServer((host, port), AfterlifeHandler)


def main() -> int:
    """Run the local Afterlife Neogenesis MVP."""

    parser = argparse.ArgumentParser(description="Run the Afterlife Neogenesis MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=4173, type=int)
    args = parser.parse_args()
    server = build_server(args.host, args.port)
    print(f"Afterlife Neogenesis MVP: http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
