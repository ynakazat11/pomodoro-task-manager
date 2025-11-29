import sys
from unittest.mock import MagicMock, patch
import main
from models import Task, TaskStatus, Project

# Mock data
mock_task = Task(
    id="t1", 
    title="Test Task", 
    estimated_tomatoes=1, 
    completed_tomatoes=0, 
    status=TaskStatus.TODO, 
    project_id="p1",
    created_at="2023-01-01"
)
mock_project = Project(id="p1", name="Test Project", description="Test", created_at="2023-01-01")

# Mock storage
main.storage.load_data = MagicMock(return_value=([mock_task], [mock_project]))
main.storage.save_data = MagicMock()

# Mock timer to raise KeyboardInterrupt
main.timer.run_timer = MagicMock(side_effect=KeyboardInterrupt)

# Mock typer.confirm to return True (User says Yes, I finished)
main.typer.confirm = MagicMock(return_value=True)

# Mock console to avoid clutter
main.console = MagicMock()

def test_interruption():
    print("Running test_interruption...")
    try:
        main.start("t1")
    except SystemExit:
        pass
    
    # Verify save_data was called
    main.storage.save_data.assert_called()
    
    # Verify task status is DONE
    if mock_task.status == TaskStatus.DONE:
        print("SUCCESS: Task marked as DONE after interruption.")
    else:
        print(f"FAILURE: Task status is {mock_task.status}")

if __name__ == "__main__":
    test_interruption()
