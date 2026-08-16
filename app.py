from flask import Flask, request, jsonify, send_from_directory, g
import telebot
import os
import urllib.parse
import hmac
import hashlib
import json
from functools import wraps
from database import (
    create_tables,
    get_groups_for_user,
    get_teammates_by_group,
    is_authorized,
    is_username_in_group,
    refresh_all_statuses,
    check_cooldown,
    record_action,
    get_cooldowns_for_group,
    create_invitation,
    can_invite_again,
    get_pending_invitations_for_username,
    get_invite_history,
    respond_invitation,
)
from bot import bot, TOKEN, send_wake_up, send_anonymous_nudge

# ---------- TELEGRAM AUTHENTICATION DECORATOR ----------
def verify_telegram_init_data(init_data: str, bot_token: str) -> dict:
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data))
        if "hash" not in parsed_data:
            return None
        
        received_hash = parsed_data.pop("hash")
        
        sorted_items = sorted(parsed_data.items())
        data_check_string = "\n".join([f"{k}={v}" for k, v in sorted_items])
        
        secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()
        
        if computed_hash == received_hash:
            user_data = json.loads(parsed_data.get("user", "{}"))
            return user_data
    except Exception as e:
        print(f"Error validating initData: {e}")
    return None

def require_telegram_user(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        init_data = request.headers.get("X-Telegram-Init-Data")
        
        if init_data:
            user_data = verify_telegram_init_data(init_data, TOKEN)
            if not user_data:
                return jsonify({"error": "Invalid Telegram session"}), 401
            g.user_id = user_data.get("id")
            g.username = user_data.get("username")
        else:
            is_vercel = os.getenv("VERCEL") == "1"
            if is_vercel:
                return jsonify({"error": "Missing Telegram session"}), 401
            
            user_id = request.args.get("user_id", type=int)
            username = request.args.get("username", type=str)
            if not user_id and request.is_json:
                data = request.get_json(silent=True) or {}
                user_id = data.get("user_id")
                username = data.get("username")
            
            if not user_id:
                return jsonify({"error": "User authentication required"}), 400
            
            g.user_id = int(user_id)
            g.username = username
            
        return f(*args, **kwargs)
    return decorated_function


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=os.path.join(BASE_DIR, "webapp"))

# ---------- VERCEL WSGI PATH MIDDLEWARE ----------
# Overrides PATH_INFO with Vercel's original request URI to fix rewrite routing.
class VercelPathMiddleware(object):
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        import sys
        print("--- DEBUG WSGI ENVIRON ---", file=sys.stderr)
        for k, v in sorted(environ.items()):
            if k.startswith('HTTP_') or k in ('PATH_INFO', 'REQUEST_URI', 'QUERY_STRING', 'REQUEST_METHOD'):
                print(f"  {k}: {v}", file=sys.stderr)
        print("-------------------------", file=sys.stderr)

        x_forwarded_uri = environ.get('HTTP_X_FORWARDED_URI')
        if x_forwarded_uri:
            path = x_forwarded_uri.split('?')[0]
            environ['PATH_INFO'] = path
            print(f"Overrode PATH_INFO to: {path}", file=sys.stderr)
        return self.app(environ, start_response)

app.wsgi_app = VercelPathMiddleware(app.wsgi_app)

create_tables()

WEBHOOK_URL = os.getenv("WEBHOOK_URL")


# ---------- TELEGRAM WEBHOOK ----------
@app.route(f"/webhook/{TOKEN}", methods=["POST"])
def telegram_webhook():
    json_str = request.stream.read().decode("utf-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    refresh_all_statuses()
    return "OK", 200


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


# ---------- GROUPS & MEMBERS ----------
@app.route("/api/groups")
@require_telegram_user
def api_groups():
    groups = get_groups_for_user(g.user_id)
    return jsonify([{"chat_id": g[0], "title": g[1], "role": g[2]} for g in groups])


@app.route("/api/groups/<chat_id>/members")
@require_telegram_user
def api_members(chat_id):
    chat_id = int(chat_id)
    if not is_authorized(chat_id, g.user_id):
        return jsonify({"error": "not authorized"}), 403

    refresh_all_statuses()  # recalculate + auto-clear cooldowns for anyone now active
    members = get_teammates_by_group(chat_id)
    cooldowns = get_cooldowns_for_group(chat_id)  # {username: seconds_remaining}

    return jsonify([
        {
            "telegram_id": m[1],
            "name": m[3],
            "username": m[4],
            "last_seen": m[5],
            "status": m[6],
            "cooldown_remaining": cooldowns.get(m[4], 0),
        } for m in members
    ])


# ---------- ACTIONS ----------
@app.route("/api/wakeup", methods=["POST"])
@require_telegram_user
def api_wakeup():
    data = request.json
    chat_id, username = data["chat_id"], data["username"]
    if not is_authorized(chat_id, g.user_id):
        return jsonify({"error": "not authorized"}), 403

    allowed, remaining = check_cooldown(chat_id, username)
    if not allowed:
        return jsonify({"ok": False, "cooldown": remaining, "error": f"On cooldown for {remaining}s"})

    success = send_wake_up(chat_id, username)
    if success:
        record_action(chat_id, username)
    return jsonify({"ok": success})


@app.route("/api/nudge", methods=["POST"])
@require_telegram_user
def api_nudge():
    data = request.json
    chat_id, username = data["chat_id"], data["username"]
    if not is_authorized(chat_id, g.user_id):
        return jsonify({"error": "not authorized"}), 403

    allowed, remaining = check_cooldown(chat_id, username)
    if not allowed:
        return jsonify({"ok": False, "cooldown": remaining, "error": f"On cooldown for {remaining}s"})

    success = send_anonymous_nudge(chat_id, username)
    if success:
        record_action(chat_id, username)
    return jsonify({"ok": success})


@app.route("/api/wakeup-all", methods=["POST"])
@require_telegram_user
def api_wakeup_all():
    data = request.json
    chat_id = data["chat_id"]
    if not is_authorized(chat_id, g.user_id):
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
@require_telegram_user
def api_nudge_all():
    data = request.json
    chat_id = data["chat_id"]
    if not is_authorized(chat_id, g.user_id):
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


# ---------- INVITATIONS ----------
@app.route("/api/invite", methods=["POST"])
@require_telegram_user
def api_invite():
    data = request.json
    chat_id, username = data["chat_id"], data["username"]
    if not is_authorized(chat_id, g.user_id):
        return jsonify({"error": "not authorized"}), 403
    if not is_username_in_group(chat_id, username):
        return jsonify({"error": "That username hasn't sent a message in this group yet"}), 400

    allowed, remaining = can_invite_again(chat_id, username)
    if not allowed:
        hours = remaining // 3600
        return jsonify({"error": f"Already invited today. Try again in {hours}h"}), 429

    create_invitation(chat_id, username, g.user_id)
    return jsonify({"ok": True})


@app.route("/api/invitations")
@require_telegram_user
def api_invitations():
    if not g.username:
        return jsonify([])
    invites = get_pending_invitations_for_username(g.username)
    return jsonify([
        {"id": i[0], "chat_id": i[1], "group_title": i[2], "invited_by": i[3]}
        for i in invites
    ])


@app.route("/api/groups/<chat_id>/invite-history")
@require_telegram_user
def api_invite_history(chat_id):
    chat_id = int(chat_id)
    if not is_authorized(chat_id, g.user_id):
        return jsonify({"error": "not authorized"}), 403
    history = get_invite_history(chat_id)
    return jsonify([
        {"username": h[0], "status": h[1], "created_at": h[2].isoformat()}
        for h in history
    ])


@app.route("/api/invitations/<int:invitation_id>/respond", methods=["POST"])
@require_telegram_user
def api_respond_invitation(invitation_id):
    data = request.json
    accept = data["accept"]
    success = respond_invitation(invitation_id, g.user_id, accept)
    return jsonify({"ok": success})


# ---------- SETUP WEBHOOK ----------
@app.route("/api/setup-webhook", methods=["GET", "POST"])
def setup_webhook():
    webhook_url = os.getenv("WEBHOOK_URL")
    if not webhook_url:
        return jsonify({"ok": False, "error": "WEBHOOK_URL environment variable is not set"}), 400
    
    if not webhook_url.startswith("http://") and not webhook_url.startswith("https://"):
        webhook_url = f"https://{webhook_url}"
        
    full_url = f"{webhook_url}/webhook/{TOKEN}"
    try:
        bot.remove_webhook()
        success = bot.set_webhook(url=full_url)
        if success:
            return jsonify({"ok": True, "message": f"Webhook successfully set to {full_url}"})
        else:
            return jsonify({"ok": False, "error": "Telegram set_webhook returned False"}), 500
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


if __name__ == "__main__":
    bot.remove_webhook()
    bot.set_webhook(url=f"{WEBHOOK_URL}/webhook/{TOKEN}")
    print(f"Webhook set to {WEBHOOK_URL}/webhook/{TOKEN}")
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))

#fixer