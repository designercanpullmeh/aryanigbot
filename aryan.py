import asyncio
import uuid
import os
import json
import threading
import requests
import time
import random
from collections import defaultdict
from flask import Flask, jsonify, Response
from instagrapi import Client
from instagrapi.exceptions import RateLimitError
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.align import Align
from dotenv import load_dotenv

load_dotenv()

ACC_COUNT = int(os.getenv("ACC_COUNT", "0"))
MESSAGE_DATA = os.getenv("MESSAGE_DATA", "")
_raw_titles = os.getenv("TITLES", "")
def parse_titles(raw: str):
    raw = raw.strip()
    if raw.startswith("(") and raw.endswith(")"):
        raw = raw[1:-1]
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    titles = []
    for p in parts:
        if (p.startswith('"') and p.endswith('"')) or (p.startswith("'") and p.endswith("'")):
            titles.append(p[1:-1])
        else:
            titles.append(p)
    return titles

TITLES = parse_titles(_raw_titles)

MSG_DELAY = int(os.getenv("MSG_DELAY", 40))
GROUP_DELAY = int(os.getenv("GROUP_DELAY", 4))

DOC_ID = os.getenv("DOC_ID", "29088580780787855")
IG_APP_ID = os.getenv("IG_APP_ID", "936619743392459")

FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.environ.get("PORT", os.getenv("FLASK_PORT", 5000)))

SELF_URL = os.getenv("SELF_URL")
SELF_PING_INTERVAL = int(os.getenv("SELF_PING_INTERVAL", 100))

app = Flask(__name__)
LOG_BUFFER = []

logs_ui = defaultdict(list)
console = Console()
USERS = []
MESSAGE_BLOCKS = []

@app.route('/')
def home():
    return "alive"

@app.route('/status')
def status():
    return jsonify({user: logs_ui[user] for user in USERS})

@app.route('/logs')
def logs_route():
    output = []
    header_text = "✦  SINISTERS | SX⁷  ✦"
    output.append(header_text)
    output.append("=" * len(header_text))
    output.append("")
    for user in USERS:
        output.append(f"[ {user} ]")
        output.append("-" * (len(user) + 4))
        for line in logs_ui[user]:
            output.append(line)
        output.append("")
    return Response("\n".join(output), mimetype="text/plain")

@app.route("/dashboard")
def dashboard():
    html = """
    <html>
    <head>
        <title>SINISTERS | SX⁷</title>
        <meta http-equiv="refresh" content="2">
        <style>
            body { background-color: #0d1117; font-family: monospace; margin: 0; padding: 20px; color: #00ff88; }
            .header { text-align: center; font-size: 28px; font-weight: bold; margin-bottom: 30px; border: 2px solid #00ff88; padding: 10px; }
            .container { display: flex; flex-direction: row; gap: 20px; align-items: flex-start; }
            .panel { flex: 1; min-width: 300px; border: 2px solid #00ff88; background-color: #111827; padding: 15px; height: 80vh; overflow-y: auto; }
            .panel-title { font-weight: bold; margin-bottom: 10px; border-bottom: 1px solid #00ff88; padding-bottom: 5px; }
            .log-line { margin-bottom: 6px; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <div class="header">✦ SINISTERS | SX⁷ ✦</div>
        <div class="container">
    """
    for user in USERS:
        html += f'<div class="panel"><div class="panel-title">{user}</div>'
        for line in logs_ui[user]:
            html += f'<div class="log-line">{line}</div>'
        html += "</div>"
    html += """
        </div>
        <script>
        function scrollPanels() {
            document.querySelectorAll('.panel').forEach(function(panel) {
                panel.scrollTop = panel.scrollHeight;
            });
        }
        window.onload = scrollPanels;
        setInterval(scrollPanels, 1500);
        </script>
    </body>
    </html>
    """
    return html

def log(console_message, clean_message=None):
    LOG_BUFFER.append(clean_message if clean_message else console_message)

def self_ping_loop():
    while True:
        if SELF_URL:
            try:
                requests.get(SELF_URL, timeout=10)
                log("🔁 Self ping successful")
            except Exception as e:
                log(f"⚠ Self ping failed: {e}")
        time.sleep(SELF_PING_INTERVAL)

MAX_PANEL_LINES = 35

def ui_log(user, message):
    if message.startswith("⏳ ROUND"):
        header = logs_ui[user][0] if logs_ui[user] else f"🍸 ID - {user}"
        logs_ui[user] = [header, message]
        log(f"{user} | {message}", message)
        return
    logs_ui[user].append(message)
    if len(logs_ui[user]) < 2:
        log(f"{user} | {message}", message)
        return
    header = logs_ui[user][0]
    round_line = logs_ui[user][1]
    body = logs_ui[user][2:]
    if len(body) > MAX_PANEL_LINES:
        body.pop(0)
    logs_ui[user] = [header, round_line] + body
    log(f"{user} | {message}", message)

def start_flask():
    import logging
    logg = logging.getLogger('werkzeug')
    logg.disabled = True
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

def load_accounts_from_env():
    accounts = []
    for i in range(1, ACC_COUNT + 1):
        user = os.getenv(f"ACC_{i}_USER", "").strip()
        password = os.getenv(f"ACC_{i}_PASS", "").strip()
        proxy = os.getenv(f"ACC_{i}_PROXY", "").strip()
        if user and password:
            accounts.append((user, password, proxy or None))
    return accounts[:5]

def load_titles_from_env():
    return TITLES[:] if TITLES else []

def load_message_blocks_from_env():
    raw_blocks = MESSAGE_DATA.split(",")
    blocks = []
    for block in raw_blocks:
        cleaned = block.strip("\n")
        if cleaned.strip():
            blocks.append(cleaned)
    return blocks

def build_layout():
    layout = Layout()
    layout.split_column(Layout(name="header", size=6), Layout(name="body"))
    layout["body"].split_row(*[Layout(name=user) for user in USERS])
    header_layout = Layout()
    header_layout.split_column(
        Layout(Panel(Align.center("[bold bright_green]SINISTERS | SX⁷[/bold bright_green]"), border_style="bright_green"), size=3),
        Layout(Panel(Align.center("[bold bright_green]MAHABHARAT | ASTRA[/bold bright_green]"), border_style="bright_green"), size=3),
    )
    layout["header"].update(header_layout)
    return layout

def render_layout(layout):
    for user in USERS:
        content = "\n".join(logs_ui[user])
        panel = Panel(
            content,
            title=f"[bold bright_green]{user}[/bold bright_green]",
            border_style="bright_green",
            padding=(0, 1),
            expand=True
        )
        layout["body"][user].update(panel)

def setup_mobile_fingerprint(cl):
    cl.set_user_agent("Instagram 312.0.0.22.114 Android")
    uuids = {
        "phone_id": str(uuid.uuid4()),
        "uuid": str(uuid.uuid4()),
        "client_session_id": str(uuid.uuid4()),
        "advertising_id": str(uuid.uuid4()),
        "device_id": "android-" + uuid.uuid4().hex[:16]
    }
    cl.set_uuids(uuids)
    cl.private.headers.update({
        "X-IG-App-ID": IG_APP_ID,
        "X-IG-Device-ID": uuids["uuid"],
        "X-IG-Android-ID": uuids["device_id"],
    })

async def login(username, password, proxy):
    cl = Client()
    if proxy:
        cl.set_proxy(proxy)
    setup_mobile_fingerprint(cl)
    session_file = f"session_{username}.json"
    try:
        if os.path.exists(session_file):
            cl.load_settings(session_file)
        cl.login(username, password)
        cl.dump_settings(session_file)
        return cl
    except Exception:
        return None

def rename_thread(cl, thread_id, title):
    try:
        cl.private_request(f"direct_v2/threads/{thread_id}/update_title/", data={"title": title})
        return True
    except RateLimitError:
        return False
    except Exception:
        return False

async def gc_send_loop(username, cl, gid, index, total, get_block, delay):
    i = 1
    while True:
        active_block = get_block()
        if active_block:
            try:
                await asyncio.to_thread(cl.direct_send, active_block, thread_ids=[gid])
            except Exception:
                pass
            ui_log(username, f"📨 → GC {index}/{total} | SEND {i}")
        i += 1
        await asyncio.sleep(delay)

async def gc_rename_loop(username, cl, gid, get_titles, delay):
    last_title = None
    used = set()
    j = 1
    while True:
        titles = get_titles()
        if not titles:
            await asyncio.sleep(delay)
            continue

        available = [t for t in titles if t != last_title and t not in used]
        if not available:
            used.clear()
            available = [t for t in titles if t != last_title]

        title = random.choice(available)
        used.add(title)
        last_title = title

        try:
            success = await asyncio.to_thread(rename_thread, cl, gid, title)
            if success:
                ui_log(username, f"💠 → {title} | GC RENAME {j}")
            else:
                ui_log(username, "⚠ Rename failed")
        except Exception:
            ui_log(username, "⚠ Rename error")

        j += 1
        await asyncio.sleep(delay)

async def worker(username, password, proxy, cl):
    round_number = 1
    while True:
        try:
            threads = await asyncio.to_thread(cl.direct_threads, amount=100)
        except Exception:
            await asyncio.sleep(60)
            continue

        groups = [t for t in threads if getattr(t, "is_group", False)]
        total = len(groups)
        if total == 0:
            await asyncio.sleep(60)
            continue

        ui_log(username, f"⏳ ROUND {round_number} | GCS → {total}")

        titles_snapshot = load_titles_from_env()

        def get_titles():
            return titles_snapshot

        def get_block():
            if not MESSAGE_BLOCKS:
                return None
            idx = (round_number - 1) % len(MESSAGE_BLOCKS)
            return MESSAGE_BLOCKS[idx]

        tasks = []
        for index, thread in enumerate(groups, start=1):
            gid = thread.id
            tasks.append(asyncio.create_task(gc_send_loop(username, cl, gid, index, total, get_block, MSG_DELAY)))
            tasks.append(asyncio.create_task(gc_rename_loop(username, cl, gid, get_titles, 240)))

        await asyncio.gather(*tasks)
        round_number += 1

async def main():
    ACCOUNTS = load_accounts_from_env()
    global MESSAGE_BLOCKS
    MESSAGE_BLOCKS = load_message_blocks_from_env()
    clients = []
    for username, password, proxy in ACCOUNTS:
        cl = await login(username, password, proxy)
        if cl:
            USERS.append(username)
            ui_log(username, f"🍸 ID - {username}")
            clients.append((username, password, proxy, cl))
    if not USERS:
        return
    layout = build_layout()
    for u, p, pr, cl in clients:
        asyncio.create_task(worker(u, p, pr, cl))
    with Live(layout, console=console, refresh_per_second=5, screen=True) as live:
        while True:
            render_layout(layout)
            live.refresh()
            await asyncio.sleep(0.2)

if __name__ == "__main__":
    threading.Thread(target=self_ping_loop, daemon=True).start()
    threading.Thread(target=lambda: asyncio.run(main()), daemon=True).start()
    start_flask()
