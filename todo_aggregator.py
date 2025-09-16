import os
import re
from datetime import datetime

# --- Configuration ---
PROJECT_ROOT = '/data/data/com.termux/files/home/Algobots'
TODO_FILE = os.path.join(PROJECT_ROOT, 'TODO.md')

# Directories to exclude from the search
EXCLUDE_DIRS = [
    '.git', '__pycache__', '.vscode', 'node_modules', 'bot_data', 'bot_logs',
    '.idx', '.pytest_cache', '.snapshots', 'logs'
]

# File extensions to include in the search
INCLUDE_EXTS = [
    '.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.sh', '.json', '.yaml', '.yml',
    '.txt', '.html', '.css', '.java', '.c', '.cpp', '.h', '.hpp', '.go', '.rs'
]

# Regular expression to find TODO comments (case-insensitive)
# Captures '# TODO:', '// TODO:', '/* TODO:', '* TODO:' and variations, but excludes the pattern definition itself.
TODO_PATTERN = re.compile(
    r'(?i)(?:(?:#|//|/\*|\*)\s*TODO[:\s].*)'
)

# --- Helper Functions ---

def find_todos_in_file(filepath):
    """
    Reads a file and finds all TODO comments.
    Returns a list of (line_number, todo_text) tuples.
    """
    todos = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                match = TODO_PATTERN.search(line)
                if match:
                    todos.append((i + 1, match.group(0).strip()))
    except UnicodeDecodeError:
        print(f"Warning: Could not decode file {filepath} with UTF-8. Skipping.")
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
    return todos

def read_existing_todos(filepath):
    """
    Reads the existing TODO.md file and returns a set of unique TODO lines
    to prevent duplicates.
    """
    existing_todos = set()
    if os.path.exists(filepath):
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                # We only care about the actual TODO text for deduplication
                if "- [ ]" in line:
                    existing_todos.add(line.strip())
    return existing_todos

def update_todo_file(filepath, new_todos_data, existing_todos):
    """
    Appends new, unique TODOs to the TODO.md file.
    new_todos_data is a list of (filepath, line_number, todo_text) tuples.
    """
    unique_new_todos = []
    for file_path, line_num, todo_text in new_todos_data:
        formatted_todo = f"- [ ] **[{os.path.relpath(file_path, PROJECT_ROOT)}:{line_num}]** - {todo_text}"
        if formatted_todo not in existing_todos:
            unique_new_todos.append(formatted_todo)

    if unique_new_todos:
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(f"\n## Discovered Tasks ({datetime.now().strftime('%Y-%m-%d')})\n")
            for todo in unique_new_todos:
                f.write(f"{todo}\n")
        print(f"Added {len(unique_new_todos)} new TODOs to {filepath}")
    else:
        print("No new TODOs found to add.")
    return len(unique_new_todos)

# --- Main Execution ---
def main():
    all_found_todos = []
    print(f"Scanning for TODOs in {PROJECT_ROOT}...")

    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Modify dirs in-place to skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]

        for file in files:
            if file == os.path.basename(TODO_FILE):  # Skip the TODO.md file itself
                continue
            if any(file.endswith(ext) for ext in INCLUDE_EXTS):
                filepath = os.path.join(root, file)
                todos_in_file = find_todos_in_file(filepath)
                for line_num, todo_text in todos_in_file:
                    all_found_todos.append((filepath, line_num, todo_text))

    print(f"Found a total of {len(all_found_todos)} TODOs across the project.")

    existing_todos = read_existing_todos(TODO_FILE)
    newly_added_count = update_todo_file(TODO_FILE, all_found_todos, existing_todos)

    print(f"Process complete. {newly_added_count} unique TODOs were added to {TODO_FILE}.")

if __name__ == "__main__":
    main()
