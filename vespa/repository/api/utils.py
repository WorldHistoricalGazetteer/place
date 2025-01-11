# /utils.py
import time
import uuid
from typing import Dict, Any
from urllib.parse import urlparse


class TaskTracker:
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def add_task(self, task_id: str, updates=None):
        self.tasks[task_id] = {
            "status": "in_progress",
            "transformed": 0,
            "processed": 0,
            "success": 0,
            "failure": 0,
            "start_time": time.time()
        }
        if updates:
            self.update_task(task_id, updates)
        self._cleanup()

    def update_task(self, task_id, updates):
        if task_id in self.tasks:
            for key, value in updates.items():
                if isinstance(value, int) and key in {"transformed", "processed", "success", "failure"}:
                    self.tasks[task_id][key] += value
                else:
                    self.tasks[task_id][key] = value
                    if key == "end_time":
                        duration = updates["end_time"] - self.tasks[task_id]["start_time"]
                        self.tasks[task_id]["duration"] = f"{int(duration // 60)}m {int(duration % 60)}s"

    def _cleanup(self, max_age: int = 86400):  # Default 24 hours in seconds
        current_time = time.time()
        expired_tasks = [
            task_id for task_id, task_info in self.tasks.items()
            if current_time - task_info["timestamp"] > max_age
        ]
        for task_id in expired_tasks:
            del self.tasks[task_id]

    def get_info(self, task_id: str):
        return self.tasks.get(task_id, {"status": "not found"})


# Global task tracker instance
task_tracker = TaskTracker()


def is_valid_url(url: str) -> bool:
    """
    Check if the provided URL has a valid format.
    """
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme) and bool(parsed_url.netloc)


def get_uuid() -> str:
    """
    Generate a unique identifier.
    """
    return str(uuid.uuid4())
