# /utils.py
import asyncio
import time
import uuid
from typing import Dict, Any
from urllib.parse import urlparse


class TaskTracker:
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}

    def add_task(self, task_id: str, task_info=None):
        if task_info is None:
            task_info = {}
        self.tasks[task_id] = {
            "task_id": task_id,
            "task": {"status": "in progress", **task_info},
            "timestamp": time.time()
        }
        self._cleanup()

    def _cleanup(self, max_age: int = 86400):  # Default 24 hours in seconds
        current_time = time.time()
        expired_tasks = [
            task_id for task_id, task_info in self.tasks.items()
            if current_time - task_info["timestamp"] > max_age
        ]

        for task_id in expired_tasks:
            del self.tasks[task_id]

    def get(self, task_id: str):
        return self.tasks.get(task_id)


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
