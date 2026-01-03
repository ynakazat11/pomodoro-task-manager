# Pomodoro Task Manager

A task manager with Pomodoro timer that uses Google Gemini for intelligent task parsing. Available as both a **CLI** and **macOS Menu Bar App**.

## Features

- **🧠 Brain Dump**: Takes a raw text dump of your tasks and uses Gemini to break them down and estimate effort
- **📋 Smart Organization**: Automatically creates projects and estimates "Tomatoes" (25-minute slots)
- **⏱️ Pomodoro Timer**: Visual timer for 25-minute focus sessions
- **📊 Progress Tracking**: View statistics on completed vs. estimated tomatoes
- **🗄️ Archive**: Archive completed tasks to keep your list clean
- **🍎 Menu Bar App**: Quick access to tasks from your macOS menu bar (no Terminal needed!)
- **🐙 GitHub Integration**: Sync tasks to `tasks.md` and ingest issues as tasks

---

## 🚀 Quick Start

### Option 1: Menu Bar App (macOS) - **Recommended**

1. **Install Dependencies**:
   ```bash
   pip3 install -r requirements.txt
   ```

2. **Set up Gemini API** (required for Brain Dump):
   Create a `.env` file:
   ```
   GEMINI_API_KEY=your_api_key_here
   ```

3. **Run the Menu Bar App**:
   
   **Easiest way** - Double-click the launcher:
   - In Finder, navigate to the project folder
   - Double-click `start_menubar.command`
   - The 🍅 tomato icon will appear in your menu bar!
   
   **Or from terminal**:
   ```bash
   ./start_menubar.sh
   ```
   
   **Or manually**:
   ```bash
   python menubar_app.py &
   ```
   
   💡 **Pro tip:** Drag `start_menubar.command` to your Dock for one-click access!

### Option 2: CLI / Interactive Terminal

Run the interactive CLI:
```bash
python3 main.py
```

---

## 🍎 Menu Bar App (macOS)

### Features

| Feature | Description |
|---------|-------------|
| **View Tasks** | Click 🍅 to see all tasks sorted by priority (shows 20, "Show More" for additional) |
| **Start Timer** | Click any task to start a 25-minute Pomodoro with macOS notifications |
| **🧠 Brain Dump** | Type tasks naturally → Gemini parses → Review & confirm before saving |
| **✅ Mark Done** | Quick-complete tasks from submenu |
| **✏️ Edit Tasks** | Edit title, priority, deadline via dialogs |
| **⌨️ GitHub Inbox** | Fetch open issues and convert to tasks |
| **☁️ Sync to GitHub** | Push current tasks to `tasks.md` in your private repo |

### Running on Startup (Optional)

To have the menu bar app launch automatically:

1. Open **System Settings** → **General** → **Login Items**
2. Click **+** and add `menubar_app.py` 
3. Or create a simple shell script wrapper

---

## Setup

1.  **Install Dependencies**:
    ```bash
    pip3 install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file in the project root:
    ```
    GEMINI_API_KEY=your_api_key_here
    GITHUB_TOKEN=your_github_token_here  # Optional, for GitHub features
    GITHUB_REPO=username/repo-name        # Optional, must be PRIVATE
    ```

## CLI Usage

### Interactive Mode (Recommended)
Simply run the program to enter the interactive menu:
```bash
python3 main.py
```
Or with make:
```bash
make run
```

### CLI Commands
You can still use the CLI commands if you prefer:

### 1. Ingest Tasks
Dump your thoughts into the system. Gemini will parse them.
```bash
python3 main.py ingest "I need to finish the quarterly report, call mom, and buy groceries for dinner."
```

### 2. List Tasks
See what's on your plate.
```bash
python3 main.py list
```

### 3. Start a Task
Pick a task by its ID (or the first few characters of the ID).
```bash
python3 main.py start <task_id_prefix>
```
Example: `python3 main.py start t1`

The timer will run for 25 minutes. When finished, it will ask if you completed the task.

### 4. Check Progress
See how many tomatoes you've crushed.
```bash
python3 main.py stats
```

### 5. Archive
Move completed tasks to the archive.
```bash
python3 main.py archive
```
To archive tasks completed more than 90 days ago:
```bash
python3 main.py archive --days 90
```

---

## Tips

- **Menu Bar**: Right-click the 🍅 icon and select "Quit" to close the app
- **Refresh**: Click 🔄 Refresh if tasks don't appear after Brain Dump
- **GitHub**: Tasks sync only works with **private** repositories (for privacy)
- **Task Limits**: Main list shows 20 tasks; use "📂 Show More..." for additional tasks
