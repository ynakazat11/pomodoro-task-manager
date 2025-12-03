import typer
import time
from rich.console import Console
from rich.table import Table
from typing import Optional, Annotated
from datetime import datetime, timedelta
import gemini_client
import storage
import timer
import github_client
import os
from models import TaskStatus, Task
from rich.panel import Panel
from rich.prompt import Prompt
import sys

app = typer.Typer()
console = Console()

def parse_task_refs(task_ref_str: str, tasks: list[Task]) -> list[str]:
    """
    Parses a string of task references (IDs or Indexes) into a list of Task IDs.
    Supports comma-separated values (1,2,3) and ranges (1-3).
    """
    target_ids = []
    refs = [r.strip() for r in task_ref_str.split(',')]
    
    for ref in refs:
        if '-' in ref and ref.replace('-', '').isdigit():
            # Range
            start, end = map(int, ref.split('-'))
            for i in range(start, end + 1):
                s_i = str(i)
                if s_i in TASK_INDEX_MAP:
                    target_ids.append(TASK_INDEX_MAP[s_i])
        elif ref.isdigit() and ref in TASK_INDEX_MAP:
            # Index
            target_ids.append(TASK_INDEX_MAP[ref])
        else:
            # ID prefix
            found = False
            for t in tasks:
                if t.id.startswith(ref):
                    target_ids.append(t.id)
                    found = True
                    break
            if not found:
                console.print(f"[yellow]Warning: Task reference '{ref}' not found.[/yellow]")
                
    return list(set(target_ids)) # Unique IDs

# Global map to store index -> task_id for the current session
TASK_INDEX_MAP = {}

@app.command()
def ingest(text: str):
    """
    Ingest a brain dump of tasks.
    """
    ingest_logic(text)

from typing import Optional, Annotated

def filter_tasks(tasks: list[Task], projects: list, project_filter: Optional[str] = None, due_filter: Optional[int] = None, id_filter: Optional[str] = None) -> list[Task]:
    """
    Helper to filter tasks based on criteria.
    """
    filtered = []
    project_map = {p.id: p.name for p in projects}
    today = datetime.now()
    
    for t in tasks:
        if t.status == TaskStatus.ARCHIVED:
            continue
            
        # ID Filter
        if id_filter and not t.id.startswith(id_filter):
            continue
            
        # Project Filter
        p_name = project_map.get(t.project_id, "No Project")
        if project_filter and project_filter.lower() not in p_name.lower():
            continue
            
        # Due Filter
        if due_filter is not None:
            if not t.deadline:
                continue
            try:
                d = datetime.fromisoformat(t.deadline)
                if (d - today).days > due_filter:
                    continue
            except ValueError:
                continue
                
        filtered.append(t)
    return filtered

def prompt_filter_options() -> dict:
    """
    Prompts user for filter options in interactive mode.
    Returns a dict of kwargs for filter_tasks/commands.
    """
    console.print("[dim]Filter options: [bold cyan]p[/bold cyan]roject, [bold cyan]d[/bold cyan]ue, [bold cyan]i[/bold cyan]d, or [bold white]Enter[/bold white] for all[/dim]")
    filter_choice = Prompt.ask("Filter?", default="").strip().lower()
    
    filters = {}
    if filter_choice == 'p':
        filters['project'] = Prompt.ask("Project Name")
    elif filter_choice == 'd':
        d_val = Prompt.ask("Due within X days")
        if d_val.isdigit():
            filters['due'] = int(d_val)
        else:
            console.print("[red]Invalid number, ignoring due filter.[/red]")
    elif filter_choice == 'i':
        filters['id'] = Prompt.ask("ID Prefix")
        
    return filters

@app.command(name="list")
def list_tasks(
    project: Annotated[Optional[str], typer.Option(help="Filter by project name (fuzzy match)")] = None,
    due: Annotated[Optional[int], typer.Option(help="Filter by tasks due within X days")] = None,
    id: Annotated[Optional[str], typer.Option(help="Filter by ID prefix")] = None
):
    """
    List all pending tasks.
    Default sort: Project -> Deadline -> ID.
    """
    global TASK_INDEX_MAP
    TASK_INDEX_MAP.clear()
    
    tasks, projects = storage.load_data()
    project_map = {p.id: p.name for p in projects}
    today = datetime.now()
    
    # Filter
    filtered_tasks = filter_tasks(tasks, projects, project, due, id)
        
    if not filtered_tasks:
        console.print("[yellow]No tasks found matching criteria.[/yellow]")
        return

    # Sort: Project Name -> Deadline (Empty last) -> ID
    def sort_key(t):
        p_name = project_map.get(t.project_id, "No Project")
        deadline_val = t.deadline if t.deadline else "9999-12-31"
        return (p_name, deadline_val, t.id)
        
    filtered_tasks.sort(key=sort_key)
    
    title = "Pending Tasks"
    if project: title += f" | Project: {project}"
    if due: title += f" | Due: {due} days"
    if id: title += f" | ID: {id}"
    
    table = Table(title=title)
    table.add_column("Index", style="bold white")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Tomatoes", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("Project", style="green")
    table.add_column("Deadline", style="red")
    
    current_index = 1
    for t in filtered_tasks:
        p_name = project_map.get(t.project_id, "No Project")
        status_color = "green" if t.status == TaskStatus.DONE else "yellow"
        
        TASK_INDEX_MAP[str(current_index)] = t.id
        
        deadline_str = t.deadline or ""
        deadline_style = ""
        if t.deadline:
            try:
                due_date = datetime.fromisoformat(t.deadline)
                delta = (due_date - today).days
                
                if delta < 0: # Overdue
                    deadline_style = "bold red"
                elif delta <= 0: # Due today (delta is -1 to 0 roughly depending on time)
                     if due_date.date() < today.date():
                         deadline_style = "bold red" # Overdue
                     elif due_date.date() == today.date():
                         deadline_style = "bold red" # Due Today
                     elif delta <= 7:
                         deadline_style = "yellow"
                     else:
                         deadline_style = "green"
                elif delta <= 7:
                    deadline_style = "yellow"
                else:
                    deadline_style = "green"
            except ValueError:
                pass

        table.add_row(
            str(current_index),
            t.id[:8], 
            t.title, 
            f"{t.completed_tomatoes}/{t.estimated_tomatoes}", 
            f"[{status_color}]{t.status.value}[/{status_color}]", 
            p_name,
            f"[{deadline_style}]{deadline_str}[/{deadline_style}]" if deadline_style else deadline_str
        )
        current_index += 1
            
    console.print(table)

@app.command()
def start(task_ref: str):
    """
    Start a Pomodoro timer for a specific task.
    Accepts Task ID (prefix) OR Task Index (if list was run previously).
    """
    tasks, projects = storage.load_data()
    
    target_task_id = None
    
    # Check if input is an index
    if task_ref.isdigit() and task_ref in TASK_INDEX_MAP:
        target_task_id = TASK_INDEX_MAP[task_ref]
    else:
        # Assume it's an ID prefix
        for t in tasks:
            if t.id.startswith(task_ref):
                target_task_id = t.id
                break
    
    if not target_task_id:
        console.print(f"[bold red]Task '{task_ref}' not found. Try running 'list' first.[/bold red]")
        return
        
    target_task = next((t for t in tasks if t.id == target_task_id), None)
            
    if not target_task:
        console.print(f"[bold red]Task with ID '{target_task_id}' not found.[/bold red]")
        return

    console.print(f"[bold]Starting Pomodoro for:[/bold] {target_task.title}")
    
    # Update status to in_progress
    target_task.status = TaskStatus.IN_PROGRESS
    storage.save_data(tasks, projects)
    
    try:
        timer.run_timer(minutes=25, task_title=target_task.title)
        
        # Timer finished naturally
        target_task.completed_tomatoes += 1
        console.print(f"[bold green]One tomato added to '{target_task.title}'[/bold green]")
        
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Timer stopped.[/bold yellow]")
    
    # Always ask if done, whether finished or stopped
    is_done = typer.confirm("Did you finish this task?")
    if is_done:
        target_task.status = TaskStatus.DONE
        target_task.completed_at = datetime.now().isoformat()
        console.print(f"[bold green]Task marked as DONE![/bold green]")
    else:
        console.print("[yellow]Task status remains 'in_progress'.[/yellow]")
        
    storage.save_data(tasks, projects)

@app.command()
def stats(
    project: Annotated[Optional[str], typer.Option(help="Filter by project name")] = None,
    due: Annotated[Optional[int], typer.Option(help="Filter by tasks due within X days")] = None,
    id: Annotated[Optional[str], typer.Option(help="Filter by ID prefix")] = None
):
    """
    Show progress statistics.
    """
    tasks, projects = storage.load_data()
    
    # Filter tasks first
    # Note: filter_tasks excludes archived, but for stats we might want to see completed ones too?
    # The original stats logic iterated over ALL tasks (including archived? No, load_data returns all).
    # Original logic:
    # for t in tasks:
    #    total_estimated += t.estimated_tomatoes
    #    total_completed += t.completed_tomatoes
    
    # If we use filter_tasks, it excludes ARCHIVED.
    # Let's use filter_tasks but maybe we want to include done/archived for stats?
    # Usually stats are for "active" or "all time"?
    # The original code: "for t in tasks:" -> implies all tasks loaded.
    # But wait, filter_tasks has "if t.status == TaskStatus.ARCHIVED: continue".
    # If I want to filter by project, I should probably filter ALL tasks.
    
    # Let's make a custom filter loop here or modify filter_tasks to accept a status list?
    # For simplicity, let's just filter manually here reusing logic or just copy-paste for now to be safe about ARCHIVED.
    # Actually, if I filter by project "Work", I want to see stats for "Work".
    
    filtered_tasks = []
    project_map = {p.id: p.name for p in projects}
    today = datetime.now()
    
    for t in tasks:
        # ID Filter
        if id and not t.id.startswith(id):
            continue
            
        # Project Filter
        p_name = project_map.get(t.project_id, "No Project")
        if project and project.lower() not in p_name.lower():
            continue
            
        # Due Filter
        if due is not None:
            if not t.deadline:
                continue
            try:
                d = datetime.fromisoformat(t.deadline)
                if (d - today).days > due:
                    continue
            except ValueError:
                continue
                
        filtered_tasks.append(t)
    
    total_estimated = 0
    total_completed = 0
    
    # Calculate stats for filtered tasks
    for t in filtered_tasks:
        total_estimated += t.estimated_tomatoes
        total_completed += t.completed_tomatoes
        
    if total_estimated == 0 and total_completed == 0:
        console.print("[yellow]No tasks found matching criteria.[/yellow]")
        return
        
    percentage = (total_completed / total_estimated) * 100 if total_estimated > 0 else 0
    
    title_text = "Statistics"
    if project: title_text += f" | Project: {project}"
    
    console.print(Panel(f"""
    [bold]Total Progress[/bold]
    
    Completed Tomatoes: [green]{total_completed}[/green]
    Estimated Tomatoes: [blue]{total_estimated}[/blue]
    Progress: [magenta]{percentage:.1f}%[/magenta]
    """, title=title_text, border_style="blue"))
    
    # Breakdown by Project
    project_stats = {}
    
    for t in filtered_tasks:
        p_name = project_map.get(t.project_id, "No Project")
        if p_name not in project_stats:
            project_stats[p_name] = {"est": 0, "comp": 0}
        project_stats[p_name]["est"] += t.estimated_tomatoes
        project_stats[p_name]["comp"] += t.completed_tomatoes
        
    table = Table(title="Project Breakdown")
    table.add_column("Project", style="cyan")
    table.add_column("Progress", style="magenta")
    table.add_column("Percentage", style="green")
    
    for p_name, stats in project_stats.items():
        pct = (stats["comp"] / stats["est"]) * 100 if stats["est"] > 0 else 0
        table.add_row(p_name, f"{stats['comp']}/{stats['est']}", f"{pct:.1f}%")
        
    console.print(table)

@app.command()
def archive(days: int = 0):
    """
    Archive completed tasks.
    If --days is provided, only archive tasks completed more than X days ago.
    Default is 0 (archive all completed tasks).
    """
    tasks, projects = storage.load_data()
    
    tasks_to_keep = []
    tasks_to_archive = []
    
    cutoff_date = datetime.now() - timedelta(days=days)
    
    for t in tasks:
        should_archive = False
        if t.status == TaskStatus.DONE:
            if days == 0:
                should_archive = True
            elif t.completed_at:
                # Parse completed_at
                try:
                    comp_date = datetime.fromisoformat(t.completed_at)
                    if comp_date < cutoff_date:
                        should_archive = True
                except ValueError:
                    pass # Keep if date is invalid
                    
        if should_archive:
            t.status = TaskStatus.ARCHIVED
            tasks_to_archive.append(t)
        else:
            tasks_to_keep.append(t)
            
    if not tasks_to_archive:
        console.print("[yellow]No tasks to archive.[/yellow]")
        return
        
    # Save active tasks
    storage.save_data(tasks_to_keep, projects)
    
    # Append to archive
    storage.append_to_archive(tasks_to_archive)
    
    console.print(f"[bold green]Archived {len(tasks_to_archive)} tasks.[/bold green]")
    console.print(f"[bold green]Archived {len(tasks_to_archive)} tasks.[/bold green]")

@app.command()
def delete(task_refs: str):
    """
    Delete task(s) by ID or Index.
    Supports multiple tasks: "1,2,3" or "1-3".
    """
    tasks, projects = storage.load_data()
    
    target_ids = parse_task_refs(task_refs, tasks)
    
    if not target_ids:
        console.print("[bold red]No valid tasks found.[/bold red]")
        return
        
    tasks_to_delete = []
    for t_id in target_ids:
        t = next((t for t in tasks if t.id == t_id), None)
        if t:
            tasks_to_delete.append(t)
            
    if not tasks_to_delete:
        console.print("[bold red]No tasks found to delete.[/bold red]")
        return
        
    console.print(f"[bold]Tasks to delete:[/bold]")
    for t in tasks_to_delete:
        console.print(f" - {t.title}")
        
    confirm = typer.confirm(f"Are you sure you want to delete these {len(tasks_to_delete)} tasks?")
    if not confirm:
        console.print("[yellow]Deletion cancelled.[/yellow]")
        return

    # Filter out
    new_tasks = [t for t in tasks if t.id not in target_ids]
        
    storage.save_data(new_tasks, projects)
    console.print(f"[bold green]Deleted {len(tasks_to_delete)} tasks.[/bold green]")

@app.command()
def edit(task_refs: str):
    """
    Edit task(s) by ID or Index.
    Supports multiple tasks: "1,2,3" or "1-3".
    """
    tasks, projects = storage.load_data()
    target_ids = parse_task_refs(task_refs, tasks)
    
    if not target_ids:
        console.print("[bold red]No valid tasks found.[/bold red]")
        return
        
    target_tasks = [t for t in tasks if t.id in target_ids]
    project_map = {p.id: p.name for p in projects}
    
    if len(target_tasks) == 1:
        # Single Task Edit
        t = target_tasks[0]
        p_name = project_map.get(t.project_id, "Unknown")
        console.print(Panel(f"""
        [bold]Editing Task[/bold]
        Title: {t.title}
        Tomatoes: {t.estimated_tomatoes}
        Project: {p_name}
        Deadline: {t.deadline or 'None'}
        """, title="Current Details", border_style="blue"))
        
        # Title
        new_title = Prompt.ask("New Title", default=t.title)
        t.title = new_title
        
        # Tomatoes
        new_tomatoes = Prompt.ask("New Tomatoes", default=str(t.estimated_tomatoes))
        if new_tomatoes.isdigit():
            t.estimated_tomatoes = int(new_tomatoes)
            
        # Deadline
        new_deadline = Prompt.ask("New Deadline (YYYY-MM-DD)", default=t.deadline or "")
        t.deadline = new_deadline if new_deadline.strip() else None
        
        # Project
        new_p_name = Prompt.ask("New Project", default=p_name)
        if new_p_name != p_name:
            # Find or create
            found_p = next((p for p in projects if p.name == new_p_name), None)
            if found_p:
                t.project_id = found_p.id
            else:
                if typer.confirm(f"Create new project '{new_p_name}'?"):
                    new_p = gemini_client.Project(
                        id=f"p_{datetime.now().timestamp()}",
                        name=new_p_name,
                        description="",
                        created_at=datetime.now().isoformat()
                    )
                    projects.append(new_p)
                    t.project_id = new_p.id
                    
        console.print("[bold green]Task updated![/bold green]")
        
    else:
        # Bulk Edit
        console.print(f"[bold blue]Bulk Editing {len(target_tasks)} Tasks[/bold blue]")
        console.print("What do you want to update?")
        console.print("[green]p[/green]: Project")
        console.print("[red]d[/red]: Deadline")
        console.print("[magenta]t[/magenta]: Tomatoes")
        console.print("[cyan]i[/cyan]: Iterate Titles (rename one by one)")
        
        choice = Prompt.ask("Choice", choices=["p", "d", "t", "i"])
        
        if choice == "p":
            # List projects
            console.print("Existing Projects:")
            unique_p_names = sorted(list({p.name for p in projects}))
            for name in unique_p_names:
                console.print(f" - {name}")
                
            new_p_name = Prompt.ask("Enter New Project Name")
            
            # Find or create
            found_p = next((p for p in projects if p.name == new_p_name), None)
            target_p_id = None
            
            if found_p:
                target_p_id = found_p.id
            else:
                if typer.confirm(f"Create new project '{new_p_name}'?"):
                    new_p = gemini_client.Project(
                        id=f"p_{datetime.now().timestamp()}",
                        name=new_p_name,
                        description="",
                        created_at=datetime.now().isoformat()
                    )
                    projects.append(new_p)
                    target_p_id = new_p.id
            
            if target_p_id:
                for t in target_tasks:
                    t.project_id = target_p_id
                console.print(f"[bold green]Updated project for {len(target_tasks)} tasks.[/bold green]")
                
        elif choice == "d":
            new_deadline = Prompt.ask("New Deadline (YYYY-MM-DD) for ALL", default="")
            val = new_deadline if new_deadline.strip() else None
            for t in target_tasks:
                t.deadline = val
            console.print(f"[bold green]Updated deadline for {len(target_tasks)} tasks.[/bold green]")
            
        elif choice == "t":
            new_tomatoes = Prompt.ask("New Tomatoes count for ALL")
            if new_tomatoes.isdigit():
                val = int(new_tomatoes)
                for t in target_tasks:
                    t.estimated_tomatoes = val
                console.print(f"[bold green]Updated tomatoes for {len(target_tasks)} tasks.[/bold green]")
                
        elif choice == "i":
            for t in target_tasks:
                console.print(f"Editing: [dim]{t.id[:8]}[/dim]")
                new_title = Prompt.ask("Title", default=t.title)
                t.title = new_title
            console.print(f"[bold green]Updated titles for {len(target_tasks)} tasks.[/bold green]")

    storage.save_data(tasks, projects)

@app.command()
def complete(task_refs: str):
    """
    Mark task(s) as done by ID or Index.
    Supports multiple tasks: "1,2,3" or "1-3".
    """
    tasks, projects = storage.load_data()
    
    target_ids = parse_task_refs(task_refs, tasks)
    
    if not target_ids:
        console.print("[bold red]No valid tasks found.[/bold red]")
        return
        
    count = 0
    for t in tasks:
        if t.id in target_ids:
            t.status = TaskStatus.DONE
            t.completed_at = datetime.now().isoformat()
            count += 1
    
    storage.save_data(tasks, projects)
    console.print(f"[bold green]Marked {count} tasks as DONE![/bold green]")

@app.command()
def check_github():
    """
    Check GitHub Inbox for new issues and ingest them.
    """
    repo_name = os.getenv("GITHUB_REPO")
    if not repo_name:
        console.print("[bold red]GITHUB_REPO not set in .env file.[/bold red]")
        return
        
    console.print(f"[bold blue]Checking GitHub repository '{repo_name}' for open issues...[/bold blue]")
    
    try:
        # Fetch issues
        issues = github_client.fetch_open_issues(repo_name)
        
        if not issues:
            console.print("[yellow]No open issues found.[/yellow]")
            return
            
        console.print(f"[green]Found {len(issues)} open issues.[/green]")
        
        # Construct brain dump text
        brain_dump_lines = []
        for number, title, body in issues:
            brain_dump_lines.append(f"- {title}")
            if body:
                brain_dump_lines.append(f"  {body}")
                
        brain_dump_text = "\n".join(brain_dump_lines)
        
        # Reuse ingest logic (but we need to handle the review loop and closing issues)
        # We can call ingest(brain_dump_text) but we need to know if it was saved to close issues.
        # Refactoring ingest to return success status would be best, but for now let's just call it.
        # If the user saves in ingest, we assume success.
        # BUT `ingest` is a command, calling it directly is fine but we can't easily get return value if it's just printing.
        # However, since we are in the same process, we can just check if data changed? No.
        
        # Let's just run the ingest logic here or refactor ingest to be reusable.
        # For simplicity, let's copy the ingest logic structure or extract it.
        # Actually, `ingest` function is right there. Let's modify `ingest` to return True/False if saved?
        # Or just assume if they don't crash it's fine?
        # Better: Let's extract the "Review Loop" part of ingest into a helper, but that's a big refactor.
        
        # Let's just call ingest. If the user discards, we shouldn't close issues.
        # We need a way to know.
        # Let's modify `ingest` to return a boolean.
        
        saved = ingest_logic(brain_dump_text)
        
        if saved:
            console.print("[bold blue]Closing GitHub issues...[/bold blue]")
            for number, _, _ in issues:
                try:
                    github_client.close_issue(repo_name, number)
                    console.print(f" - Closed issue #{number}")
                except Exception as e:
                    console.print(f"[red]Failed to close issue #{number}: {e}[/red]")
            console.print("[bold green]GitHub sync complete![/bold green]")
        else:
            console.print("[yellow]Ingest discarded. GitHub issues left open.[/yellow]")

    except Exception as e:
        console.print(f"[bold red]Error checking GitHub:[/bold red] {e}")

@app.command()
def sync():
    """
    Sync current tasks to GitHub (tasks.md).
    Requires GITHUB_REPO to be a PRIVATE repository.
    """
    repo_name = os.getenv("GITHUB_REPO")
    if not repo_name:
        console.print("[bold red]GITHUB_REPO not set in .env file.[/bold red]")
        return
        
    console.print(f"[bold blue]Syncing tasks to '{repo_name}'...[/bold blue]")
    
    try:
        # 1. Check Privacy
        is_private = github_client.get_repo_privacy(repo_name)
        if not is_private:
            console.print("[bold red]SECURITY WARNING: Repository is PUBLIC![/bold red]")
            console.print("To protect your privacy, sync is disabled for public repositories.")
            return

        # 2. Load Data
        tasks, projects = storage.load_data()
        project_map = {p.id: p.name for p in projects}
        
        # 3. Format Markdown
        md_lines = ["# Current Tasks", "", f"Last Updated: {datetime.now().isoformat()}", ""]
        
        # 3a. Due Soon Section
        today = datetime.now()
        due_soon_tasks = []
        for t in tasks:
            if t.status in [TaskStatus.TODO, TaskStatus.IN_PROGRESS] and t.deadline:
                try:
                    d = datetime.fromisoformat(t.deadline)
                    if (d - today).days <= 7: # Overdue or within 7 days
                        due_soon_tasks.append((t, d))
                except ValueError:
                    pass
        
        if due_soon_tasks:
            due_soon_tasks.sort(key=lambda x: x[1])
            md_lines.append("## 🚨 Due Soon (Next 7 Days)")
            md_lines.append("| Date | Title | Project |")
            md_lines.append("| :--- | :--- | :--- |")
            for t, d in due_soon_tasks:
                icon = "🔴" if d.date() <= today.date() else "🟡"
                p_name = project_map.get(t.project_id, "Unknown")
                md_lines.append(f"| {icon} {t.deadline} | {t.title} | {p_name} |")
            md_lines.append("")
        
        # Group by Project
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
            md_lines.append("| ID | Status | Title | Tomatoes | Deadline |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- |")
            for t in p_tasks:
                status_icon = "✅" if t.status == TaskStatus.DONE else "⬜"
                if t.status == TaskStatus.IN_PROGRESS:
                    status_icon = "🍅"
                md_lines.append(f"| `{t.id[:8]}` | {status_icon} | {t.title} | {t.completed_tomatoes}/{t.estimated_tomatoes} | {t.deadline or ''} |")
            md_lines.append("")
            
        content = "\n".join(md_lines)
        
        # 4. Push to GitHub
        github_client.update_file(repo_name, "tasks.md", content, "Update tasks.md via CLI")
        console.print("[bold green]Successfully synced 'tasks.md' to GitHub![/bold green]")
        
    except Exception as e:
        console.print(f"[bold red]Sync failed:[/bold red] {e}")

@app.command()
def due(days: int = 7):
    """
    List tasks due within the next X days (default 7).
    """
    tasks, projects = storage.load_data()
    project_map = {p.id: p.name for p in projects}
    
    cutoff_date = datetime.now() + timedelta(days=days)
    today = datetime.now()
    
    due_tasks = []
    
    for t in tasks:
        if t.status == TaskStatus.ARCHIVED or t.status == TaskStatus.DONE:
            continue
        if not t.deadline:
            continue
            
        try:
            t_date = datetime.fromisoformat(t.deadline)
            # Check if due date is <= cutoff (and we include overdue tasks too usually?)
            # Let's include everything up to cutoff.
            if t_date.date() <= cutoff_date.date():
                due_tasks.append((t, t_date))
        except ValueError:
            continue
            
    if not due_tasks:
        console.print(f"[green]No tasks due within the next {days} days![/green]")
        return
        
    # Sort by date
    due_tasks.sort(key=lambda x: x[1])
    
    table = Table(title=f"Tasks Due Within {days} Days")
    table.add_column("Date", style="bold white")
    table.add_column("Title", style="cyan")
    table.add_column("Project", style="green")
    
    for t, date in due_tasks:
        style = "green"
        if date.date() < today.date():
            style = "bold red" # Overdue
        elif date.date() == today.date():
            style = "bold red" # Today
        elif (date - today).days <= 7:
            style = "yellow"
            
        table.add_row(
            f"[{style}]{t.deadline}[/{style}]",
            t.title,
            project_map.get(t.project_id, "Unknown")
        )
        
    console.print(table)

def ingest_logic(text: str) -> bool:
    """
    Reusable ingest logic. Returns True if saved, False if discarded.
    """
    console.print("[bold blue]Processing with Gemini...[/bold blue]")
    try:
        new_tasks, new_projects = gemini_client.process_brain_dump(text)
        
        # Load existing data
        existing_tasks, existing_projects = storage.load_data()
        
        # Initial smart merge of projects
        existing_project_names = {p.name: p for p in existing_projects}
        final_projects = existing_projects.copy()
        
        # Map new project IDs to existing ones if name matches
        project_id_map = {} # old_id -> new_id
        
        for p in new_projects:
            if p.name in existing_project_names:
                existing_p = existing_project_names[p.name]
                project_id_map[p.id] = existing_p.id
            else:
                final_projects.append(p)
                existing_project_names[p.name] = p
                project_id_map[p.id] = p.id
                
        # Update tasks with mapped project IDs
        for t in new_tasks:
            if t.project_id in project_id_map:
                t.project_id = project_id_map[t.project_id]

        # Review Loop
        while True:
            console.clear()
            console.print(Panel("[bold blue]Review Ingested Tasks[/bold blue]"))
            
            table = Table(title="Draft Tasks")
            table.add_column("Index", style="bold white")
            table.add_column("Project", style="green")
            table.add_column("Title", style="cyan")
            table.add_column("Tomatoes", style="magenta")
            table.add_column("Deadline", style="red")
            
            project_map = {p.id: p.name for p in final_projects}
            
            for i, t in enumerate(new_tasks, 1):
                p_name = project_map.get(t.project_id, "Unknown")
                table.add_row(str(i), p_name, t.title, str(t.estimated_tomatoes), t.deadline or "")
                
            console.print(table)
            
            console.print("\n[bold]Options:[/bold]")
            console.print("[green]s[/green]: Save and Finish")
            console.print("[red]d[/red]: Discard and Exit")
            console.print("[cyan]e <index>[/cyan]: Edit Task")
            console.print("[yellow]m[/yellow]: Merge Projects")
            
            choice = Prompt.ask("Action").strip().lower()
            
            if choice == 's':
                final_tasks = existing_tasks + new_tasks
                storage.save_data(final_tasks, final_projects)
                console.print(f"[bold green]Successfully added {len(new_tasks)} tasks![/bold green]")
                return True
                
            elif choice == 'd':
                console.print("[yellow]Discarded.[/yellow]")
                return False
                
            elif choice.startswith('e '):
                try:
                    idx = int(choice.split()[1]) - 1
                    if 0 <= idx < len(new_tasks):
                        task = new_tasks[idx]
                        console.print(f"Editing: [bold]{task.title}[/bold]")
                        
                        new_title = Prompt.ask("Title", default=task.title)
                        task.title = new_title
                        
                        new_tomatoes = Prompt.ask("Tomatoes", default=str(task.estimated_tomatoes))
                        if new_tomatoes.isdigit():
                            task.estimated_tomatoes = int(new_tomatoes)
                            
                        # Edit Deadline
                        new_deadline = Prompt.ask("Deadline (YYYY-MM-DD)", default=task.deadline or "")
                        task.deadline = new_deadline if new_deadline.strip() else None
                            
                        # Edit Project
                        current_p_name = project_map.get(task.project_id, "Unknown")
                        new_p_name = Prompt.ask("Project", default=current_p_name)
                        
                        # Find or create project
                        found_p = next((p for p in final_projects if p.name == new_p_name), None)
                        if found_p:
                            task.project_id = found_p.id
                        else:
                            # Create new project?
                            if typer.confirm(f"Create new project '{new_p_name}'?"):
                                new_p = gemini_client.Project(
                                    id=f"p_{datetime.now().timestamp()}",
                                    name=new_p_name,
                                    description="",
                                    created_at=datetime.now().isoformat()
                                )
                                final_projects.append(new_p)
                                task.project_id = new_p.id
                    else:
                        console.print("[red]Invalid index[/red]")
                        time.sleep(1)
                except (ValueError, IndexError):
                    console.print("[red]Invalid format. Use 'e <index>'[/red]")
                    time.sleep(1)
                    
            elif choice == 'm':
                # Simple merge workflow
                # List projects
                p_list = list({p.name for p in final_projects if any(t.project_id == p.id for t in new_tasks)})
                console.print("Active Projects in Draft:")
                for i, name in enumerate(p_list, 1):
                    console.print(f"{i}. {name}")
                    
                try:
                    src_idx = int(Prompt.ask("Merge FROM (index)")) - 1
                    dest_idx = int(Prompt.ask("Merge INTO (index)")) - 1
                    
                    if 0 <= src_idx < len(p_list) and 0 <= dest_idx < len(p_list) and src_idx != dest_idx:
                        src_name = p_list[src_idx]
                        dest_name = p_list[dest_idx]
                        
                        src_p = next(p for p in final_projects if p.name == src_name)
                        dest_p = next(p for p in final_projects if p.name == dest_name)
                        
                        # Move tasks
                        count = 0
                        for t in new_tasks:
                            if t.project_id == src_p.id:
                                t.project_id = dest_p.id
                                count += 1
                        console.print(f"[green]Moved {count} tasks from '{src_name}' to '{dest_name}'[/green]")
                        time.sleep(1)
                    else:
                        console.print("[red]Invalid selection[/red]")
                        time.sleep(1)
                except ValueError:
                    console.print("[red]Invalid input[/red]")
                    time.sleep(1)
            else:
                console.print("[red]Unknown command[/red]")
                time.sleep(1)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return False

@app.command()
def interactive():
    """
    Start the interactive session.
    """
    console.print(Panel.fit("[bold blue]Welcome to Pomodoro Task Manager[/bold blue]", border_style="blue"))
    
    # Startup Summary
    tasks, _ = storage.load_data()
    today = datetime.now()
    due_soon_count = 0
    overdue_count = 0
    
    for t in tasks:
        if t.status in [TaskStatus.TODO, TaskStatus.IN_PROGRESS] and t.deadline:
            try:
                d = datetime.fromisoformat(t.deadline)
                if d.date() < today.date():
                    overdue_count += 1
                elif (d - today).days <= 7:
                    due_soon_count += 1
            except ValueError:
                pass
                
    if overdue_count > 0:
        console.print(f"🚨 [bold red]You have {overdue_count} OVERDUE task(s)![/bold red]")
    if due_soon_count > 0:
        console.print(f"📅 [yellow]You have {due_soon_count} task(s) due within 7 days.[/yellow]")
    
    while True:
        console.print("\n[bold]Main Menu[/bold]")
        console.print("1. [cyan]Ingest Tasks[/cyan] (Brain Dump)")
        console.print("2. [cyan]List Tasks[/cyan]")
        console.print("3. [cyan]Start Task[/cyan]")
        console.print("4. [cyan]Check Progress[/cyan]")
        console.print("5. [cyan]Archive Completed[/cyan]")
        console.print("6. [cyan]Mark Task Done[/cyan]")
        console.print("7. [red]Delete Task[/red]")
        console.print("8. [magenta]Check GitHub Inbox[/magenta]")
        console.print("9. [cyan]Sync to GitHub[/cyan]")
        console.print("10. [yellow]Edit Task(s)[/yellow]")
        console.print("11. [red]Exit[/red]")
        
        choice = Prompt.ask("What would you like to do?", choices=["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11"], default="2")
        
        if choice == "1":
            text = Prompt.ask("Enter your brain dump")
            ingest(text)
        elif choice == "2":
            # List with filters
            filters = prompt_filter_options()
            list_tasks(**filters)
        elif choice == "3":
            # Start Task - List first (maybe filtered?)
            # User might want to filter to find the task to start
            console.print("[dim]Tip: You can filter the list to find your task.[/dim]")
            filters = prompt_filter_options()
            list_tasks(**filters)
            
            task_id = Prompt.ask("Enter Task ID (or prefix)")
            start(task_id)
        elif choice == "4":
            # Stats with filters
            filters = prompt_filter_options()
            stats(**filters)
        elif choice == "5":
            days = Prompt.ask("Archive tasks older than X days (0 for all) or 'exit'", default="0")
            if days.lower() == "exit":
                console.print("[yellow]Cancelled.[/yellow]")
                continue
            try:
                archive(int(days))
            except ValueError:
                console.print("[red]Invalid number[/red]")
        elif choice == "6":
            # Mark Done - Filter first
            filters = prompt_filter_options()
            list_tasks(**filters)
            
            task_refs = Prompt.ask("Enter Task Index(es) or ID(s) to mark done (e.g. 1,2 or 1-3) or 'exit'")
            if task_refs.lower() == "exit":
                console.print("[yellow]Cancelled.[/yellow]")
                continue
            complete(task_refs)
        elif choice == "7":
            # Delete - Filter first
            filters = prompt_filter_options()
            list_tasks(**filters)
            
            task_refs = Prompt.ask("Enter Task Index(es) or ID(s) to delete (e.g. 1,2 or 1-3) or 'exit'")
            if task_refs.lower() == "exit":
                console.print("[yellow]Cancelled.[/yellow]")
                continue
            delete(task_refs)
        elif choice == "8":
            check_github()
        elif choice == "9":
            sync()
        elif choice == "10":
            # Edit - Filter first
            filters = prompt_filter_options()
            list_tasks(**filters)
            
            task_refs = Prompt.ask("Enter Task Index(es) or ID(s) to edit (e.g. 1,2 or 1-3) or 'exit'")
            if task_refs.lower() == "exit":
                console.print("[yellow]Cancelled.[/yellow]")
                continue
            edit(task_refs)
        elif choice == "11":
            console.print("[bold blue]Goodbye![/bold blue]")
            break

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default to interactive mode if no arguments provided
        sys.argv.append("interactive")
    app()
