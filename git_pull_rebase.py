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

def git_pull_rebase():
    """Pulls changes from the remote and rebases the current branch."""
    print("Attempting to pull and rebase current branch...")
    try:
        output = run_git_command(["git", "pull", "--rebase"])
        print("Git pull --rebase successful:")
        print(output)
    except Exception as e:
        print(f"Git pull --rebase failed: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    git_pull_rebase()
