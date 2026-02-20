import os
import json
import anthropic
from typing import List, Tuple
from dotenv import load_dotenv
from models import Task, Project, TaskStatus

load_dotenv()

# Load API key with fallback to manual parsing if dotenv truncates it
API_KEY = os.getenv("ANTHROPIC_API_KEY")
if API_KEY and len(API_KEY) < 100:
    # Fallback: manually parse .env file
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('ANTHROPIC_API_KEY='):
                    API_KEY = line.split('=', 1)[1].strip()
                    break

def process_brain_dump(text: str) -> Tuple[List[Task], List[Project]]:
    """
    Takes a raw brain dump text and uses Claude to parse it into tasks and projects.
    """
    if not API_KEY:
        raise ValueError("ANTHROPIC_API_KEY not found in environment variables.")

    client = anthropic.Anthropic(api_key=API_KEY)

    prompt = f"""You are a helpful project manager.
I will give you a "brain dump" of tasks.
Your job is to:
1. Break down the brain dump into individual, actionable tasks.
2. Estimate the effort for each task in "Tomatoes" (1 Tomato = 25 minutes).
3. Assign each task to a Project (Theme). If no project fits, create a new one or use "General".
4. Extract any deadlines mentioned (e.g., "by Friday", "tomorrow") and convert them to YYYY-MM-DD format. If no deadline, leave null.

Output valid JSON with the following structure:
{{
    "projects": [
        {{ "name": "Project Name", "description": "Optional description" }}
    ],
    "tasks": [
        {{ "title": "Task Title", "estimated_tomatoes": 1, "project_name": "Project Name", "deadline": "YYYY-MM-DD or null" }}
    ]
}}

Here is the brain dump:
"{text}"

Return ONLY valid JSON. Do not include markdown formatting like ```json ... ```."""

    try:
        message = client.messages.create(
            model=os.getenv("EVAL_MODEL_OVERRIDE", "claude-haiku-4-5-20251001"),
            max_tokens=4096,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        if _log := os.getenv("EVAL_TOKEN_LOG"):
            with open(_log, "a") as _f:
                _f.write(json.dumps({"input": message.usage.input_tokens, "output": message.usage.output_tokens, "model": os.getenv("EVAL_MODEL_OVERRIDE", "claude-haiku-4-5-20251001")}) + "\n")

        response_text = message.content[0].text.strip()

        # Extract JSON object robustly — model sometimes adds prose before/after
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON object found in response: {response_text!r}")
        data = json.loads(response_text[start:end])

        projects_map = {}
        projects = []
        tasks = []

        # Create Project objects
        for p_data in data.get("projects", []):
            project = Project(name=p_data["name"], description=p_data.get("description", ""))
            projects.append(project)
            projects_map[project.name] = project.id

        # Create Task objects
        for t_data in data.get("tasks", []):
            project_name = t_data.get("project_name")
            project_id = projects_map.get(project_name)

            # If project not found (edge case), maybe create a default one or leave None
            # For now, let's assume Claude follows instructions.
            # If not, we could create a "Misc" project.

            task = Task(
                title=t_data["title"],
                description=t_data.get("description", ""),
                estimated_tomatoes=int(t_data.get("estimated_tomatoes", 1)),
                project_id=project_id,
                deadline=t_data.get("deadline")
            )
            tasks.append(task)

        return tasks, projects

    except Exception as e:
        # In a real app, we'd want better error handling
        print(f"Error calling Claude: {e}")
        raise e
