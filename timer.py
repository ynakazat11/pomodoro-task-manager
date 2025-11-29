import time
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn
from rich.console import Console
from rich.layout import Layout
from rich.align import Align
from rich.text import Text
from datetime import timedelta

console = Console()

def run_timer(minutes: int = 25, task_title: str = "Focus Time"):
    """
    Runs a visual timer for the specified duration.
    """
    seconds = minutes * 60
    
    # Create a progress bar
    progress = Progress(
        SpinnerColumn(),
        "[progress.description]{task.description}",
        BarColumn(),
        "[progress.percentage]{task.percentage:>3.0f}%",
        TextColumn("{task.fields[time_remaining]}"),
    )
    
    task_id = progress.add_task(f"[bold cyan]{task_title}", total=seconds, time_remaining=str(timedelta(seconds=seconds)))
    
    console.print("[dim]Press Ctrl+C to stop timer[/dim]")
    
    with Live(Panel(progress, title="Pomodoro Timer", border_style="green"), refresh_per_second=4) as live:
        while not progress.finished:
            time.sleep(1)
            progress.advance(task_id, 1)
            remaining = seconds - progress.tasks[0].completed
            progress.update(task_id, time_remaining=str(timedelta(seconds=int(remaining))))
            
    console.print(f"[bold green]Time's up! {minutes} minutes completed.[/bold green]")
    # Play a sound? (Optional, might be annoying or platform specific. Skip for now)
