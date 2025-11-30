from unittest.mock import MagicMock, patch
import main
from models import Task, Project, TaskStatus

# Mock GitHub Client
main.github_client.fetch_open_issues = MagicMock(return_value=[
    (1, "GitHub Task 1", "Description from GitHub"),
    (2, "GitHub Task 2", "")
])
main.github_client.close_issue = MagicMock()

# Mock Environment
main.os.getenv = MagicMock(return_value="test/repo")

# Mock Ingest Logic (Return True = Saved)
main.ingest_logic = MagicMock(return_value=True)

# Mock Console
main.console = MagicMock()

def test_github_check():
    print("Testing GitHub check...")
    main.check_github()
    
    # Verify fetch called
    main.github_client.fetch_open_issues.assert_called_with("test/repo")
    
    # Verify ingest called with correct text
    expected_text = "- GitHub Task 1\n  Description from GitHub\n- GitHub Task 2"
    main.ingest_logic.assert_called_with(expected_text)
    
    # Verify issues closed
    main.github_client.close_issue.assert_any_call("test/repo", 1)
    main.github_client.close_issue.assert_any_call("test/repo", 2)
    
    print("GitHub check test passed!")

if __name__ == "__main__":
    test_github_check()
