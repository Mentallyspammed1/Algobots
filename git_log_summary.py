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


def git_log_summary(num_commits: int = 10):
    """Prints a summary of recent git commits."""
    print(f"Fetching summary of last {num_commits} commits...")
    try:
        output = run_git_command(
            ["git", "log", f"-n{num_commits}", "--pretty=format:%h - %an, %ar : %s"]
        )
        print("--- Git Log Summary ---")
        print(output)
        print("-----------------------")
    except Exception as e:
        print(f"Failed to get git log summary: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Get a summary of recent git commits.")
    parser.add_argument(
        "-n",
        "--num_commits",
        type=int,
        default=10,
        help="Number of commits to display.",
    )
    args = parser.parse_args()
    git_log_summary(args.num_commits)
