import typer
from rich.console import Console
from rich.table import Table
from typing import Optional
from datetime import datetime, timedelta
import gemini_client
import storage
import timer
from models import TaskStatus, Task
from rich.panel import Panel
from rich.prompt import Prompt
import sys

app = typer.Typer()
console = Console()

# Global map to store index -> task_id for the current session
TASK_INDEX_MAP = {}

@app.command()
def ingest(text: str):
    """
    Ingest a brain dump of tasks.
    """
    console.print("[bold blue]Processing your brain dump with Gemini...[/bold blue]")
    try:
        new_tasks, new_projects = gemini_client.process_brain_dump(text)
        
        # Load existing data
        existing_tasks, existing_projects = storage.load_data()
        
        # Merge projects (simple name check could be better, but for now just append)
        # Ideally we check if project name exists.
        existing_project_names = {p.name: p for p in existing_projects}
        
        final_projects = existing_projects.copy()
        
        # Update project IDs in new tasks if project already exists
        for p in new_projects:
            if p.name in existing_project_names:
                # Use existing project ID
                existing_p = existing_project_names[p.name]
                # Update all new tasks that pointed to this new p to point to existing_p
                for t in new_tasks:
                    if t.project_id == p.id:
                        t.project_id = existing_p.id
            else:
                final_projects.append(p)
                existing_project_names[p.name] = p # Add to map for subsequent checks
        
        final_tasks = existing_tasks + new_tasks
        
        storage.save_data(final_tasks, final_projects)
        
        console.print(f"[bold green]Successfully added {len(new_tasks)} tasks and {len(new_projects)} new projects![/bold green]")
        
        # Show summary
        table = Table(title="New Tasks")
        table.add_column("Index", style="dim")
        table.add_column("Project", style="green")
        table.add_column("Title", style="cyan")
        table.add_column("Tomatoes", style="magenta")
        
        project_map = {p.id: p.name for p in final_projects}
        
        # We can't easily give them a permanent index here without reloading everything and sorting
        # But for "New Tasks" display, we can just show them as 1..N relative to this batch, 
        # OR we can just show "-" since they are not in the main list yet.
        # User asked for "Task Index", implying they want to be able to reference them?
        # Let's just show "-" for now as they need to run 'list' to get the actionable index.
        # Or better, we can just list everything after ingest.
        
        for i, t in enumerate(new_tasks, 1):
            p_name = project_map.get(t.project_id, "Unknown")
            table.add_row("-", p_name, t.title, str(t.estimated_tomatoes))
            
        console.print(table)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command()
def list():
    """
    List all pending tasks.
    """
    global TASK_INDEX_MAP
    TASK_INDEX_MAP.clear()
    
    tasks, projects = storage.load_data()
    project_map = {p.id: p.name for p in projects}
    
    table = Table(title="Pending Tasks")
    table.add_column("Index", style="bold white")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Tomatoes", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("Project", style="green")
    
    current_index = 1
    # Sort by project maybe?
    for t in tasks:
        if t.status != TaskStatus.ARCHIVED:
            p_name = project_map.get(t.project_id, "No Project")
            status_color = "green" if t.status == TaskStatus.DONE else "yellow"
            
            TASK_INDEX_MAP[str(current_index)] = t.id
            
            table.add_row(
                str(current_index),
                t.id[:8], 
                t.title, 
                f"{t.completed_tomatoes}/{t.estimated_tomatoes}", 
                f"[{status_color}]{t.status.value}[/{status_color}]", 
                p_name
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
        
        # Timer finished
        target_task.completed_tomatoes += 1
        console.print(f"[bold green]One tomato added to '{target_task.title}'[/bold green]")
        
        # Ask if done
        is_done = typer.confirm("Did you finish this task?")
        if is_done:
            target_task.status = TaskStatus.DONE
            target_task.completed_at = datetime.now().isoformat()
            console.print(f"[bold green]Task marked as DONE![/bold green]")
        else:
            # Ask if want to continue immediately? Or just exit.
            # Usually Pomodoro implies a break.
            console.print("[yellow]Take a short break![/yellow]")
            
        storage.save_data(tasks, projects)
        
    except KeyboardInterrupt:
        console.print("\n[bold red]Timer cancelled.[/bold red]")

@app.command()
def stats():
    """
    Show progress statistics.
    """
    tasks, projects = storage.load_data()
    
    total_estimated = 0
    total_completed = 0
    
    # Calculate stats for active tasks
    for t in tasks:
        total_estimated += t.estimated_tomatoes
        total_completed += t.completed_tomatoes
        
    if total_estimated == 0:
        console.print("[yellow]No tasks found.[/yellow]")
        return
        
    percentage = (total_completed / total_estimated) * 100 if total_estimated > 0 else 0
    
    console.print(Panel(f"""
    [bold]Total Progress[/bold]
    
    Completed Tomatoes: [green]{total_completed}[/green]
    Estimated Tomatoes: [blue]{total_estimated}[/blue]
    Progress: [magenta]{percentage:.1f}%[/magenta]
    """, title="Statistics", border_style="blue"))
    
    # Breakdown by Project
    project_map = {p.id: p.name for p in projects}
    project_stats = {}
    
    for t in tasks:
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
def delete(task_ref: str):
    """
    Delete a task by ID or Index.
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
        
    # Filter out the task
    target_task = next((t for t in tasks if t.id == target_task_id), None)
    
    if not target_task:
        console.print(f"[bold red]Task not found.[/bold red]")
        return
        
    confirm = typer.confirm(f"Are you sure you want to delete '{target_task.title}'?")
    if not confirm:
        console.print("[yellow]Deletion cancelled.[/yellow]")
        return

    new_tasks = [t for t in tasks if t.id != target_task_id]
        
    storage.save_data(new_tasks, projects)
    console.print(f"[bold green]Task deleted.[/bold green]")

@app.command()
def complete(task_ref: str):
    """
    Mark a task as done by ID or Index.
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
        
    target_task.status = TaskStatus.DONE
    target_task.completed_at = datetime.now().isoformat()
    
    storage.save_data(tasks, projects)
    console.print(f"[bold green]Task '{target_task.title}' marked as DONE![/bold green]")

@app.command()
def interactive():
    """
    Start the interactive session.
    """
    console.print(Panel.fit("[bold blue]Welcome to Pomodoro Task Manager[/bold blue]", border_style="blue"))
    
    while True:
        console.print("\n[bold]Main Menu[/bold]")
        console.print("1. [cyan]Ingest Tasks[/cyan] (Brain Dump)")
        console.print("2. [cyan]List Tasks[/cyan]")
        console.print("3. [cyan]Start Task[/cyan]")
        console.print("4. [cyan]Check Progress[/cyan]")
        console.print("5. [cyan]Archive Completed[/cyan]")
        console.print("6. [cyan]Mark Task Done[/cyan]")
        console.print("7. [red]Delete Task[/red]")
        console.print("8. [red]Exit[/red]")
        
        choice = Prompt.ask("What would you like to do?", choices=["1", "2", "3", "4", "5", "6", "7", "8"], default="2")
        
        if choice == "1":
            text = Prompt.ask("Enter your brain dump")
            ingest(text)
        elif choice == "2":
            list()
        elif choice == "3":
            # List tasks first to see IDs
            list()
            task_id = Prompt.ask("Enter Task ID (or prefix)")
            start(task_id)
        elif choice == "4":
            stats()
        elif choice == "5":
            days = Prompt.ask("Archive tasks older than X days (0 for all)", default="0")
            try:
                archive(int(days))
            except ValueError:
                console.print("[red]Invalid number[/red]")
        elif choice == "6":
            # List tasks first
            list()
            task_ref = Prompt.ask("Enter Task Index or ID to mark done")
            complete(task_ref)
        elif choice == "7":
            # List tasks first
            list()
            task_ref = Prompt.ask("Enter Task Index or ID to delete")
            delete(task_ref)
        elif choice == "8":
            console.print("[bold blue]Goodbye![/bold blue]")
            break

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Default to interactive mode if no arguments provided
        sys.argv.append("interactive")
    app()
