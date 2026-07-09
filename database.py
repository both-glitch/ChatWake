import sqlite3
import os
from datetime import datetime, timezone

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "chatwake.db")

QUIET_THRESHOLD_SECONDS = 30     
GHOST_THRESHOLD_SECONDS = 60     

def create_tables():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS groups (
        chat_id INTEGER PRIMARY KEY,
        title TEXT,
        owner_id INTEGER,
        folder_id INTEGER DEFAULT NULL
    )
""")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS teammates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id INTEGER,
            chat_id INTEGER,
            name TEXT,
            username TEXT,
            last_seen TEXT,
            status TEXT DEFAULT 'active',
            UNIQUE(telegram_id, chat_id)
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            color TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS folder_maps (
            chat_id INTEGER,
            folder_id INTEGER,
            PRIMARY KEY (chat_id, folder_id)
        )
    """)
    conn.commit()
    conn.close()

def save_group(chat_id, title, owner_id=None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO groups (chat_id, title, owner_id) VALUES (?, ?, ?)", (chat_id, title, owner_id))
    cursor.execute("UPDATE groups SET title = ? WHERE chat_id = ?", (title, chat_id))
    if owner_id is not None:
        cursor.execute("UPDATE groups SET owner_id = ? WHERE chat_id = ? AND owner_id IS NULL", (owner_id, chat_id))
    conn.commit()
    conn.close()

def delete_group(chat_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM groups WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM teammates WHERE chat_id = ?", (chat_id,))
    cursor.execute("DELETE FROM folder_maps WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()

def get_all_groups():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups")
    rows = cursor.fetchall()
    conn.close()
    return rows

def add_custom_folder(name, color):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO folders (name, color) VALUES (?, ?)", (name, color))
    conn.commit()
    folder_id = cursor.lastrowid
    conn.close()
    return folder_id

def get_all_folders():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, color FROM folders")
    rows = cursor.fetchall()
    conn.close()
    return rows

def assign_group_to_folder(chat_id, folder_id):
    if folder_id is None:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO folder_maps (chat_id, folder_id) VALUES (?, ?)", (chat_id, folder_id))
    conn.commit()
    conn.close()

def get_groups_by_folder(folder_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    if folder_id is None:
        cursor.execute("SELECT chat_id, title FROM groups")
    else:
        cursor.execute("""
            SELECT g.chat_id, g.title 
            FROM folder_maps f 
            JOIN groups g ON f.chat_id = g.chat_id 
            WHERE f.folder_id = ?
        """, (folder_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def save_teammate(telegram_id, chat_id, name, username, last_seen):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO teammates (telegram_id, chat_id, name, username, last_seen, status)
        VALUES (?, ?, ?, ?, ?, 'active')
        ON CONFLICT(telegram_id, chat_id) DO UPDATE SET
            name = excluded.name,
            username = excluded.username,
            last_seen = excluded.last_seen,
            status = 'active'
    """, (telegram_id, chat_id, name, username, last_seen))
    conn.commit()
    conn.close()

def get_teammates_by_group(chat_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, telegram_id, chat_id, name, username, last_seen, status 
        FROM teammates 
        WHERE chat_id = ?
        ORDER BY last_seen DESC
    """, (chat_id,))
    teammates = cursor.fetchall()
    conn.close()
    return teammates

def update_status(telegram_id, chat_id, status):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE teammates SET status = ? WHERE telegram_id = ? AND chat_id = ?
    """, (status, telegram_id, chat_id))
    conn.commit()
    conn.close()

def refresh_all_statuses():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT telegram_id, chat_id, last_seen FROM teammates")
    rows = cursor.fetchall()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for telegram_id, chat_id, last_seen_str in rows:
        last_seen_time = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
        seconds_inactive = (now - last_seen_time).total_seconds()
        if seconds_inactive >= GHOST_THRESHOLD_SECONDS:
            new_status = "ghosting"
        elif seconds_inactive >= QUIET_THRESHOLD_SECONDS:
            new_status = "quiet"
        else:
            new_status = "active"
        cursor.execute("""
            UPDATE teammates SET status = ? WHERE telegram_id = ? AND chat_id = ?
        """, (new_status, telegram_id, chat_id))
    conn.commit()
    conn.close()

def remove_group_from_folder(chat_id, folder_id):
    """Removes a copied channel mapping from a specific folder."""
    if folder_id is None:
        return
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM folder_maps WHERE chat_id = ? AND folder_id = ?", (chat_id, folder_id))
    conn.commit()
    conn.close()
    
def get_groups_by_owner(owner_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT chat_id, title FROM groups WHERE owner_id = ?", (owner_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows


def is_group_owner(chat_id, user_id):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT owner_id FROM groups WHERE chat_id = ?", (chat_id,))
    row = cursor.fetchone()
    conn.close()
    return row is not None and row[0] == user_id