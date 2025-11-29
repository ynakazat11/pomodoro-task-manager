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

app = typer.Typer()
console = Console()

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
        table.add_column("Title", style="cyan")
        table.add_column("Tomatoes", style="magenta")
        table.add_column("Project", style="green")
        
        project_map = {p.id: p.name for p in final_projects}
        
        for t in new_tasks:
            p_name = project_map.get(t.project_id, "Unknown")
            table.add_row(t.title, str(t.estimated_tomatoes), p_name)
            
        console.print(table)

    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")

@app.command()
def list():
    """
    List all pending tasks.
    """
    tasks, projects = storage.load_data()
    project_map = {p.id: p.name for p in projects}
    
    table = Table(title="Pending Tasks")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Tomatoes", style="magenta")
    table.add_column("Status", style="yellow")
    table.add_column("Project", style="green")
    
    # Sort by project maybe?
    for t in tasks:
        if t.status != TaskStatus.ARCHIVED:
            p_name = project_map.get(t.project_id, "No Project")
            status_color = "green" if t.status == TaskStatus.DONE else "yellow"
            table.add_row(t.id[:8], t.title, f"{t.completed_tomatoes}/{t.estimated_tomatoes}", f"[{status_color}]{t.status.value}[/{status_color}]", p_name)
            
    console.print(table)

@app.command()
def start(task_id_prefix: str):
    """
    Start a Pomodoro timer for a specific task.
    """
    tasks, projects = storage.load_data()
    
    # Find task by ID prefix
    target_task = None
    for t in tasks:
        if t.id.startswith(task_id_prefix):
            target_task = t
            break
            
    if not target_task:
        console.print(f"[bold red]Task with ID prefix '{task_id_prefix}' not found.[/bold red]")
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

if __name__ == "__main__":
    app()
