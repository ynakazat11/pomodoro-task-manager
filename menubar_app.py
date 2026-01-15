#!/usr/bin/env python3
"""
Pomodoro Task Manager - macOS Menu Bar App

A lightweight menu bar application for managing tasks and Pomodoro timers.
Reuses existing storage, models, and client modules from the CLI.
"""

import sys
if sys.version_info < (3, 10):
    import importlib.metadata
    import importlib_metadata
    if not hasattr(importlib.metadata, 'packages_distributions'):
        importlib.metadata.packages_distributions = importlib_metadata.packages_distributions

import warnings
# Suppress warnings about Python 3.9 EOL and OpenSSL
warnings.filterwarnings("ignore", message="You are using a Python version")
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

import os
import threading
import time
from datetime import datetime, timedelta

import rumps

# Ensure we can import our modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import storage
from models import Task, Project, TaskStatus

# Try to import optional modules (may not be configured)
try:
    import llm_client
    HAS_LLM = True
except Exception:
    HAS_LLM = False

try:
    import github_client
    from dotenv import load_dotenv
    load_dotenv()
    HAS_GITHUB = bool(os.getenv("GITHUB_REPO"))
except Exception:
    HAS_GITHUB = False


class PomodoroMenuBar(rumps.App):
    """Main menu bar application for Pomodoro Task Manager."""
    
    TIMER_DURATION = 25 * 60  # 25 minutes in seconds
    
    def __init__(self):
        super().__init__("🍅", quit_button=None)
        self.timer_running = False
        self.remaining_seconds = 0
        self.current_task = None
        self.timer_thread = None
        self._build_menu()
    
    def _build_menu(self):
        """Build the menu dynamically from task data."""
        self.menu.clear()
        
        # Load tasks
        try:
            tasks, projects = storage.load_data()
            project_map = {p.id: p.name for p in projects}
        except Exception as e:
            self.menu.add(rumps.MenuItem(f"⚠️ Error loading tasks: {e}"))
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem("🔄 Refresh", callback=self._refresh))
            self.menu.add(rumps.MenuItem("Quit", callback=self._quit))
            return
        
        # Filter pending tasks
        pending_tasks = [t for t in tasks if t.status in [TaskStatus.TODO, TaskStatus.IN_PROGRESS]]
        
        # Sort by priority then deadline
        priority_order = {"High": 1, "Medium": 2, "Low": 3, None: 4}
        pending_tasks.sort(key=lambda t: (
            priority_order.get(t.priority, 4),
            t.deadline or "9999-12-31"
        ))
        
        # --- Tasks Section ---
        self.menu.add(rumps.MenuItem("─── Tasks ───"))
        
        # Display limits (like Chrome bookmarks)
        INITIAL_LIMIT = 20
        TITLE_WIDTH = 50  # Wider for readability
        PROJECT_WIDTH = 20
        
        if not pending_tasks:
            self.menu.add(rumps.MenuItem("  No pending tasks", callback=None))
        else:
            # Show first 20 tasks
            for task in pending_tasks[:INITIAL_LIMIT]:
                p_name = project_map.get(task.project_id, "")
                priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(task.priority, "  ")
                label = f"{priority_icon} {task.title[:TITLE_WIDTH]}"
                if p_name:
                    label += f" ({p_name[:PROJECT_WIDTH]})"
                
                item = rumps.MenuItem(label, callback=self._make_start_callback(task))
                self.menu.add(item)
            
            # "Show More" submenu for remaining tasks
            if len(pending_tasks) > INITIAL_LIMIT:
                more_menu = rumps.MenuItem(f"📂 Show {len(pending_tasks) - INITIAL_LIMIT} More...")
                for task in pending_tasks[INITIAL_LIMIT:]:
                    p_name = project_map.get(task.project_id, "")
                    priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(task.priority, "  ")
                    label = f"{priority_icon} {task.title[:TITLE_WIDTH]}"
                    if p_name:
                        label += f" ({p_name[:PROJECT_WIDTH]})"
                    item = rumps.MenuItem(label, callback=self._make_start_callback(task))
                    more_menu.add(item)
                self.menu.add(more_menu)
        
        self.menu.add(rumps.separator)
        
        # --- Actions ---
        if HAS_LLM:
            self.menu.add(rumps.MenuItem("🧠 Brain Dump", callback=self._brain_dump))
        
        self.menu.add(rumps.MenuItem("⏱️ Quick Timer (25 min)", callback=self._start_quick_timer))
        
        # Mark Done submenu
        done_menu = rumps.MenuItem("✅ Mark Done...")
        if pending_tasks:
            for task in pending_tasks[:INITIAL_LIMIT]:
                priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(task.priority, "  ")
                item = rumps.MenuItem(
                    f"{priority_icon} {task.title[:TITLE_WIDTH]}",
                    callback=self._make_done_callback(task)
                )
                done_menu.add(item)
            # Show More in submenu
            if len(pending_tasks) > INITIAL_LIMIT:
                done_more = rumps.MenuItem(f"📂 {len(pending_tasks) - INITIAL_LIMIT} More...")
                for task in pending_tasks[INITIAL_LIMIT:]:
                    priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(task.priority, "  ")
                    item = rumps.MenuItem(
                        f"{priority_icon} {task.title[:TITLE_WIDTH]}",
                        callback=self._make_done_callback(task)
                    )
                    done_more.add(item)
                done_menu.add(done_more)
        else:
            done_menu.add(rumps.MenuItem("No tasks"))
        self.menu.add(done_menu)
        
        # Remove Completed submenu
        completed_tasks = [t for t in tasks if t.status == TaskStatus.DONE]
        remove_menu = rumps.MenuItem("🗑️ Remove Completed...")
        if completed_tasks:
            for task in completed_tasks[:INITIAL_LIMIT]:
                item = rumps.MenuItem(
                    f"✅ {task.title[:TITLE_WIDTH]}",
                    callback=self._make_remove_callback(task)
                )
                remove_menu.add(item)
            # Show More in submenu
            if len(completed_tasks) > INITIAL_LIMIT:
                remove_more = rumps.MenuItem(f"📂 {len(completed_tasks) - INITIAL_LIMIT} More...")
                for task in completed_tasks[INITIAL_LIMIT:]:
                    item = rumps.MenuItem(
                        f"✅ {task.title[:TITLE_WIDTH]}",
                        callback=self._make_remove_callback(task)
                    )
                    remove_more.add(item)
                remove_menu.add(remove_more)
            # Add "Remove All" option
            remove_menu.add(rumps.separator)
            remove_menu.add(rumps.MenuItem(f"🗑️ Remove All ({len(completed_tasks)})", callback=self._remove_all_completed))
        else:
            remove_menu.add(rumps.MenuItem("No completed tasks"))
        self.menu.add(remove_menu)

        # Edit submenu
        edit_menu = rumps.MenuItem("✏️ Edit Task...")
        if pending_tasks:
            for task in pending_tasks[:INITIAL_LIMIT]:
                priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(task.priority, "  ")
                item = rumps.MenuItem(
                    f"{priority_icon} {task.title[:TITLE_WIDTH]}",
                    callback=self._make_edit_callback(task)
                )
                edit_menu.add(item)
            # Show More in submenu
            if len(pending_tasks) > INITIAL_LIMIT:
                edit_more = rumps.MenuItem(f"📂 {len(pending_tasks) - INITIAL_LIMIT} More...")
                for task in pending_tasks[INITIAL_LIMIT:]:
                    priority_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(task.priority, "  ")
                    item = rumps.MenuItem(
                        f"{priority_icon} {task.title[:TITLE_WIDTH]}",
                        callback=self._make_edit_callback(task)
                    )
                    edit_more.add(item)
                edit_menu.add(edit_more)
        else:
            edit_menu.add(rumps.MenuItem("No tasks"))
        self.menu.add(edit_menu)
        
        # --- GitHub Section ---
        if HAS_GITHUB:
            self.menu.add(rumps.separator)
            self.menu.add(rumps.MenuItem("─── GitHub ───"))
            self.menu.add(rumps.MenuItem("⌨️ Check Inbox", callback=self._check_github))
            self.menu.add(rumps.MenuItem("☁️ Sync to GitHub", callback=self._sync_github))
        
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("🔄 Refresh", callback=self._refresh))
        self.menu.add(rumps.MenuItem("📟 Open Terminal CLI", callback=self._open_terminal))
        self.menu.add(rumps.separator)
        self.menu.add(rumps.MenuItem("Quit", callback=self._quit))
    
    # --- Callback Factories ---
    
    def _make_start_callback(self, task):
        """Create a callback to start timer for a specific task."""
        def callback(sender):
            self._start_timer_for_task(task)
        return callback
    
    def _make_done_callback(self, task):
        """Create a callback to mark a specific task as done."""
        def callback(sender):
            self._mark_task_done(task)
        return callback
    
    def _make_edit_callback(self, task):
        """Create a callback to edit a specific task."""
        def callback(sender):
            self._edit_task(task)
        return callback

    def _make_remove_callback(self, task):
        """Create a callback to remove a specific completed task."""
        def callback(sender):
            self._remove_task(task)
        return callback
    
    # --- Timer Methods ---
    
    def _start_timer_for_task(self, task):
        """Start a Pomodoro timer for a specific task."""
        if self.timer_running:
            rumps.notification(
                "Timer Already Running",
                "",
                "Stop the current timer first.",
                sound=False
            )
            return
        
        self.current_task = task
        self.remaining_seconds = self.TIMER_DURATION
        self.timer_running = True
        
        # Update task status
        try:
            tasks, projects = storage.load_data()
            for t in tasks:
                if t.id == task.id:
                    t.status = TaskStatus.IN_PROGRESS
                    break
            storage.save_data(tasks, projects)
        except Exception:
            pass
        
        rumps.notification(
            "🍅 Pomodoro Started",
            task.title[:50],
            f"{self.TIMER_DURATION // 60} minutes - Focus time!",
            sound=True
        )
        
        self._run_timer_thread()
    
    def _start_quick_timer(self, sender):
        """Start a quick timer without a specific task."""
        if self.timer_running:
            rumps.notification(
                "Timer Already Running",
                "",
                "Stop the current timer first.",
                sound=False
            )
            return
        
        self.current_task = None
        self.remaining_seconds = self.TIMER_DURATION
        self.timer_running = True
        
        rumps.notification(
            "🍅 Quick Timer Started",
            "",
            f"{self.TIMER_DURATION // 60} minutes - Focus time!",
            sound=True
        )
        
        self._run_timer_thread()
    
    def _run_timer_thread(self):
        """Run the timer in a background thread."""
        def timer_loop():
            while self.timer_running and self.remaining_seconds > 0:
                mins, secs = divmod(self.remaining_seconds, 60)
                self.title = f"🍅 {mins:02d}:{secs:02d}"
                time.sleep(1)
                self.remaining_seconds -= 1
            
            if self.remaining_seconds <= 0:
                self._on_timer_complete()
        
        self.timer_thread = threading.Thread(target=timer_loop, daemon=True)
        self.timer_thread.start()
    
    def _on_timer_complete(self):
        """Handle timer completion."""
        self.timer_running = False
        self.title = "🍅"
        
        task_title = self.current_task.title[:50] if self.current_task else "Quick Timer"
        
        # Increment tomato count if we have a task
        if self.current_task:
            try:
                tasks, projects = storage.load_data()
                for t in tasks:
                    if t.id == self.current_task.id:
                        t.completed_tomatoes += 1
                        break
                storage.save_data(tasks, projects)
            except Exception:
                pass
        
        rumps.notification(
            "🍅 Time's Up!",
            task_title,
            "Great work! Take a short break.",
            sound=True
        )
        
        self.current_task = None
        self._build_menu()
    
    # --- Task Actions ---
    
    def _mark_task_done(self, task):
        """Mark a task as done."""
        try:
            tasks, projects = storage.load_data()
            for t in tasks:
                if t.id == task.id:
                    t.status = TaskStatus.DONE
                    t.completed_at = datetime.now().isoformat()
                    break
            storage.save_data(tasks, projects)
            
            rumps.notification(
                "✅ Task Completed",
                task.title[:50],
                "Nice work!",
                sound=True
            )
            self._build_menu()
        except Exception as e:
            rumps.notification("Error", "", str(e)[:100], sound=False)
    
    def _remove_task(self, task):
        """Remove a completed task from the list."""
        try:
            tasks, projects = storage.load_data()
            tasks = [t for t in tasks if t.id != task.id]
            storage.save_data(tasks, projects)

            rumps.notification(
                "🗑️ Task Removed",
                task.title[:50],
                "",
                sound=False
            )
            self._build_menu()
        except Exception as e:
            rumps.notification("Error", "", str(e)[:100], sound=False)

    def _remove_all_completed(self, sender):
        """Remove all completed tasks from the list."""
        try:
            tasks, projects = storage.load_data()
            completed_count = len([t for t in tasks if t.status == TaskStatus.DONE])

            if completed_count == 0:
                rumps.notification("No Tasks", "", "No completed tasks to remove", sound=False)
                return

            tasks = [t for t in tasks if t.status != TaskStatus.DONE]
            storage.save_data(tasks, projects)

            rumps.notification(
                "🗑️ Tasks Removed",
                f"{completed_count} completed task(s) removed",
                "",
                sound=True
            )
            self._build_menu()
        except Exception as e:
            rumps.notification("Error", "", str(e)[:100], sound=False)

    def _edit_task(self, task):
        """Edit a task via dialog."""
        # Title
        response = rumps.Window(
            message=f"Current: {task.title}",
            title="Edit Task Title",
            default_text=task.title,
            ok="Next",
            cancel="Cancel",
            dimensions=(400, 24)
        ).run()
        
        if not response.clicked:
            return
        
        new_title = response.text.strip() or task.title
        
        # Priority
        response = rumps.Window(
            message="Enter priority: High, Medium, Low (or leave blank)",
            title="Edit Priority",
            default_text=task.priority or "",
            ok="Next",
            cancel="Cancel",
            dimensions=(300, 24)
        ).run()
        
        if not response.clicked:
            return
        
        new_priority = response.text.strip().capitalize()
        if new_priority not in ["High", "Medium", "Low", ""]:
            new_priority = task.priority
        elif new_priority == "":
            new_priority = task.priority
        
        # Deadline
        response = rumps.Window(
            message="Enter deadline (YYYY-MM-DD) or leave blank",
            title="Edit Deadline",
            default_text=task.deadline or "",
            ok="Save",
            cancel="Cancel",
            dimensions=(300, 24)
        ).run()
        
        if not response.clicked:
            return
        
        new_deadline = response.text.strip() if response.text.strip() else None
        
        # Save changes
        try:
            tasks, projects = storage.load_data()
            for t in tasks:
                if t.id == task.id:
                    t.title = new_title
                    t.priority = new_priority
                    t.deadline = new_deadline
                    break
            storage.save_data(tasks, projects)
            
            rumps.notification("✅ Task Updated", new_title[:50], "", sound=False)
            self._build_menu()
        except Exception as e:
            rumps.notification("Error", "", str(e)[:100], sound=False)
    
    def _brain_dump(self, sender):
        """LLM-powered task ingestion with confirmation."""
        if not HAS_LLM:
            rumps.notification("Error", "", "LLM not configured", sound=False)
            return

        response = rumps.Window(
            message="Type your tasks naturally.\nAI will parse and organize them.",
            title="🧠 Brain Dump",
            default_text="",
            ok="Process",
            cancel="Cancel",
            dimensions=(500, 150)
        ).run()
        
        if not response.clicked or not response.text.strip():
            return
        
        text = response.text.strip()
        
        rumps.notification("🧠 Processing...", "", "Sending to AI...", sound=False)
        
        try:
            new_tasks, new_projects = llm_client.process_brain_dump(text)
            
            if not new_tasks:
                rumps.notification("No Tasks", "", "AI didn't find any tasks", sound=False)
                return
            
            # Load existing for project mapping
            existing_tasks, existing_projects = storage.load_data()
            
            # Merge projects
            existing_project_names = {p.name: p for p in existing_projects}
            project_id_map = {}
            final_projects = existing_projects.copy()
            
            for p in new_projects:
                if p.name in existing_project_names:
                    project_id_map[p.id] = existing_project_names[p.name].id
                else:
                    final_projects.append(p)
                    existing_project_names[p.name] = p
                    project_id_map[p.id] = p.id
            
            # Update task project IDs
            for t in new_tasks:
                if t.project_id in project_id_map:
                    t.project_id = project_id_map[t.project_id]
            
            # Build summary for confirmation
            project_map = {p.id: p.name for p in final_projects}
            task_summary_lines = []
            for i, t in enumerate(new_tasks, 1):
                p_name = project_map.get(t.project_id, "Unknown")
                p_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(t.priority, "")
                task_summary_lines.append(f"{i}. {p_icon} {t.title} ({p_name}) - {t.estimated_tomatoes}🍅")
            
            task_summary = "\n".join(task_summary_lines)
            
            # Confirmation dialog
            confirm = rumps.Window(
                message=f"Tasks parsed by AI:\n\n{task_summary}\n\nClick 'Save' to add these tasks, or 'Edit' to modify them first.",
                title="📋 Confirm Tasks",
                default_text="",
                ok="Save",
                cancel="Cancel",
                dimensions=(500, 200)
            ).run()
            
            if not confirm.clicked:
                rumps.notification("Cancelled", "", "Brain dump cancelled", sound=False)
                return
            
            # Edit option - if user typed something, interpret as edit instructions
            if confirm.text.strip():
                # User typed an index to edit
                edit_text = confirm.text.strip()
                if edit_text.isdigit():
                    idx = int(edit_text) - 1
                    if 0 <= idx < len(new_tasks):
                        task_to_edit = new_tasks[idx]
                        # Quick edit dialog
                        edit_response = rumps.Window(
                            message=f"Edit task: {task_to_edit.title}",
                            title="Edit Task",
                            default_text=task_to_edit.title,
                            ok="Update & Save All",
                            cancel="Cancel",
                            dimensions=(400, 24)
                        ).run()
                        
                        if not edit_response.clicked:
                            return
                        
                        task_to_edit.title = edit_response.text.strip() or task_to_edit.title
            
            # Save all tasks
            existing_tasks.extend(new_tasks)
            storage.save_data(existing_tasks, final_projects)
            
            rumps.notification(
                "✅ Tasks Added",
                f"{len(new_tasks)} task(s) created",
                ", ".join([t.title[:20] for t in new_tasks[:3]]),
                sound=True
            )
            
            # Force menu rebuild
            self._build_menu()
            
        except Exception as e:
            rumps.notification("❌ Error", "", str(e)[:100], sound=False)
    
    # --- GitHub Actions ---
    
    def _check_github(self, sender):
        """Check GitHub inbox for new issues."""
        if not HAS_GITHUB:
            rumps.notification("Error", "", "GitHub not configured", sound=False)
            return
        
        repo_name = os.getenv("GITHUB_REPO")
        rumps.notification("⌨️ Checking...", "", f"Fetching issues from {repo_name}...", sound=False)
        
        try:
            issues = github_client.fetch_open_issues(repo_name)
            
            if not issues:
                rumps.notification("📭 No Issues", "", "Inbox is empty!", sound=False)
                return
            
            # Build brain dump text from issues
            brain_dump_lines = []
            for number, title, body in issues:
                brain_dump_lines.append(f"- {title}")
                if body:
                    brain_dump_lines.append(f"  {body[:200]}")
            
            brain_dump_text = "\n".join(brain_dump_lines)
            
            if HAS_LLM:
                # Process with LLM
                new_tasks, new_projects = llm_client.process_brain_dump(brain_dump_text)
                
                existing_tasks, existing_projects = storage.load_data()
                
                # Merge projects
                existing_project_names = {p.name: p for p in existing_projects}
                project_id_map = {}
                
                for p in new_projects:
                    if p.name in existing_project_names:
                        project_id_map[p.id] = existing_project_names[p.name].id
                    else:
                        existing_projects.append(p)
                        existing_project_names[p.name] = p
                        project_id_map[p.id] = p.id
                
                for t in new_tasks:
                    if t.project_id in project_id_map:
                        t.project_id = project_id_map[t.project_id]
                
                existing_tasks.extend(new_tasks)
                storage.save_data(existing_tasks, existing_projects)
                
                # Close issues
                for number, _, _ in issues:
                    try:
                        github_client.close_issue(repo_name, number)
                    except Exception:
                        pass
                
                rumps.notification(
                    "✅ GitHub Inbox Processed",
                    f"{len(new_tasks)} task(s) from {len(issues)} issue(s)",
                    "Issues closed",
                    sound=True
                )
                self._build_menu()
            else:
                rumps.notification(
                    "📬 Issues Found",
                    f"{len(issues)} issue(s)",
                    "Configure LLM to auto-ingest",
                    sound=False
                )
                
        except Exception as e:
            rumps.notification("❌ Error", "", str(e)[:100], sound=False)
    
    def _sync_github(self, sender):
        """Sync tasks to GitHub."""
        if not HAS_GITHUB:
            rumps.notification("Error", "", "GitHub not configured", sound=False)
            return
        
        repo_name = os.getenv("GITHUB_REPO")
        
        try:
            # Check if private
            is_private = github_client.get_repo_privacy(repo_name)
            if not is_private:
                rumps.notification(
                    "⚠️ Security Warning",
                    "Repository is PUBLIC",
                    "Sync disabled for public repos",
                    sound=True
                )
                return
            
            tasks, projects = storage.load_data()
            project_map = {p.id: p.name for p in projects}
            
            # Build markdown
            md_lines = ["# Current Tasks", "", f"Last Updated: {datetime.now().isoformat()}", ""]
            
            # Group by project
            tasks_by_project = {}
            for t in tasks:
                if t.status == TaskStatus.ARCHIVED:
                    continue
                p_name = project_map.get(t.project_id, "No Project")
                if p_name not in tasks_by_project:
                    tasks_by_project[p_name] = []
                tasks_by_project[p_name].append(t)
            
            for p_name, p_tasks in tasks_by_project.items():
                md_lines.append(f"## {p_name}")
                md_lines.append("| Status | P | Title | Tomatoes | Deadline |")
                md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
                for t in p_tasks:
                    status_icon = "✅" if t.status == TaskStatus.DONE else "⬜"
                    if t.status == TaskStatus.IN_PROGRESS:
                        status_icon = "🍅"
                    p_icon = {"High": "🔴", "Medium": "🟡", "Low": "🔵"}.get(t.priority, "")
                    md_lines.append(
                        f"| {status_icon} | {p_icon} | {t.title} | "
                        f"{t.completed_tomatoes}/{t.estimated_tomatoes} | {t.deadline or ''} |"
                    )
                md_lines.append("")
            
            content = "\n".join(md_lines)
            github_client.update_file(repo_name, "tasks.md", content, "Update tasks.md via Menu Bar")
            
            rumps.notification(
                "☁️ Synced to GitHub",
                repo_name,
                "tasks.md updated",
                sound=True
            )
            
        except Exception as e:
            rumps.notification("❌ Sync Failed", "", str(e)[:100], sound=False)
    
    # --- Utility ---
    
    def _refresh(self, sender):
        """Refresh the menu."""
        self._build_menu()
        rumps.notification("🔄 Refreshed", "", "Task list updated", sound=False)
    
    def _open_terminal(self, sender):
        """Open Terminal with the CLI."""
        app_dir = os.path.dirname(os.path.abspath(__file__))
        os.system(f'open -a Terminal "{app_dir}"')
    
    def _quit(self, sender):
        """Quit the app."""
        self.timer_running = False
        rumps.quit_application()


if __name__ == "__main__":
    # Change to app directory so relative paths work
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    
    app = PomodoroMenuBar()
    app.run()
