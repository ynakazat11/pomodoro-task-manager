import os
from github import Github, Auth
from dotenv import load_dotenv
from typing import List, Tuple

load_dotenv()

def get_github_client():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        return None
    auth = Auth.Token(token)
    return Github(auth=auth)

def fetch_open_issues(repo_name: str, label: str = None) -> List[Tuple[int, str, str]]:
    """
    Fetches open issues from the specified repository.
    Returns a list of tuples: (issue_number, title, body).
    """
    g = get_github_client()
    if not g:
        raise ValueError("GITHUB_TOKEN not found in environment variables.")
        
    try:
        repo = g.get_repo(repo_name)
        
        # Filter by label if provided, otherwise get all open issues
        if label:
            # Note: PyGithub expects labels as a list of objects or strings, 
            # but getting the label object first is safer if strict.
            # For simplicity, we can just filter manually or pass the string if supported.
            # get_issues(state='open', labels=[...])
            issues = repo.get_issues(state='open', labels=[label])
        else:
            issues = repo.get_issues(state='open')
            
        results = []
        for issue in issues:
            # Skip pull requests (PyGithub treats PRs as issues too)
            if issue.pull_request:
                continue
            results.append((issue.number, issue.title, issue.body or ""))
            
        return results
        
    except Exception as e:
        raise Exception(f"Failed to fetch issues from {repo_name}: {e}")

def close_issue(repo_name: str, issue_number: int):
    """
    Closes the specified issue.
    """
    g = get_github_client()
    if not g:
        raise ValueError("GITHUB_TOKEN not found.")
        
    try:
        repo = g.get_repo(repo_name)
        issue = repo.get_issue(issue_number)
        issue.edit(state='closed')
    except Exception as e:
        raise Exception(f"Failed to close issue #{issue_number}: {e}")
