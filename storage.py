import json
import os
from typing import List, Dict, Tuple
from models import Task, Project, TaskStatus

DATA_DIR = "data"
TASKS_FILE = os.path.join(DATA_DIR, "tasks.json")
ARCHIVE_FILE = os.path.join(DATA_DIR, "archive.json")

def _ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def _load_json(filepath: str) -> Dict:
    if not os.path.exists(filepath):
        return {"tasks": [], "projects": []}
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {"tasks": [], "projects": []}

def _save_json(filepath: str, data: Dict):
    _ensure_data_dir()
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=4)

def load_data() -> Tuple[List[Task], List[Project]]:
    data = _load_json(TASKS_FILE)
    tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
    projects = [Project.from_dict(p) for p in data.get("projects", [])]
    return tasks, projects

def save_data(tasks: List[Task], projects: List[Project]):
    data = {
        "tasks": [t.to_dict() for t in tasks],
        "projects": [p.to_dict() for p in projects]
    }
    _save_json(TASKS_FILE, data)

def load_archive() -> Tuple[List[Task], List[Project]]:
    data = _load_json(ARCHIVE_FILE)
    tasks = [Task.from_dict(t) for t in data.get("tasks", [])]
    projects = [Project.from_dict(p) for p in data.get("projects", [])]
    return tasks, projects

def save_archive(tasks: List[Task], projects: List[Project]):
    # When saving archive, we might want to append or overwrite. 
    # For simplicity, we'll load, append/merge, and save.
    # But usually, the caller will handle the merging logic.
    # Here we just save what is passed.
    data = {
        "tasks": [t.to_dict() for t in tasks],
        "projects": [p.to_dict() for p in projects]
    }
    _save_json(ARCHIVE_FILE, data)

def append_to_archive(tasks_to_archive: List[Task]):
    archived_tasks, archived_projects = load_archive()
    archived_tasks.extend(tasks_to_archive)
    # We might want to also archive projects if they are no longer used in active tasks,
    # but for now let's just keep projects in active list or duplicate them if needed.
    # A simple approach: just archive tasks.
    save_archive(archived_tasks, archived_projects)
