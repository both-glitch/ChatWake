import psycopg2
import os
from datetime import datetime, timezone

DATABASE_URL = os.getenv("DATABASE_URL")

QUIET_THRESHOLD_SECONDS = 30
GHOST_THRESHOLD_SECONDS = 60
COOLDOWN_SECONDS = 120  #2 minutes

def get_conn():
    return psycopg2.connect(DATABASE_URL)


def create_tables():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS groups (
            chat_id BIGINT PRIMARY KEY,
            title TEXT,
            owner_id BIGINT,
            folder_id INTEGER DEFAULT NULL
        )
    """)
    cursor.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS quiet_limit INTEGER DEFAULT 30")
    cursor.execute("ALTER TABLE groups ADD COLUMN IF NOT EXISTS ghost_limit INTEGER DEFAULT 60")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teammates (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            chat_id BIGINT,
            name TEXT,
            username TEXT,
            last_seen TEXT,
            status TEXT DEFAULT 'active',
            UNIQUE(telegram_id, chat_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            color TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folder_maps (
            chat_id BIGINT,
            folder_id INTEGER,
            PRIMARY KEY (chat_id, folder_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS action_cooldowns (
            chat_id BIGINT,
            username TEXT,
            last_sent TIMESTAMP,
            PRIMARY KEY (chat_id, username)
        )
    """)
    # People who've been invited and accepted -- get the same access as the owner
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_access (
            chat_id BIGINT,
            user_id BIGINT,
            role TEXT DEFAULT 'collaborator',
            PRIMARY KEY (chat_id, user_id)
        )
    """)
    # Pending invites -- stored by username since we don't know their user_id yet
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS invitations (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            invited_username TEXT,
            invited_by BIGINT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def save_group(chat_id, title, owner_id=None):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO groups (chat_id, title, owner_id) VALUES (%s, %s, %s)
        ON CONFLICT (chat_id) DO NOTHING
    """, (chat_id, title, owner_id))
    cursor.execute("UPDATE groups SET title = %s WHERE chat_id = %s", (title, chat_id))
    if owner_id is not None:
        cursor.execute(
            "UPDATE groups SET owner_id = %s WHERE chat_id = %s AND owner_id IS NULL",
            (owner_id, chat_id)
        )
    conn.commit()
    cursor.close()
    conn.close()


def delete_group(chat_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE chat_id = %s", (chat_id,))
    cursor.execute("DELETE FROM teammates WHERE chat_id = %s", (chat_id,))
    cursor.execute("DELETE FROM folder_maps WHERE chat_id = %s", (chat_id,))
    conn.commit()
    cursor.close()
    conn.close()


def get_all_groups():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def get_groups_by_owner(owner_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups WHERE owner_id = %s", (owner_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def is_username_in_group(chat_id, username):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM teammates WHERE chat_id = %s AND LOWER(username) = %s",
        (chat_id, username.lower())
    )
    exists = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return exists

def is_group_owner(chat_id, user_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT owner_id FROM groups WHERE chat_id = %s", (chat_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row is not None and row[0] == user_id


def add_custom_folder(name, color):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO folders (name, color) VALUES (%s, %s) RETURNING id", (name, color))
    folder_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return folder_id


def get_all_folders():
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, color FROM folders")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def assign_group_to_folder(chat_id, folder_id):
    if folder_id is None:
        return
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO folder_maps (chat_id, folder_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
        (chat_id, folder_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


def get_groups_by_folder(folder_id):
    conn = get_conn()
    cursor = conn.cursor()
    if folder_id is None:
        cursor.execute("SELECT chat_id, title FROM groups")
    else:
        cursor.execute("""
            SELECT g.chat_id, g.title
            FROM folder_maps f
            JOIN groups g ON f.chat_id = g.chat_id
            WHERE f.folder_id = %s
        """, (folder_id,))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def save_teammate(telegram_id, chat_id, name, username, last_seen):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO teammates (telegram_id, chat_id, name, username, last_seen, status)
        VALUES (%s, %s, %s, %s, %s, 'active')
        ON CONFLICT (telegram_id, chat_id) DO UPDATE SET
            name = EXCLUDED.name,
            username = EXCLUDED.username,
            last_seen = EXCLUDED.last_seen,
            status = 'active'
    """, (telegram_id, chat_id, name, username, last_seen))
    conn.commit()
    cursor.close()
    conn.close()


def get_teammates_by_group(chat_id):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, telegram_id, chat_id, name, username, last_seen, status
        FROM teammates
        WHERE chat_id = %s
        ORDER BY last_seen DESC
    """, (chat_id,))
    teammates = cursor.fetchall()
    cursor.close()
    conn.close()
    return teammates


def update_status(telegram_id, chat_id, status):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE teammates SET status = %s WHERE telegram_id = %s AND chat_id = %s",
        (status, telegram_id, chat_id)
    )
    conn.commit()
    cursor.close()
    conn.close()


# Replace your current refresh_all_statuses loop with this updated query:
def refresh_all_statuses():
    conn = get_conn()
    cursor = conn.cursor()
    # Grabs limits from the group table side-by-side with teammates
    cursor.execute("""
        SELECT t.telegram_id, t.chat_id, t.last_seen, g.quiet_limit, g.ghost_limit 
        FROM teammates t
        JOIN groups g ON t.chat_id = g.chat_id
    """)
    rows = cursor.fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for telegram_id, chat_id, last_seen_str, q_lim, g_lim in rows:
        last_seen_time = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
        seconds_inactive = (now - last_seen_time).total_seconds()
        
        if seconds_inactive >= g_lim:
            new_status = "ghosting"
        elif seconds_inactive >= q_lim:
            new_status = "quiet"
        else:
            new_status = "active"
            
        cursor.execute(
            "UPDATE teammates SET status = %s WHERE telegram_id = %s AND chat_id = %s",
            (new_status, telegram_id, chat_id)
        )
    conn.commit()
    cursor.close()
    conn.close()


def remove_group_from_folder(chat_id, folder_id):
    if folder_id is None:
        return
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM folder_maps WHERE chat_id = %s AND folder_id = %s",
        (chat_id, folder_id)
    )
    conn.commit()
    cursor.close()
    conn.close()

def check_cooldown(chat_id, username):
    """Returns (allowed: bool, seconds_remaining: int)."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT last_sent FROM action_cooldowns WHERE chat_id = %s AND username = %s",
        (chat_id, username)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if row is None:
        return True, 0

    last_sent = row[0]
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    elapsed = (now - last_sent).total_seconds()
    remaining = COOLDOWN_SECONDS - elapsed

    if remaining > 0:
        return False, int(remaining)
    return True, 0


def record_action(chat_id, username):
    conn = get_conn()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    cursor.execute("""
        INSERT INTO action_cooldowns (chat_id, username, last_sent)
        VALUES (%s, %s, %s)
        ON CONFLICT (chat_id, username) DO UPDATE SET last_sent = EXCLUDED.last_sent
    """, (chat_id, username, now))
    conn.commit()
    cursor.close()
    conn.close()

def is_authorized(chat_id, user_id):
    """True if this user owns the group OR has accepted collaborator access."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT owner_id FROM groups WHERE chat_id = %s", (chat_id,))
    row = cursor.fetchone()
    if row is not None and row[0] == user_id:
        cursor.close()
        conn.close()
        return True
    cursor.execute(
        "SELECT 1 FROM group_access WHERE chat_id = %s AND user_id = %s",
        (chat_id, user_id)
    )
    has_access = cursor.fetchone() is not None
    cursor.close()
    conn.close()
    return has_access


def get_groups_for_user(user_id):
    """Groups this user owns OR has accepted access to, tagged with their role."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT chat_id, title, 'owner' AS role FROM groups WHERE owner_id = %s
        UNION
        SELECT g.chat_id, g.title, 'collaborator' AS role
        FROM group_access a JOIN groups g ON a.chat_id = g.chat_id
        WHERE a.user_id = %s
    """, (user_id, user_id))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def create_invitation(chat_id, invited_username, invited_by):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO invitations (chat_id, invited_username, invited_by, status)
        VALUES (%s, %s, %s, 'pending')
    """, (chat_id, invited_username.lstrip("@").lower(), invited_by))
    conn.commit()
    cursor.close()
    conn.close()


def get_pending_invitations_for_username(username):
    """Called when a user opens the Mini App -- checks if anyone invited their @username."""
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.id, i.chat_id, g.title, i.invited_by
        FROM invitations i
        JOIN groups g ON i.chat_id = g.chat_id
        WHERE i.invited_username = %s AND i.status = 'pending'
    """, (username.lower(),))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def respond_invitation(invitation_id, user_id, accept):
    conn = get_conn()
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, status FROM invitations WHERE id = %s", (invitation_id,))
    row = cursor.fetchone()
    if row is None or row[1] != 'pending':
        cursor.close()
        conn.close()
        return False

    chat_id = row[0]
    new_status = 'accepted' if accept else 'declined'
    cursor.execute("UPDATE invitations SET status = %s WHERE id = %s", (new_status, invitation_id))

    if accept:
        cursor.execute("""
            INSERT INTO group_access (chat_id, user_id, role)
            VALUES (%s, %s, 'collaborator')
            ON CONFLICT (chat_id, user_id) DO NOTHING
        """, (chat_id, user_id))

    conn.commit()
    cursor.close()
    conn.close()
    return True