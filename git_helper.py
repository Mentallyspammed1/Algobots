import subprocess
import sys

def run_git_command(command: list[str]) -> str:
    """Runs a git command and returns its output."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing git command: {' '.join(command)}", file=sys.stderr)
        print(f"Stdout: {e.stdout}", file=sys.stderr)
        print(f"Stderr: {e.stderr}", file=sys.stderr)
        sys.exit(1)

def create_and_push_tag(version: str, message: str):
    """Creates an annotated tag and pushes it to the remote."""
    print(f"Creating tag {version}...")
    run_git_command(["git", "tag", "-a", version, "-m", message])
    print(f"Pushing tag {version} to remote...")
    run_git_command(["git", "push", "origin", version])
    print(f"Tag {version} created and pushed successfully.")

def get_git_status():
    """Returns the current git status."""
    print("Fetching git status...")
    status = run_git_command(["git", "status"])
    print(status)
    return status

def get_latest_tag():
    """Returns the latest git tag."""
    print("Fetching latest git tag...")
    try:
        latest_tag = run_git_command(["git", "describe", "--tags", "--abbrev=0"])
        print(f"Latest tag: {latest_tag}")
        return latest_tag
    except Exception:
        print("No tags found in the repository.")
        return None

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python git_helper.py <command> [args]", file=sys.stderr)
        print("Commands: tag <version> <message>, status, latest_tag", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]
    if command == "tag":
        if len(sys.argv) < 4:
            print("Usage: python git_helper.py tag <version> <message>", file=sys.stderr)
            sys.exit(1)
        version = sys.argv[2]
        message = sys.argv[3]
        create_and_push_tag(version, message)
    elif command == "status":
        get_git_status()
    elif command == "latest_tag":
        get_latest_tag()
    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)
