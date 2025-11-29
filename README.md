# Pomodoro Task Manager

A simple CLI-based task manager that uses the Pomodoro technique and Google Gemini to organize your day.

## Features

- **Ingest**: Takes a raw "brain dump" of your tasks and uses Gemini to break them down and estimate effort.
- **Process**: Automatically creates projects and estimates "Tomatoes" (25-minute slots).
- **Execute**: Visual timer for running Pomodoro sessions.
- **Progress**: View statistics on completed vs. estimated tomatoes.
- **Archive**: Archive completed tasks to keep your list clean.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    Create a `.env` file in the project root and add your Gemini API key:
    ```
    GEMINI_API_KEY=your_api_key_here
    ```

## Usage

### 1. Ingest Tasks
Dump your thoughts into the system. Gemini will parse them.
```bash
python main.py ingest "I need to finish the quarterly report, call mom, and buy groceries for dinner."
```

### 2. List Tasks
See what's on your plate.
```bash
python main.py list
```

### 3. Start a Task
Pick a task by its ID (or the first few characters of the ID).
```bash
python main.py start <task_id_prefix>
```
Example: `python main.py start t1`

The timer will run for 25 minutes. When finished, it will ask if you completed the task.

### 4. Check Progress
See how many tomatoes you've crushed.
```bash
python main.py stats
```

### 5. Archive
Move completed tasks to the archive.
```bash
python main.py archive
```
To archive tasks completed more than 90 days ago:
```bash
python main.py archive --days 90
```
