from colorama import Fore, Style, init

init(autoreset=True)


def explain_scheduling_with_cron():
    print(
        Fore.MAGENTA
        + "\n# Unveiling the secrets of automated scheduling in Termux with Cron and termux-job-scheduler...\n"
        + Style.RESET_ALL,
    )

    print(
        Fore.CYAN
        + "## The Ancient Art of Cron (for regular, time-based tasks)"
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  Cron is a time-based job scheduler in Unix-like operating systems. In Termux, you can use it"
        "  to run scripts automatically at specified intervals." + Style.RESET_ALL,
    )
    print(Fore.YELLOW + "  ### Step 1: Install `cron` in Termux:" + Style.RESET_ALL)
    print(Fore.GREEN + "  pkg install cron -y" + Style.RESET_ALL)
    print(Fore.YELLOW + "  ### Step 2: Start the `crond` service:" + Style.RESET_ALL)
    print(Fore.GREEN + "  crond" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  (You might want to add `crond` to your `~/.bashrc` or `~/.zshrc` to start it automatically on Termux launch.)"
        + Style.RESET_ALL,
    )
    print(
        Fore.YELLOW + "  ### Step 3: Edit your crontab (cron table):" + Style.RESET_ALL,
    )
    print(Fore.GREEN + "  crontab -e" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  This will open a text editor (usually `vi` or `nano`)."
        + Style.RESET_ALL,
    )
    print(Fore.YELLOW + "  ### Step 4: Add your cron job entry." + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  A cron job entry has 5 time fields (minute, hour, day of month, month, day of week) followed by the command."
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  To run a Python script every hour, you would add a line like this:"
        + Style.RESET_ALL,
    )
    print(
        Fore.GREEN
        + "  0 * * * * python /data/data/com.termux/files/home/bybit2/your_script_name.py >> /data/data/com.termux/files/home/bybit2/cron_log.log 2>&1"
        + Style.RESET_ALL,
    )
    print(Fore.WHITE + "  Explanation:" + Style.RESET_ALL)
    print(Fore.WHITE + "  - `0`: At minute 0 (the top of the hour)." + Style.RESET_ALL)
    print(Fore.WHITE + "  - `*`: Every hour." + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  - `* * *`: Every day of the month, every month, every day of the week."
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  - `python /data/data/com.termux/files/home/bybit2/your_script_name.py`: The command to execute."
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  - `>> /data/data/com.termux/files/home/bybit2/cron_log.log 2>&1`: Redirects all output (stdout and stderr) to a log file."
        + Style.RESET_ALL,
    )
    print(Fore.WHITE + "  Save and exit the editor." + Style.RESET_ALL)
    print(Fore.YELLOW + "  ### Step 5: Verify your cron jobs:" + Style.RESET_ALL)
    print(Fore.GREEN + "  crontab -l" + Style.RESET_ALL)

    print(
        Fore.CYAN
        + "\n## The Modern Enchantment of termux-job-scheduler (for event-based or more flexible tasks)"
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  `termux-job-scheduler` is a Termux-specific tool that allows scheduling jobs based on various triggers,"
        "  including network state, power state, or simply at a regular interval, even when Termux is not actively running in the foreground."
        + Style.RESET_ALL,
    )
    print(
        Fore.YELLOW
        + "  ### Step 1: Ensure `termux-api` is installed:"
        + Style.RESET_ALL,
    )
    print(Fore.GREEN + "  pkg install termux-api -y" + Style.RESET_ALL)
    print(Fore.YELLOW + "  ### Step 2: Register a job:" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  To run a script every hour, you can use the `--period-hourly` flag:"
        + Style.RESET_ALL,
    )
    print(
        Fore.GREEN
        + '  termux-job-scheduler --period-hourly --command "python /data/data/com.termux/files/home/bybit2/your_script_name.py" --tag my_hourly_bybit_script --mount-storage yes'
        + Style.RESET_ALL,
    )
    print(Fore.WHITE + "  Explanation:" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  - `--period-hourly`: Runs the command approximately once every hour."
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE + '  - `--command "..."`: The command to execute.' + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  - `--tag my_hourly_bybit_script`: A unique tag to identify your job."
        + Style.RESET_ALL,
    )
    print(
        Fore.WHITE
        + "  - `--mount-storage yes`: Ensures storage is mounted if your script needs to access files outside Termux's home directory."
        + Style.RESET_ALL,
    )
    print(Fore.YELLOW + "  ### Step 3: List registered jobs:" + Style.RESET_ALL)
    print(Fore.GREEN + "  termux-job-scheduler -l" + Style.RESET_ALL)
    print(Fore.YELLOW + "  ### Step 4: Remove a job:" + Style.RESET_ALL)
    print(
        Fore.GREEN
        + "  termux-job-scheduler -c --tag my_hourly_bybit_script"
        + Style.RESET_ALL,
    )

    print(Fore.CYAN + "\n## Pyrmethus's Recommendation:" + Style.RESET_ALL)
    print(
        Fore.WHITE
        + "  For simple, regular time-based tasks, "
        + Fore.YELLOW
        + "Cron"
        + Fore.WHITE
        + " is straightforward and effective. "
        "  However, for tasks that need to run reliably in the background, even when Termux is not in the foreground, "
        + Fore.YELLOW
        + "`termux-job-scheduler`"
        + Fore.WHITE
        + " is generally more robust and battery-friendly on Android."
        + Style.RESET_ALL,
    )
    print(
        Fore.MAGENTA
        + "\n# The scheduling incantations are now known to you!\n"
        + Style.RESET_ALL,
    )


if __name__ == "__main__":
    explain_scheduling_with_cron()
