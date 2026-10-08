"""
Utility functions.
"""

import json
import os


def save_json(path: str, data: dict):
    """Save data as JSON file."""
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_json(path: str) -> dict:
    """Load JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def print_banner():
    print("""
+------------------------------------------------------------+
|             STEM AGENT -- JetBrains Internship             |
|             JavaScript Code Generation Specialist          |
|             Author: Marko Spasojevic                       |
+------------------------------------------------------------+
    """)
