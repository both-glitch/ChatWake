# ChatWake ⏰

An asynchronous, multi-threaded group monitoring system that tracks teammate activity via Telegram and visualizes engagement states through a real-time desktop GUI dashboard.

## 🚀 Key Features
* **Real-time Telemetry:** Automatically captures and logs user interaction timestamps from connected Telegram groups.
* **Deterministic Inactivity Calculation:** Computes precise time-deltas to categorize users into Active, Quiet, or Ghosting states.
* **Direct Alert Dispatch:** Features single-user and bulk-action "WAKE UP" or anonymous nudges routed directly back to specific users via the Telegram API.
* **Dynamic Workspace Organization:** Custom folder layout mappings to filter and manage multiple group tracks seamlessly.

## 🛠️ System Architecture
The application relies on a decoupled, bidirectional data lifecycle running across concurrent threads:
1. **Main Thread:** Drives the responsive `CustomTkinter` GUI layer (`test_ui.py`).
2. **Worker Thread 1:** Dedicated to continuous network payload ingestion via the Telegram Polling API (`bot.py`).
3. **Worker Thread 2 (Daemon):** Executes a persistent background loop managing database state calculations (`database.py`).

## 📦 Installation & Setup

1. **Clone the repository:**
   ```bash
   git clone [https://github.com/YOUR_GITHUB_USERNAME/ChatWake.git](https://github.com/YOUR_GITHUB_USERNAME/ChatWake.git)(https://github.com/YOUR_GITHUB_USERNAME/ChatWake.git](https://github.com/YOUR_GITHUB_USERNAME/ChatWake.git)
   cd ChatWake
