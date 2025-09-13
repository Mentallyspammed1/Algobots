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

def git_clean_branches():
    """Deletes local branches that have been merged into the current branch."""
    print("Cleaning up merged local branches...")
    try:
        # Fetch latest remote branches to ensure accurate merge status
        run_git_command(["git", "fetch", "--prune"])

        # Get a list of merged branches (excluding current branch and main/master)
        merged_branches = run_git_command(["git", "branch", "--merged"])
        current_branch = run_git_command(["git", "rev-parse", "--abbrev-ref", "HEAD"])

        branches_to_delete = []
        for branch in merged_branches.splitlines():
            branch = branch.strip()
            if branch and branch != current_branch and branch != "main" and branch != "master":
                branches_to_delete.append(branch)

        if not branches_to_delete:
            print("No merged branches to delete.")
            return

        print(f"Branches to delete: {', '.join(branches_to_delete)}")
        for branch in branches_to_delete:
            print(f"Deleting branch: {branch}")
            run_git_command(["git", "branch", "-d", branch])
        print("Merged branches cleaned up successfully.")

    except Exception as e:
        print(f"Failed to clean branches: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    git_clean_branches()
