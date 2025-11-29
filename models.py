import uuid
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    ARCHIVED = "archived"

@dataclass
class Project:
    name: str
    description: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class Task:
    title: str
    description: str = ""
    estimated_tomatoes: int = 1
    completed_tomatoes: int = 0
    status: TaskStatus = TaskStatus.TODO
    project_id: Optional[str] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    completed_at: Optional[str] = None

    def to_dict(self):
        data = asdict(self)
        data['status'] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data):
        if 'status' in data:
            data['status'] = TaskStatus(data['status'])
        return cls(**data)
