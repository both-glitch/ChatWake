from flask import Flask, request, jsonify, send_from_directory
import telebot
import os
from database import (
    create_tables,
    get_groups_by_owner,
    get_teammates_by_group,
    is_group_owner,
    refresh_all_statuses,
)
from bot import bot, TOKEN, send_wake_up, send_anonymous_nudge

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "webapp"))

create_tables()

# Render gives you this automatically once deployed, e.g.
# https://chatwake.onrender.com -- set it as an env var after first deploy.
WEBHOOK_URL = os.getenv("WEBHOOK_URL")


# ---------- TELEGRAM WEBHOOK ----------
# Telegram POSTs updates here instead of us polling forever.
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def telegram_webhook():
    json_str = request.stream.read().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    refresh_all_statuses()  # recalc everyone's status on every incoming update
    return "OK", 200


# ---------- OPTIONAL: force a status refresh even with no new messages ----------
# Point a free Render Cron Job (or cron-job.org) at this URL every few minutes
# so ghosting/quiet status updates even during silence, not just on new messages.
@app.route("/api/refresh-statuses", methods=["POST", "GET"])
def api_refresh_statuses():
    refresh_all_statuses()
    return jsonify({"ok": True})


# ---------- MINI APP FRONTEND ----------
@app.route("/")
def serve_index():
    return send_from_directory(app.static_folder, "index.html")


@app.route("/<path:filename>")
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)


# ---------- MINI APP API ----------
@app.route("/api/groups")
def api_groups():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    groups = get_groups_by_owner(user_id)
    return jsonify([{"chat_id": g[0], "title": g[1]} for g in groups])


@app.route("/api/groups/<chat_id>/members")
def api_members(chat_id):
    chat_id = int(chat_id)  # manually convert, since Flask's <int:> converter rejects negative numbers
    user_id = request.args.get("user_id", type=int)
    if not user_id or not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    members = get_teammates_by_group(chat_id)
    return jsonify([
        {
            "telegram_id": m[1], "name": m[3], "username": m[4],
            "last_seen": m[5], "status": m[6],
        } for m in members
    ])


@app.route("/api/wakeup-all", methods=["POST"])
def api_wakeup_all():
    data = request.json
    chat_id, user_id = data["chat_id"], data["user_id"]
    if not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    members = get_teammates_by_group(chat_id)
    ghosts = [m for m in members if m[6] == "ghosting"]
    for m in ghosts:
        send_wake_up(chat_id, m[4])
    return jsonify({"ok": True, "count": len(ghosts)})


@app.route("/api/nudge-all", methods=["POST"])
def api_nudge_all():
    data = request.json
    chat_id, user_id = data["chat_id"], data["user_id"]
    if not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    members = get_teammates_by_group(chat_id)
    quiet = [m for m in members if m[6] == "quiet"]
    for m in quiet:
        send_anonymous_nudge(chat_id, m[4])
    return jsonify({"ok": True, "count": len(quiet)})


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{TOKEN}")
    print(f"Webhook set to {WEBHOOK_URL}/webhook/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))