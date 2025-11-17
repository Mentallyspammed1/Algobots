"""
This module provides functions for displaying various indicators and progress notifications.
It includes functions for simple text-based progress bars, spinners, and status messages.
"""

import sys
import time


def display_status(message: str, clear_lines: int = 0) -> None:
    """
    Displays a status message to the console.

    Args:
        message: The message to display.
        clear_lines: The number of preceding lines to clear before displaying the message.
                     This is useful for overwriting previous status updates.
    """
    if clear_lines > 0:
        # Move cursor up and clear lines
        sys.stdout.write(f"\033[{clear_lines}A")
        sys.stdout.write("\033[J")  # Clear entire screen from cursor down

    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def display_progress_bar(
    iteration: int, total: int, prefix: str = "", suffix: str = "", length: int = 50, fill: str = "#"
) -> None:
    """
    Displays a text-based progress bar.

    Args:
        iteration: Current iteration (completed). 
        total: Total iterations.
        prefix: String to display before the progress bar.
        suffix: String to display after the progress bar.
        length: Character length of the bar itself.
        fill: Character to use for the filled part of the bar.
    """
    percent = ("{0:.1f}").format(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + "-" * (length - filled_length)

    # Use carriage return to overwrite the line
    sys.stdout.write(f"\r{prefix} |{bar}| {percent}% {suffix}")
    sys.stdout.flush()


def display_spinner(message: str, delay: float = 0.1) -> None:
    """
    Displays a simple command-line spinner animation.

    Args:
        message: The message to display alongside the spinner.
        delay: The delay between spinner frames in seconds.
    """
    spinner_chars = ["|", "/", "-", "\"]
    for i in range(20):  # Display for a limited number of frames
        frame = spinner_chars[i % len(spinner_chars)]
        sys.stdout.write(f"\r{frame} {message}")
        sys.stdout.flush()
        time.sleep(delay)
    # Clear the spinner line after completion
    sys.stdout.write("\r" + " " * (len(message) + 2) + "\r")
    sys.stdout.flush()

if __name__ == "__main__":
    # Example Usage:
    total_items = 100

    display_status("Starting process...")
    time.sleep(1)

    for i in range(total_items + 1):
        # Simulate work
        time.sleep(0.05)
        display_progress_bar(i, total_items, prefix="Progress:", suffix="Complete", length=50)

    display_status("Process finished successfully!", clear_lines=1) # Clear the progress bar line

    display_status("Performing a task with a spinner...")
    display_spinner("Processing data...")
    display_status("Spinner task completed.")

    display_status("Demonstrating status clearing", clear_lines=1)
    display_status("First message.", clear_lines=0)
    time.sleep(1)
    display_status("Second message, overwriting the first.", clear_lines=1)
    time.sleep(1)
    display_status("Third message, overwriting the second.", clear_lines=1)

    display_status("All indicators demonstrated.")
