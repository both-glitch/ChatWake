import customtkinter as ctk
import threading
from datetime import datetime, timezone
from database import (
    get_all_groups, get_teammates_by_group, create_tables,
    add_custom_folder, get_all_folders, assign_group_to_folder, get_groups_by_folder
)
from database import remove_group_from_folder
from bot import send_wake_up, send_anonymous_nudge, start_bot

# ---------- DESIGN TOKENS (PREMIUM SMOOTH BLUE THEME) ----------
COLOR_BG = "#090d1a"          
COLOR_CARD = "#121829"        
COLOR_CARD_HOVER = "#1b233d"  
COLOR_TEXT = "#f8fafc"        
COLOR_SUBTEXT = "#94a3b8"     
COLOR_ACCENT = "#38bdf8"      
COLOR_ACCENT_DIM = "#0c4a6e"  

COLOR_ACTIVE = "#4ade80"      
COLOR_QUIET = "#fbbf24"       
COLOR_GHOSTING = "#f87171"    

FONT_TITLE = ("Segoe UI", 24, "bold")
FONT_HEADER = ("Segoe UI", 18, "bold")
FONT_BODY = ("Segoe UI", 14, "normal")
FONT_BODY_BOLD = ("Segoe UI", 14, "bold")
FONT_SMALL = ("Segoe UI", 12, "normal")
FONT_METRIC = ("Segoe UI", 13, "bold")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

app = ctk.CTk()
app.title("ChatWake Control Center")
app.geometry("1100x750")
app.configure(fg_color=COLOR_BG)

create_tables()

current_frame = None
selected_folder_id = None  
folders_visible = True 

def format_explicit_time(last_seen_str):
    try:
        utc_dt = datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
        local_dt = utc_dt.replace(tzinfo=timezone.utc).astimezone(tz=None)
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return last_seen_str

def launch_backend_automatically():
    status_indicator.configure(text="• System Live", text_color=COLOR_ACTIVE)
    status_label.configure(text="Asynchronous tracking engine fully monitoring network arrays", text_color=COLOR_SUBTEXT)
    thread = threading.Thread(target=start_bot, daemon=True)
    thread.start()

def delete_folder_action(folder_id):
    import sqlite3
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM folder_maps WHERE folder_id = ?", (folder_id,))
    cursor.execute("DELETE FROM folders WHERE id = ?", (folder_id,))
    conn.commit()
    conn.close()
    
    global selected_folder_id
    if selected_folder_id == folder_id:
        selected_folder_id = None
        
    render_sidebar_folders()
    show_dashboard()

def remove_group_action(chat_id, folder_id):
    remove_group_from_folder(chat_id, folder_id)
    show_dashboard()

def toggle_folders_view():
    global folders_visible
    folders_visible = not folders_visible
    render_sidebar_folders()

# ---------- GLOBAL TOP BAR NAVIGATION ----------
top_bar = ctk.CTkFrame(app, fg_color="transparent")
top_bar.pack(pady=(24, 4), padx=28, fill="x")

brand_frame = ctk.CTkFrame(top_bar, fg_color="transparent")
brand_frame.pack(side="left")

brand_label = ctk.CTkLabel(brand_frame, text="ChatWake", font=FONT_TITLE, text_color=COLOR_TEXT)
brand_label.pack(side="left")

status_indicator = ctk.CTkLabel(brand_frame, text="• Initializing", font=("Segoe UI", 14, "bold"), text_color=COLOR_QUIET)
status_indicator.pack(side="left", padx=(14, 0), pady=(4, 0))

status_bar = ctk.CTkFrame(app, fg_color="transparent")
status_bar.pack(padx=28, fill="x")
status_label = ctk.CTkLabel(status_bar, text="Booting background middleware arrays...", font=FONT_SMALL, text_color=COLOR_SUBTEXT)
status_label.pack(side="left")

# ---------- PRIMARY LAYOUT COUPLERS ----------
main_container = ctk.CTkFrame(app, fg_color="transparent")
main_container.pack(fill="both", expand=True, padx=28, pady=14)

# We start with width=260 by default
sidebar_frame = ctk.CTkFrame(main_container, fg_color=COLOR_CARD, width=260, corner_radius=14, border_width=1, border_color="#1e293b")
sidebar_frame.pack(side="left", fill="y", padx=(0, 20))
sidebar_frame.pack_propagate(False)

content_area = ctk.CTkFrame(main_container, fg_color="transparent")
content_area.pack(side="right", fill="both", expand=True)

def open_create_folder_window():
    modal = ctk.CTkToplevel(app)
    modal.title("New Workspace Folder")
    modal.geometry("380x300")
    modal.configure(fg_color=COLOR_BG)
    modal.transient(app)
    modal.grab_set()

    lbl = ctk.CTkLabel(modal, text="New Custom Folder", font=FONT_HEADER, text_color=COLOR_TEXT)
    lbl.pack(pady=(20, 12))

    name_entry = ctk.CTkEntry(modal, placeholder_text="Course Name (e.g., CS A)", font=FONT_BODY, width=300, height=40, fg_color=COLOR_CARD, border_color="#1e293b")
    name_entry.pack(pady=10)

    color_opt = ctk.CTkComboBox(modal, values=["Blue", "Green", "Gold", "Purple", "Red"], font=FONT_BODY, width=300, height=40, fg_color=COLOR_CARD, border_color="#1e293b")
    color_opt.pack(pady=10)
    color_opt.set("Blue")

    COLOR_MAP = {
        "Blue": "#38bdf8", "Green": "#4ade80", "Gold": "#fbbf24", "Purple": "#c084fc", "Red": "#f87171"
    }

    def save_folder():
        name = name_entry.get().strip()
        color_hex = COLOR_MAP.get(color_opt.get(), "#38bdf8")
        if name:
            add_custom_folder(name, color_hex)
            render_sidebar_folders()
            show_dashboard()
            modal.destroy()

    save_btn = ctk.CTkButton(modal, text="Create Workspace", fg_color=COLOR_ACCENT, hover_color="#0284c7", text_color="#0f172a", font=FONT_BODY_BOLD, height=42, width=300, corner_radius=8, command=save_folder)
    save_btn.pack(pady=20)

def render_sidebar_folders():
    for widget in sidebar_frame.winfo_children():
        widget.destroy()

    def select_folder(fid):
        global selected_folder_id
        selected_folder_id = fid
        show_dashboard()

    if folders_visible:
        # --- EXPANDED SIDEBAR VIEW (Width = 260) ---
        sidebar_frame.configure(width=260)
        
        header_box = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
        header_box.pack(fill="x", pady=(20, 14), padx=16)

        lbl = ctk.CTkLabel(header_box, text="Workspaces", font=FONT_HEADER, text_color=COLOR_TEXT)
        lbl.pack(side="left")

        toggle_btn = ctk.CTkButton(
            header_box, text="◀ Hide", width=60, height=26, font=FONT_SMALL,
            fg_color=COLOR_ACCENT_DIM, text_color=COLOR_TEXT, hover_color=COLOR_CARD_HOVER,
            command=toggle_folders_view
        )
        toggle_btn.pack(side="right")

        unassigned_row = ctk.CTkFrame(sidebar_frame, fg_color="transparent")
        unassigned_row.pack(fill="x", padx=10, pady=2)
        
        all_btn = ctk.CTkButton(
            unassigned_row, text="📋  All Channels", font=FONT_BODY, anchor="w", height=38,
            fg_color=COLOR_CARD_HOVER if selected_folder_id is None else "transparent",
            text_color=COLOR_TEXT, hover_color=COLOR_CARD_HOVER, command=lambda: select_folder(None)
        )
        all_btn.pack(fill="x", side="left", expand=True)

        custom_folders_container = ctk.CTkScrollableFrame(sidebar_frame, fg_color="transparent", label_text="")
        custom_folders_container.pack(fill="both", expand=True, padx=4)

        for fid, name, color in get_all_folders():
            is_sel = (selected_folder_id == fid)
            row_container = ctk.CTkFrame(custom_folders_container, fg_color="transparent")
            row_container.pack(fill="x", pady=2)
            
            f_btn = ctk.CTkButton(
                row_container, text=f"📁  {name}", font=FONT_BODY, anchor="w", height=36,
                fg_color=COLOR_CARD_HOVER if is_sel else "transparent",
                text_color=color, hover_color=COLOR_CARD_HOVER, command=lambda f=fid: select_folder(f)
            )
            f_btn.pack(side="left", fill="x", expand=True)
            
            del_btn = ctk.CTkButton(
                row_container, text="✕", width=28, height=28, corner_radius=6,
                fg_color="transparent", hover_color="#271c1c", text_color="#ef4444",
                font=("Segoe UI", 12, "bold"), command=lambda f=fid: delete_folder_action(f)
            )
            del_btn.pack(side="right", padx=(4, 2))

        add_btn = ctk.CTkButton(
            sidebar_frame, text="+ Create Workspace", font=FONT_BODY_BOLD, height=40,
            fg_color=COLOR_ACCENT_DIM, text_color=COLOR_ACCENT, hover_color=COLOR_CARD_HOVER,
            command=open_create_folder_window
        )
        add_btn.pack(side="bottom", fill="x", pady=18, padx=12)

    else:
        # --- MODERN MINIMAL COLLAPSED VIEW (Width = 60) ---
        sidebar_frame.configure(width=60)
        
        # Toggle Arrow Icon
        toggle_btn = ctk.CTkButton(
            sidebar_frame, text="▶", width=36, height=36, font=("Segoe UI", 14, "bold"),
            fg_color=COLOR_ACCENT_DIM, text_color=COLOR_ACCENT, hover_color=COLOR_CARD_HOVER,
            command=toggle_folders_view
        )
        toggle_btn.pack(pady=(20, 16), padx=10)

        # Global Channels Icon Button
        all_btn = ctk.CTkButton(
            sidebar_frame, text="📋", font=("Segoe UI", 18), width=40, height=40, corner_radius=8,
            fg_color=COLOR_CARD_HOVER if selected_folder_id is None else "transparent",
            hover_color=COLOR_CARD_HOVER, command=lambda: select_folder(None)
        )
        all_btn.pack(pady=4, padx=10)

        # Dynamic Folders Icon Strip
        for fid, name, color in get_all_folders():
            is_sel = (selected_folder_id == fid)
            first_letter = name[0].upper() if name else "F"
            
            f_btn = ctk.CTkButton(
                sidebar_frame, text=first_letter, font=("Segoe UI", 14, "bold"), width=40, height=40, corner_radius=8,
                fg_color=COLOR_CARD_HOVER if is_sel else "transparent",
                text_color=color, hover_color=COLOR_CARD_HOVER, command=lambda f=fid: select_folder(f)
            )
            f_btn.pack(pady=4, padx=10)

        # Mini "+" Creator Button
        add_btn = ctk.CTkButton(
            sidebar_frame, text="+", font=("Segoe UI", 18, "bold"), width=40, height=40, corner_radius=8,
            fg_color="transparent", text_color=COLOR_ACCENT, hover_color=COLOR_CARD_HOVER,
            command=open_create_folder_window
        )
        add_btn.pack(side="bottom", pady=20, padx=10)

def show_right_click_menu(event, chat_id):
    menu = ctk.CTkToplevel(app)
    menu.title("Map to Folder")
    menu.geometry(f"220x250+{event.x_root}+{event.y_root}")
    menu.configure(fg_color=COLOR_CARD)
    menu.resizable(False, False)
    menu.transient(app)
    menu.grab_set()

    title_lbl = ctk.CTkLabel(menu, text="Assign Channel To:", font=FONT_SMALL, text_color=COLOR_SUBTEXT)
    title_lbl.pack(pady=(12, 6))

    def copy_to_target(fid):
        assign_group_to_folder(chat_id, fid)
        menu.destroy()
        show_dashboard()

    folders = get_all_folders()
    if not folders:
        no_f = ctk.CTkLabel(menu, text="No folders created.\nAdd a workspace first!", font=FONT_SMALL, text_color=COLOR_GHOSTING)
        no_f.pack(pady=24)
    else:
        scroll = ctk.CTkScrollableFrame(menu, fg_color="transparent", height=170)
        scroll.pack(fill="both", expand=True, padx=6, pady=4)
        for fid, name, color in folders:
            f_btn = ctk.CTkButton(
                scroll, text=name, font=FONT_SMALL, fg_color=COLOR_BG, hover_color=COLOR_CARD_HOVER,
                text_color=color, height=32, command=lambda f=fid: copy_to_target(f)
            )
            f_btn.pack(fill="x", pady=2, padx=2)

# ---------- MAIN DASHBOARD STREAM ----------
def show_dashboard():
    global current_frame
    stop_auto_refresh()
    
    if current_frame is not None:
        current_frame.destroy()

    frame = ctk.CTkFrame(content_area, fg_color="transparent")
    frame.pack(fill="both", expand=True)
    current_frame = frame

    title_text = "All Synchronized Channels"
    if selected_folder_id is not None:
        for fid, name, _ in get_all_folders():
            if fid == selected_folder_id:
                title_text = f"Workspace: {name}"

    title = ctk.CTkLabel(frame, text=title_text, font=FONT_HEADER, text_color=COLOR_TEXT)
    title.pack(pady=(4, 14), anchor="w")

    groups = get_groups_by_folder(selected_folder_id)

    if not groups:
        empty = ctk.CTkLabel(
            frame, text="No tracked channels linked here.\n\nRight-click a channel under 'All Channels' to copy it inside workspaces.",
            justify="center", font=FONT_BODY, text_color=COLOR_SUBTEXT,
        )
        empty.pack(pady=100)
        return

    scroll_area = ctk.CTkScrollableFrame(frame, fg_color="transparent")
    scroll_area.pack(fill="both", expand=True)

    for chat_id, title_text in groups:
        row = ctk.CTkFrame(scroll_area, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color="#1e293b")
        row.pack(pady=5, padx=2, fill="x")

        actions_box = ctk.CTkFrame(row, fg_color="transparent")
        actions_box.pack(side="right", padx=16, pady=12)

        open_btn = ctk.CTkButton(
            actions_box, text="Inspect", width=90, height=34, corner_radius=8,
            fg_color="#1e293b", hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT, font=FONT_BODY_BOLD,
            command=lambda cid=chat_id, t=title_text: show_tracker(cid, t)
        )
        open_btn.pack(side="right", padx=(6, 0))

        if selected_folder_id is not None:
            remove_btn = ctk.CTkButton(
                actions_box, text="Remove", width=90, height=34, corner_radius=8,
                fg_color="transparent", hover_color="#2d1a1c", text_color=COLOR_GHOSTING, font=FONT_BODY_BOLD,
                border_width=1, border_color="#ef4444",
                command=lambda cid=chat_id: remove_group_action(cid, selected_folder_id)
            )
            remove_btn.pack(side="right", padx=(0, 6))

        label = ctk.CTkLabel(row, text=title_text or "Unnamed Group Chat", font=FONT_BODY_BOLD, text_color=COLOR_TEXT)
        label.pack(side="left", padx=20, pady=16)

        row.bind("<Button-3>", lambda e, cid=chat_id: show_right_click_menu(e, cid))
        label.bind("<Button-3>", lambda e, cid=chat_id: show_right_click_menu(e, cid))

# ---------- LIVE MONITORING METRICS SCREEN ----------
auto_refresh_job = None

def stop_auto_refresh():
    global auto_refresh_job
    if auto_refresh_job is not None:
        app.after_cancel(auto_refresh_job)
        auto_refresh_job = None

def wake_up_all_ghosts(chat_id):
    teammates = get_teammates_by_group(chat_id)
    ghosts = [t for t in teammates if t[6] == "ghosting"]
    for t in ghosts:
        send_wake_up(chat_id, t[4])
    if ghosts:
        status_label.configure(text="Alert signals dispatched to non-responsive profiles", text_color=COLOR_GHOSTING)
    else:
        status_label.configure(text="Zero missing telemetry markers discovered", text_color=COLOR_SUBTEXT)

def nudge_all_quiet_members(chat_id):
    teammates = get_teammates_by_group(chat_id)
    quiet_members = [t for t in teammates if t[6] == "quiet"]
    for t in quiet_members:
        send_anonymous_nudge(chat_id, t[4])
    if quiet_members:
        status_label.configure(text="Dispatched anonymous ping alerts to quiet list", text_color=COLOR_QUIET)
    else:
        status_label.configure(text="Zero quiet activity records detected", text_color=COLOR_SUBTEXT)

def show_tracker(chat_id, group_title):
    global current_frame, auto_refresh_job
    stop_auto_refresh()
    
    if current_frame is not None:
        current_frame.destroy()

    frame = ctk.CTkFrame(content_area, fg_color="transparent")
    frame.pack(fill="both", expand=True)
    current_frame = frame

    header = ctk.CTkFrame(frame, fg_color="transparent")
    header.pack(fill="x", pady=(4, 14))

    back_btn = ctk.CTkButton(
        header, text="← Back", width=70, height=36, corner_radius=8,
        fg_color=COLOR_CARD, hover_color=COLOR_CARD_HOVER, text_color=COLOR_TEXT,
        font=FONT_BODY_BOLD, border_width=1, border_color="#1e293b", command=show_dashboard
    )
    back_btn.pack(side="left")

    title = ctk.CTkLabel(header, text=group_title or "Telemetry Interface", font=FONT_HEADER, text_color=COLOR_TEXT)
    title.pack(side="left", padx=16)

    summary_box = ctk.CTkFrame(frame, fg_color=COLOR_CARD, corner_radius=14, border_width=1, border_color="#1e293b")
    summary_box.pack(pady=(0, 16), fill="x")
    summary_box.columnconfigure((0, 1, 2), weight=1)

    frame.active_count_lbl = ctk.CTkLabel(summary_box, text="Active: 0", font=FONT_METRIC, text_color=COLOR_ACTIVE)
    frame.active_count_lbl.grid(row=0, column=0, pady=14)

    frame.quiet_count_lbl = ctk.CTkLabel(summary_box, text="Quiet: 0", font=FONT_METRIC, text_color=COLOR_QUIET)
    frame.quiet_count_lbl.grid(row=0, column=1, pady=14)

    frame.ghost_count_lbl = ctk.CTkLabel(summary_box, text="Ghosting: 0", font=FONT_METRIC, text_color=COLOR_GHOSTING)
    frame.ghost_count_lbl.grid(row=0, column=2, pady=14)

    bulk_frame = ctk.CTkFrame(frame, fg_color="transparent")
    bulk_frame.pack(pady=(0, 16), fill="x")
    bulk_frame.columnconfigure(0, weight=1)
    bulk_frame.columnconfigure(1, weight=1)

    wake_all_btn = ctk.CTkButton(
        bulk_frame, text="🚨 Wake All Ghosts", fg_color="transparent", hover_color="#3a1a1c",
        text_color=COLOR_GHOSTING, corner_radius=8, height=40, font=FONT_BODY_BOLD,
        border_width=1, border_color="#f87171",
        command=lambda: wake_up_all_ghosts(chat_id)
    )
    wake_all_btn.grid(row=0, column=0, padx=(0, 6), sticky="ew")

    nudge_all_btn = ctk.CTkButton(
        bulk_frame, text="🔔 Nudge All Quiet", fg_color="transparent", hover_color="#3a2e1a",
        text_color=COLOR_QUIET, corner_radius=8, height=40, font=FONT_BODY_BOLD,
        border_width=1, border_color="#fbbf24",
        command=lambda: nudge_all_quiet_members(chat_id)
    )
    nudge_all_btn.grid(row=0, column=1, padx=(6, 0), sticky="ew")

    list_frame = ctk.CTkScrollableFrame(frame, fg_color="transparent")
    list_frame.pack(fill="both", expand=True)

    frame.list_frame = list_frame
    frame.member_rows = {} 
    frame.empty_label = None

    build_or_update_tracker(chat_id, group_title, frame)
    auto_refresh_job = app.after(3000, lambda: refresh_tracker(chat_id, group_title))

STATUS_STYLE = {
    "active":   {"color": COLOR_ACTIVE,   "label": "ACTIVE"},
    "quiet":    {"color": COLOR_QUIET,    "label": "QUIET"},
    "ghosting": {"color": COLOR_GHOSTING, "label": "GHOSTING"},
}

def build_action_button(parent, status, chat_id, username):
    if status == "ghosting":
        return ctk.CTkButton(
            parent, text="WAKE UP", width=110, height=32, corner_radius=6,
            fg_color=COLOR_GHOSTING, hover_color="#dc2626", text_color="#0f172a", font=FONT_BODY_BOLD,
            command=lambda: send_wake_up(chat_id, username)
        )
    elif status == "quiet":
        return ctk.CTkButton(
            parent, text="Nudge", width=110, height=32, corner_radius=6,
            fg_color=COLOR_QUIET, hover_color="#d97706", text_color="#0f172a", font=FONT_BODY_BOLD,
            command=lambda: send_anonymous_nudge(chat_id, username)
        )
    return None

def build_or_update_tracker(chat_id, group_title, frame):
    teammates = get_teammates_by_group(chat_id)

    if not teammates:
        if frame.empty_label is None:
            frame.empty_label = ctk.CTkLabel(
                frame.list_frame, text="No profile feeds loaded.",
                justify="center", font=FONT_BODY, text_color=COLOR_SUBTEXT
            )
            frame.empty_label.pack(pady=60)
        frame.active_count_lbl.configure(text="Active: 0")
        frame.quiet_count_lbl.configure(text="Quiet: 0")
        frame.ghost_count_lbl.configure(text="Ghosting: 0")
        return
    else:
        if frame.empty_label is not None:
            frame.empty_label.destroy()
            frame.empty_label = None

    active_count = sum(1 for t in teammates if t[6] == "active")
    quiet_count = sum(1 for t in teammates if t[6] == "quiet")
    ghost_count = sum(1 for t in teammates if t[6] == "ghosting")

    frame.active_count_lbl.configure(text=f"🟢 Active: {active_count}")
    frame.quiet_count_lbl.configure(text=f"🟡 Quiet: {quiet_count}")
    frame.ghost_count_lbl.configure(text=f"🔴 Ghosting: {ghost_count}")

    current_ids = set()

    for row_data in teammates:
        t_id, telegram_id, _, name, username, last_seen, status = row_data
        current_ids.add(telegram_id)

        style = STATUS_STYLE.get(status, STATUS_STYLE["active"])
        pretty_last_reply = format_explicit_time(last_seen)

        if telegram_id not in frame.member_rows:
            row = ctk.CTkFrame(frame.list_frame, fg_color=COLOR_CARD, corner_radius=12, border_width=1, border_color="#1e293b")
            row.pack(pady=4, padx=2, fill="x")

            profile_lbl = ctk.CTkLabel(row, text="●", font=("Segoe UI", 18), text_color=style["color"])
            profile_lbl.pack(side="left", padx=(18, 2), pady=12)

            info_frame = ctk.CTkFrame(row, fg_color="transparent")
            info_frame.pack(side="left", padx=12, pady=12, fill="both", expand=True)

            name_lbl = ctk.CTkLabel(info_frame, text=name, font=FONT_BODY_BOLD, text_color=COLOR_TEXT, anchor="w")
            name_lbl.pack(fill="x")

            meta_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            meta_frame.pack(fill="x", pady=(2, 0))

            status_lbl = ctk.CTkLabel(
                meta_frame, text=f"{style['label']}   •   Last seen {pretty_last_reply}", 
                font=FONT_SMALL, text_color=style["color"]
            )
            status_lbl.pack(side="left")

            btn_container = ctk.CTkFrame(row, fg_color="transparent")
            btn_container.pack(side="right", padx=18, pady=12)

            act_btn = build_action_button(btn_container, status, chat_id, username)
            if act_btn:
                act_btn.pack()

            frame.member_rows[telegram_id] = {
                "row_frame": row, "profile_lbl": profile_lbl, "name_lbl": name_lbl,
                "status_lbl": status_lbl, "btn_container": btn_container, "act_btn": act_btn,
                "status": status, "last_seen": last_seen
            }
        else:
            cache = frame.member_rows[telegram_id]
            if cache["status"] != status or cache["last_seen"] != last_seen:
                cache["status_lbl"].configure(
                    text=f"{style['label']}   •   Last seen {pretty_last_reply}", text_color=style["color"]
                )
                cache["profile_lbl"].configure(text_color=style["color"])
                if cache["status"] != status:
                    if cache["act_btn"]: cache["act_btn"].destroy()
                    cache["act_btn"] = build_action_button(cache["btn_container"], status, chat_id, username)
                    if cache["act_btn"]: cache["act_btn"].pack()
                cache["status"] = status
                cache["last_seen"] = last_seen

    for cached_id in list(frame.member_rows.keys()):
        if cached_id not in current_ids:
            frame.member_rows[cached_id]["row_frame"].destroy()
            del frame.member_rows[cached_id]

def refresh_tracker(chat_id, group_title, force_rebuild=False):
    global auto_refresh_job, current_frame
    if current_frame is None or not hasattr(current_frame, "member_rows"): return
    if force_rebuild:
        show_tracker(chat_id, group_title)
        return
    build_or_update_tracker(chat_id, group_title, current_frame)
    auto_refresh_job = app.after(3000, lambda: refresh_tracker(chat_id, group_title))

render_sidebar_folders()
show_dashboard()

app.after(100, launch_backend_automatically)

app.mainloop()