# /utils.py
import re
import time
import uuid
from typing import Dict, Any
from urllib.parse import urlparse


class TaskTracker:
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
        self.error_limit = 100

    def add_task(self, task_id: str, updates=None):
        self.tasks[task_id] = {
            "status": "in_progress",
            "transformed": 0,
            "processed": 0,
            "toponyms_staged": 0,
            "toponyms_unstaged": 0,
            "success": 0,
            "failure": 0,
            "errors": [],
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
                elif key == "error":
                    errors = self.tasks[task_id].setdefault("errors", [])
                    if len(errors) < self.error_limit:
                        errors.append(value)
                else:
                    self.tasks[task_id][key] = value
                    if key == "end_time":
                        duration = updates["end_time"] - self.tasks[task_id]["start_time"]
                        self.tasks[task_id]["duration"] = f"{int(duration // 60)}m {int(duration % 60)}s"

    def _cleanup(self, max_age: int = 86400):  # Default 24 hours in seconds
        current_time = time.time()
        expired_tasks = [
            task_id for task_id, task_info in self.tasks.items()
            if current_time - task_info.get("start_time", current_time) > max_age
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


def escape_match_yql(text: str) -> str:
    """
    Quote " and backslash \ characters in text values must be escaped by a backslash
    See: https://docs.vespa.ai/en/reference/query-language-reference.html
    """
    # return re.sub(r'[\\^$|()"]', r"\\\g<0>", text)  # NOT: {}[].*+?
    subtext = re.sub(r'[\\"]', r"\\\g<0>", text)
    return re.sub(r'[*]', r"\\\\\g<0>", subtext)


def escape_yql(text: str) -> str:
    """
    Quote " and backslash \ characters in text values must be escaped by a backslash
    See: https://docs.vespa.ai/en/reference/query-language-reference.html
    """
    return re.sub(r'[\\"]', r"\\\g<0>", text)


def debracket(text):
    """
    Removes round brackets and their contents from a string,
    including nested brackets, using recursion.
    Also trims the final string, reduces double spaces to single,
    and removes spaces before periods.
    """
    subtext = re.sub(r"\([^()]*\)", "", text)
    if subtext != text:
        return debracket(subtext)
    # Remove extra spaces
    subtext = ' '.join(subtext.split())
    # Remove spaces before periods
    subtext = re.sub(r'\s+\.', '.', subtext)
    # Remove any erroneous isolated brackets, for example:
    # "(पुरूषपुर" https://pleiades.stoa.org/places/569531631/name.2018-07-24.9890884070
    return re.sub(r'[()]', '', subtext)


def existing_document(query_response_root):
    if query_response_root.get("fields", {}).get("totalCount", 0) == 0:
        return None
    document = query_response_root.get("children", [{}])[0].get("fields", {})
    return {
        'document_id': document.get("documentid").split("::")[-1],
        'fields': document,
    }

def distinct_dicts(existing_dicts, new_dicts):
    """
    Deduplicates two lists of dictionaries based on all fields.

    Args:
        existing_dicts (list or dict): List of existing dictionaries or a single dictionary.
        new_dicts (list or dict): List of new dictionaries or a single dictionary to be merged.

    Returns:
        list: A list of unique dictionaries, with duplicates removed based on all fields.
    """
    # Ensure both inputs are lists (wrap single dicts as lists)
    if isinstance(existing_dicts, dict):
        existing_dicts = [existing_dicts]
    if isinstance(new_dicts, dict):
        new_dicts = [new_dicts]

    # Ensure both inputs are lists now
    if not isinstance(existing_dicts, list) or not isinstance(new_dicts, list):
        raise ValueError("Both existing_dicts and new_dicts must be lists or single dictionaries.")

    # Combine the existing and new dictionaries
    combined_dicts = existing_dicts + new_dicts

    # Set to track unique dictionaries (converted to frozensets for hashing)
    seen = set()
    unique_dicts = []

    for dictionary in combined_dicts:
        # Convert each dictionary to a frozenset of its items (making it hashable)
        dict_frozenset = frozenset(dictionary.items())

        # If the frozenset has not been seen, add to the result
        if dict_frozenset not in seen:
            unique_dicts.append(dictionary)
            seen.add(dict_frozenset)

    return unique_dicts

