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

ACC_FILE = os.getenv("ACC_FILE", "acc.txt")
MESSAGE_FILE = os.getenv("MESSAGE_FILE", "text.txt")
TITLE_FILE = os.getenv("TITLE_FILE", "nc.txt")

MSG_DELAY = int(os.getenv("MSG_DELAY", 40))
GROUP_DELAY = int(os.getenv("GROUP_DELAY", 4))

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

# 🔥 RANDOM EMOJIS LIST
EMOJIS = ["🔥","⚡","💀","😈","🚀","💎","🎯","👑","🖤","✨","🌪️","🧨","🎭","🐍","🧿"]

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
    html = "<html><body style='background:#0d1117;color:#00ff88;font-family:monospace;'>"
    html += "<h1 style='text-align:center;'>SINISTERS | SX⁷</h1><div style='display:flex;'>"
    for user in USERS:
        html += f"<div style='margin:10px;border:1px solid #00ff88;padding:10px;width:300px;'>"
        html += f"<h3>{user}</h3>"
        for line in logs_ui[user]:
            html += f"<div>{line}</div>"
        html += "</div>"
    html += "</div></body></html>"
    return html

def log(console_message, clean_message=None):
    LOG_BUFFER.append(clean_message if clean_message else console_message)

def self_ping_loop():
    while True:
        if SELF_URL:
            try:
                requests.get(SELF_URL, timeout=10)
            except:
                pass
        time.sleep(SELF_PING_INTERVAL)

def ui_log(user, message):
    logs_ui[user].append(message)
    if len(logs_ui[user]) > 40:
        logs_ui[user].pop(0)

def start_flask():
    import logging
    logging.getLogger('werkzeug').disabled = True
    app.run(host=FLASK_HOST, port=FLASK_PORT, debug=False, use_reloader=False)

def load_accounts(path):
    accounts = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 2:
                username = parts[0].strip()
                password = parts[1].strip()
                proxy = parts[2].strip() if len(parts) >= 3 else None
                accounts.append((username, password, proxy))
    return accounts[:5]

def load_lines(path):
    with open(path, "r", encoding="utf-8") as f:
        return [x.strip() for x in f if x.strip()]

def load_message_blocks(path):
    with open(path, "r", encoding="utf-8") as f:
        return [x.strip() for x in f.read().split(",") if x.strip()]

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
    try:
        cl.login(username, password)
        return cl
    except:
        return None

# 🔥 ADD EMOJI HERE
def add_random_emoji(title):
    return f"{title} {random.choice(EMOJIS)}"

def rename_thread(cl, thread_id, title):
    try:
        title = add_random_emoji(title)  # 🔥 emoji added here
        cl.private_request(
            f"direct_v2/threads/{thread_id}/update_title/",
            data={"title": title}
        )
        return title
    except:
        return None

async def gc_send_loop(username, cl, gid, get_block):
    i = 1
    while True:
        block = get_block()
        if block:
            try:
                await asyncio.to_thread(cl.direct_send, block, thread_ids=[gid])
                ui_log(username, f"📨 Sent {i}")
            except:
                pass
        i += 1
        await asyncio.sleep(MSG_DELAY)

async def gc_rename_loop(username, cl, gid, get_titles):
    while True:
        titles = get_titles()
        if titles:
            title = random.choice(titles)
            new_title = await asyncio.to_thread(rename_thread, cl, gid, title)
            if new_title:
                ui_log(username, f"💠 {new_title}")
            else:
                ui_log(username, "⚠ Rename failed")
        await asyncio.sleep(240)

async def worker(username, password, proxy, cl):
    while True:
        try:
            threads = await asyncio.to_thread(cl.direct_threads, amount=50)
            groups = [t for t in threads if getattr(t, "is_group", False)]
        except:
            await asyncio.sleep(60)
            continue

        if not groups:
            await asyncio.sleep(60)
            continue

        titles = load_lines(TITLE_FILE) if os.path.exists(TITLE_FILE) else []

        def get_titles():
            return titles

        def get_block():
            return random.choice(MESSAGE_BLOCKS) if MESSAGE_BLOCKS else None

        for thread in groups:
            gid = thread.id
            asyncio.create_task(gc_send_loop(username, cl, gid, get_block))
            asyncio.create_task(gc_rename_loop(username, cl, gid, get_titles))

        await asyncio.sleep(999999)

async def main():
    ACCOUNTS = load_accounts(ACC_FILE)
    global MESSAGE_BLOCKS
    MESSAGE_BLOCKS = load_message_blocks(MESSAGE_FILE)

    clients = []
    for username, password, proxy in ACCOUNTS:
        cl = await login(username, password, proxy)
        if cl:
            USERS.append(username)
            clients.append((username, password, proxy, cl))

    for u, p, pr, cl in clients:
        asyncio.create_task(worker(u, p, pr, cl))

    while True:
        await asyncio.sleep(1)

if __name__ == "__main__":
    threading.Thread(target=start_flask, daemon=True).start()
    threading.Thread(target=self_ping_loop, daemon=True).start()
    asyncio.run(main())
