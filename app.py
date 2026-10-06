from flask import Flask, request, jsonify, send_from_directory
import telebot
import os
from database import (
    create_tables,
    get_groups_for_user,
    get_teammates_by_group,
    is_authorized,
    refresh_all_statuses,
    check_cooldown,
    record_action,
    create_invitation,
    get_pending_invitations_for_username,
    respond_invitation,
)
from bot import bot, TOKEN, send_wake_up, send_anonymous_nudge
from database import (
    create_tables,
    get_groups_by_owner,
    get_teammates_by_group,
    is_group_owner,
    refresh_all_statuses,
    check_cooldown,
    record_action,
)

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
@app.route("/api/groups")
def api_groups():
    user_id = request.args.get("user_id", type=int)
    if not user_id:
        return jsonify({"error": "user_id required"}), 400
    groups = get_groups_for_user(user_id)
    return jsonify([{"chat_id": g[0], "title": g[1], "role": g[2]} for g in groups])


@app.route("/api/groups/<chat_id>/members")
def api_members(chat_id):
    chat_id = int(chat_id)
    user_id = request.args.get("user_id", type=int)
    if not user_id or not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    refresh_all_statuses()  # recalculate every time someone checks, not just on new messages
    members = get_teammates_by_group(chat_id)
    return jsonify([
        {
            "telegram_id": m[1], "name": m[3], "username": m[4],
            "last_seen": m[5], "status": m[6],
        } for m in members
    ])

@app.route("/api/wakeup", methods=["POST"])
def api_wakeup():
    data = request.json
    chat_id, username, user_id = data["chat_id"], data["username"], data["user_id"]
    if not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    allowed, remaining = check_cooldown(chat_id, username)
    if not allowed:
        return jsonify({"ok": False, "cooldown": remaining, "error": f"On cooldown for {remaining}s"})
    success = send_wake_up(chat_id, username)
    if success:
        record_action(chat_id, username)
    return jsonify({"ok": success})


@app.route("/api/nudge", methods=["POST"])
def api_nudge():
    data = request.json
    chat_id, username, user_id = data["chat_id"], data["username"], data["user_id"]
    if not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    allowed, remaining = check_cooldown(chat_id, username)
    if not allowed:
        return jsonify({"ok": False, "cooldown": remaining, "error": f"On cooldown for {remaining}s"})
    success = send_anonymous_nudge(chat_id, username)
    if success:
        record_action(chat_id, username)
    return jsonify({"ok": success})


@app.route("/api/wakeup-all", methods=["POST"])
def api_wakeup_all():
    data = request.json
    chat_id, user_id = data["chat_id"], data["user_id"]
    if not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    members = get_teammates_by_group(chat_id)
    ghosts = [m for m in members if m[6] == "ghosting"]
    sent = 0
    for m in ghosts:
        allowed, _ = check_cooldown(chat_id, m[4])
        if allowed and send_wake_up(chat_id, m[4]):
            record_action(chat_id, m[4])
            sent += 1
    return jsonify({"ok": True, "count": sent})


@app.route("/api/nudge-all", methods=["POST"])
def api_nudge_all():
    data = request.json
    chat_id, user_id = data["chat_id"], data["user_id"]
    if not is_group_owner(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    members = get_teammates_by_group(chat_id)
    quiet = [m for m in members if m[6] == "quiet"]
    sent = 0
    for m in quiet:
        allowed, _ = check_cooldown(chat_id, m[4])
        if allowed and send_anonymous_nudge(chat_id, m[4]):
            record_action(chat_id, m[4])
            sent += 1
    return jsonify({"ok": True, "count": sent})


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{TOKEN}")
    print(f"Webhook set to {WEBHOOK_URL}/webhook/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

from database import is_username_in_group  # add to imports

from database import can_invite_again, get_invite_history  # add to imports

@app.route("/api/invite", methods=["POST"])
def api_invite():
    data = request.json
    chat_id, username, user_id = data["chat_id"], data["username"], data["user_id"]
    if not is_authorized(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    if not is_username_in_group(chat_id, username):
        return jsonify({"error": "That username hasn't sent a message in this group yet"}), 400

    allowed, remaining = can_invite_again(chat_id, username)
    if not allowed:
        hours = remaining // 3600
        return jsonify({"error": f"Already invited today. Try again in {hours}h"}), 429

    create_invitation(chat_id, username, user_id)
    return jsonify({"ok": True})


@app.route("/api/groups/<chat_id>/invite-history")
def api_invite_history(chat_id):
    chat_id = int(chat_id)
    user_id = request.args.get("user_id", type=int)
    if not user_id or not is_authorized(chat_id, user_id):
        return jsonify({"error": "not authorized"}), 403
    history = get_invite_history(chat_id)
    return jsonify([
        {"username": h[0], "status": h[1], "created_at": h[2].isoformat()}
        for h in history
    ])


@app.route("/api/invitations")
def api_invitations():
    username = request.args.get("username", type=str)
    if not username:
        return jsonify([])
    invites = get_pending_invitations_for_username(username)
    return jsonify([
        {"id": i[0], "chat_id": i[1], "group_title": i[2], "invited_by": i[3]}
        for i in invites
    ])


@app.route("/api/invitations/<int:invitation_id>/respond", methods=["POST"])
def api_respond_invitation(invitation_id):
    data = request.json
    user_id, accept = data["user_id"], data["accept"]
    success = respond_invitation(invitation_id, user_id, accept)
    return jsonify({"ok": success})