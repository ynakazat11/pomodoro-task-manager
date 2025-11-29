import os
import json
import google.generativeai as genai
from typing import List, Tuple
from dotenv import load_dotenv
from models import Task, Project, TaskStatus

load_dotenv()

API_KEY = os.getenv("GEMINI_API_KEY")
if not API_KEY:
    # We might want to raise an error or handle this gracefully in main.py
    pass
else:
    genai.configure(api_key=API_KEY)

def process_brain_dump(text: str) -> Tuple[List[Task], List[Project]]:
    """
    Takes a raw brain dump text and uses Gemini to parse it into tasks and projects.
    """
    if not API_KEY:
        raise ValueError("GEMINI_API_KEY not found in environment variables.")

    model = genai.GenerativeModel('gemini-2.0-flash-exp')

    prompt = f"""
    You are an expert task manager and productivity coach.
    I will give you a "brain dump" of tasks and ideas.
    Your goal is to:
    1. Analyze the text and identify distinct tasks.
    2. Group related tasks into "Projects" (or Themes).
    3. Estimate the number of "Tomatoes" (25-minute work slots) for each task. Be realistic. 
       If a task is too big (more than 4 tomatoes), break it down into smaller subtasks.
    4. Return the result strictly as a JSON object with the following structure:
    {{
        "projects": [
            {{
                "name": "Project Name",
                "description": "Brief description of the project goal"
            }}
        ],
        "tasks": [
            {{
                "title": "Task Title",
                "description": "Actionable description",
                "estimated_tomatoes": <int>,
                "project_name": "Project Name" (must match one of the projects above)
            }}
        ]
    }}

    Here is the brain dump:
    "{text}"
    
    Return ONLY valid JSON. Do not include markdown formatting like ```json ... ```.
    """

    try:
        response = model.generate_content(prompt)
        response_text = response.text.strip()
        
        # Clean up potential markdown formatting if Gemini adds it despite instructions
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]
            
        data = json.loads(response_text)
        
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
            # For now, let's assume Gemini follows instructions. 
            # If not, we could create a "Misc" project.
            
            task = Task(
                title=t_data["title"],
                description=t_data.get("description", ""),
                estimated_tomatoes=int(t_data.get("estimated_tomatoes", 1)),
                project_id=project_id
            )
            tasks.append(task)
            
        return tasks, projects

    except Exception as e:
        # In a real app, we'd want better error handling
        print(f"Error calling Gemini: {e}")
        raise e
