# setup_enhanced.py
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Third-party library for YAML generation, needs to be installed if not present.
try:
    import yaml
except ImportError:
    print("PyYAML is not installed. Please install it using: pip install PyYAML")
    sys.exit(1)

# Import file content templates
from templates import (
    BYBIT_CLIENT_CONTENT,
    CONFIG_PY_CONTENT,
    ENV_CONTENT,
    GITIGNORE_CONTENT,
    INIT_CONTENT,
    MAIN_PY_CONTENT,
    MODELS_CONTENT,
    README_TEMPLATE,
    REQUIREMENTS_CONTENT,
    TECH_ANALYSIS_CONTENT,
    TERMUX_SMS_CONTENT,
)

# --- Configuration ---
PROJECT_NAME = "ai_trend_bot"
PYTHON_CMD = sys.executable or "python3" # Use sys.executable for better venv detection
VENV_DIR = "venv"
MIN_PYTHON_VERSION = (3, 9)

# --- Terminal Colors ---
class Colors:
    GREEN = "\033[0;32m"
    YELLOW = "\033[1;33m"
    BLUE = "\033[0;34m"
    RED = "\033[0;31m"
    CYAN = "\033[0;36m"
    MAGENTA = "\033[0;35m"
    NC = "\033[0m" # No Color

# --- Helper Functions ---
def print_step(text: str) -> None:
    print(f"{Colors.BLUE}---> {text}{Colors.NC}")

def print_success(text: str) -> None:
    print(f"{Colors.GREEN}✅ {text}{Colors.NC}")

def print_warning(text: str) -> None:
    print(f"{Colors.YELLOW}⚠️  {text}{Colors.NC}")

def print_error(text: str) -> None:
    print(f"{Colors.RED}❌ {text}{Colors.NC}")

def print_info(text: str) -> None:
    print(f"{Colors.CYAN}ℹ️  {text}{Colors.NC}")

def prompt_user_input(prompt: str, default: str | None = None) -> str:
    """Prompts user for input with an optional default value."""
    prompt_str = f"{Colors.CYAN}{prompt}{Colors.NC}"
    if default is not None:
        prompt_str += f" {Colors.YELLOW}[default: {default}]{Colors.NC}: "
    else:
        prompt_str += ": "

    user_input = input(prompt_str).strip()
    return user_input if user_input else default

class ProjectBuilder:
    """Handles the entire project setup process."""
    def __init__(self, name: str, venv_dir: str):
        self.project_name = name
        self.venv_dir = venv_dir
        self.config: dict[str, Any] = {}

    def run(self) -> None:
        """Executes the full setup workflow."""
        self._display_header()
        self._prompt_for_config()
        self._run_system_checks()
        self._setup_project_directory()
        self._create_directories()
        self._generate_files()
        self._setup_python_environment()
        self._validate_setup()
        self._print_final_instructions()

    def _display_header(self) -> None:
        """Prints the script's header."""
        clear_command = "cls" if os.name == "nt" else "clear"
        os.system(clear_command)
        print(f"{Colors.BLUE}╔════════════════════════════════════════════════════════════╗")
        print("║   🚀 AI Trend Bot v3.0 - Gemini 2.5 Flash Edition 🚀     ║")
        print("║          with Termux SMS Notifications                    ║")
        print(f"╚════════════════════════════════════════════════════════════╝{Colors.NC}\n")

    def _prompt_for_config(self) -> None:
        """Gathers all necessary configuration from the user."""
        print(f"{Colors.MAGENTA}═══════════════════════════════════════════════════════{Colors.NC}")
        print(f"{Colors.YELLOW}Interactive Setup - Customize Your Bot{Colors.NC}")
        print(f"{Colors.MAGENTA}═══════════════════════════════════════════════════════{Colors.NC}\n")

        self.config["symbols"] = prompt_user_input("Enter symbols (comma-separated)", "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT")

        print_info("Select primary timeframe:")
        print(f"  {Colors.CYAN}1){Colors.NC} 1 minute (1)")
        print(f"  {Colors.CYAN}2){Colors.NC} 5 minutes (5)")
        print(f"  {Colors.CYAN}3){Colors.NC} 15 minutes (15)")
        print(f"  {Colors.CYAN}4){Colors.NC} 1 hour (60) {Colors.GREEN}[Recommended]{Colors.NC}")
        print(f"  {Colors.CYAN}5){Colors.NC} 4 hours (240)")
        print(f"  {Colors.CYAN}6){Colors.NC} 1 day (D)")
        timeframe_map = {"1": "1", "2": "5", "3": "15", "4": "60", "5": "240", "6": "D"}
        choice = prompt_user_input("Select timeframe (1-6)", "4")
        self.config["primary_interval"] = timeframe_map.get(choice, "60")

        mtf_choice = prompt_user_input("Enable multi-timeframe analysis? (y/N)", "y")
        self.config["enable_mtf"] = mtf_choice.lower() == "y"

        self.config["confidence_threshold"] = int(prompt_user_input("Minimum confidence threshold (0-100)", "75"))

        sms_choice = prompt_user_input("Enable Termux SMS notifications? (y/N)", "n")
        self.config["enable_sms"] = sms_choice.lower() == "y"
        self.config["sms_phone"] = ""
        if self.config["enable_sms"]:
            self.config["sms_phone"] = prompt_user_input("Enter phone number for SMS alerts (+1234567890)")

        print("\n" + Colors.GREEN + "✅ Configuration completed!" + Colors.NC + "\n")

    def _run_system_checks(self) -> None:
        """Verifies that required tools (Python, pip, git) are installed."""
        print_step("Checking Python installation...")
        try:
            # Use sys.executable to ensure we're checking the Python running the script
            py_version_str = subprocess.check_output([sys.executable, "--version"], text=True).strip().split()[-1]
            py_version = tuple(map(int, py_version_str.split(".")[:2]))
            if py_version >= MIN_PYTHON_VERSION:
                print_success(f"Found Python {py_version_str}")
            else:
                raise RuntimeError(f"Python {'.'.join(map(str, MIN_PYTHON_VERSION))}+ is required. You are running {py_version_str}.")
        except (subprocess.CalledProcessError, FileNotFoundError, RuntimeError) as e:
            print_error(f"Python check failed: {e}")
            sys.exit(1)

        print_step("Checking for pip...")
        # Check for pip3 first, then pip
        pip_cmd = shutil.which("pip3") or shutil.which("pip")
        if not pip_cmd:
            print_error("pip is not installed. Please install it to continue (e.g., 'pkg install python-pip').")
            sys.exit(1)
        print_success(f"Found pip: {pip_cmd}")

        print_step("Checking for git...")
        self.git_available = shutil.which("git") is not None
        if self.git_available:
            print_success("Git detected")
        else:
            print_warning("Git not found - version control will be unavailable")

    def _setup_project_directory(self) -> None:
        """Handles creation of the main project directory, including backups."""
        project_path = Path(self.project_name)
        if project_path.exists():
            reply = prompt_user_input(f"Directory '{self.project_name}' already exists. Backup and recreate? (y/N)", "N")
            if reply.lower() == "y":
                backup_name = f"{self.project_name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                try:
                    shutil.move(self.project_name, backup_name)
                    print_success(f"Backed up existing directory to '{backup_name}'")
                except Exception as e:
                    print_error(f"Failed to backup existing directory: {e}")
                    sys.exit(1)
            else:
                print_error("Installation cancelled. Please remove the existing directory or choose to back it up.")
                sys.exit(1)

        print_step(f"Creating project directory: {self.project_name}")
        try:
            project_path.mkdir()
            os.chdir(self.project_name)
            print_success(f"Directory '{self.project_name}' created and entered.")
        except Exception as e:
            print_error(f"Failed to create project directory: {e}")
            sys.exit(1)

    def _create_directories(self) -> None:
        """Creates the internal project folder structure."""
        print_step("Creating project structure...")
        dirs_to_create = [
            "trend_analyzer/utils", "trend_analyzer/strategies",
            "trend_analyzer/indicators", "trend_analyzer/notifications",
            "logs", "data", "backups", "docs",
        ]
        try:
            for dir_path in dirs_to_create:
                Path(dir_path).mkdir(parents=True, exist_ok=True)
            print_success("Directory structure created.")
        except Exception as e:
            print_error(f"Failed to create directory structure: {e}")
            sys.exit(1)

    def _generate_files(self) -> None:
        """Generates all static and templated files for the project."""
        print_step("Generating project files...")

        # Helper to write files
        def write_file(filepath: str, content: str):
            try:
                path = Path(filepath)
                path.parent.mkdir(parents=True, exist_ok=True)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)
                # print(f"Created file: {filepath}") # Avoid excessive output during generation
            except Exception as e:
                print_error(f"Error writing file {filepath}: {e}")
                # Decide if this is fatal or if we can continue
                # For now, we'll just log and continue, validation will catch issues

        # Static files
        write_file(".gitignore", GITIGNORE_CONTENT)
        write_file("requirements.txt", REQUIREMENTS_CONTENT)
        write_file(".env", ENV_CONTENT)

        # Templated README
        readme_content = README_TEMPLATE.format(
            PROJECT_NAME=self.project_name,
            VENV_DIR=self.venv_dir,
        )
        write_file("README.md", readme_content)

        # Python package files (__init__.py)
        init_paths = [
            "trend_analyzer", "trend_analyzer/indicators", "trend_analyzer/strategies",
            "trend_analyzer/utils", "trend_analyzer/notifications",
        ]
        for path in init_paths:
            write_file(f"{path}/__init__.py", INIT_CONTENT)

        # Core Python files
        write_file("trend_analyzer/models.py", MODELS_CONTENT)
        write_file("trend_analyzer/config.py", CONFIG_PY_CONTENT)
        write_file("trend_analyzer/bybit_client.py", BYBIT_CLIENT_CONTENT)
        write_file("trend_analyzer/indicators/technical_analysis.py", TECH_ANALYSIS_CONTENT)
        write_file("trend_analyzer/notifications/termux_sms.py", TERMUX_SMS_CONTENT)
        write_file("trend_analyzer/main.py", MAIN_PY_CONTENT)

        # Dynamically generate config.yaml
        self._generate_yaml_config()

        # Initialize Git repository if git is available
        if self.git_available:
            try:
                subprocess.run(["git", "init"], check=True, capture_output=True)
                print_success("Git repository initialized.")
            except subprocess.CalledProcessError as e:
                print_error(f"Failed to initialize Git repository: {e.stderr.decode()}")
            except FileNotFoundError:
                print_error("Git command not found, cannot initialize repository.")

    def _generate_yaml_config(self) -> None:
        """Creates config.yaml from user settings."""
        symbols_list = [s.strip().upper() for s in self.config["symbols"].split(",")]

        yaml_config = {
            "api": {
                "bybit": {"base_url": "https://api.bybit.com", "use_testnet": False, "timeout": 30},
                "gemini": {"model_name": "gemini-2.5-flash-latest", "temperature": 0.3},
            },
            "analysis": {
                "symbols": symbols_list,
                "intervals": {
                    "primary": self.config["primary_interval"],
                    "secondary": "240", # Default secondary interval
                    "tertiary": "D",     # Default tertiary interval
                },
                "multi_timeframe": self.config["enable_mtf"],
                "category": "linear", # Default category for Bybit
                "kline_limit": 200,
                "min_confidence": self.config["confidence_threshold"],
            },
            "notifications": {
                "enabled": True, # Global notification flag
                "termux_sms": {
                    "enabled": self.config["enable_sms"],
                    "phone_number": self.config["sms_phone"],
                },
            },
            "logging": {
                "level": "INFO",
                "file_logging": True,
                "log_file": "logs/trend_bot.log",
            },
        }
        try:
            with open("config.yaml", "w", encoding="utf-8") as f:
                yaml.dump(yaml_config, f, default_flow_style=False, sort_keys=False)
            print_success("Created config.yaml with your custom settings")
        except Exception as e:
            print_error(f"Failed to write config.yaml: {e}")
            sys.exit(1)

    def _setup_python_environment(self) -> None:
        """Creates a virtual environment and installs dependencies."""
        print_step(f"Setting up Python virtual environment at './{self.venv_dir}'...")
        try:
            subprocess.run([PYTHON_CMD, "-m", "venv", self.venv_dir], check=True)
            print_success("Virtual environment created.")
        except subprocess.CalledProcessError as e:
            print_error(f"Failed to create virtual environment: {e}")
            sys.exit(1)
        except FileNotFoundError:
            print_error(f"Python command '{PYTHON_CMD}' not found. Ensure Python is installed and in your PATH.")
            sys.exit(1)

        # Determine the path to pip within the venv
        pip_executable = Path(self.venv_dir) / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
        if not pip_executable.exists():
            print_error(f"Could not find pip executable at {pip_executable}. Virtual environment setup might be incomplete.")
            sys.exit(1)

        print_step("Upgrading pip and installing dependencies...")
        try:
            # Upgrade pip first
            subprocess.run([str(pip_executable), "install", "--upgrade", "pip"], check=True, capture_output=True)

            # Install requirements
            result = subprocess.run([str(pip_executable), "install", "-r", "requirements.txt"], check=False, capture_output=True, text=True)

            if result.returncode != 0:
                print_error("Failed to install dependencies.")
                print(f"--- pip install output ---\n{result.stdout}\n--- pip install errors ---\n{result.stderr}")
                sys.exit(1)
            print_success("Dependencies installed successfully.")
        except FileNotFoundError:
            print_error(f"Pip executable not found at {pip_executable}. Cannot install dependencies.")
            sys.exit(1)
        except Exception as e:
            print_error(f"An error occurred during dependency installation: {e}")
            sys.exit(1)

    def _validate_setup(self) -> None:
        """Final check to ensure all key files and folders are in place."""
        print_step("Validating setup...")
        paths_to_check = [
            self.venv_dir,
            "config.yaml",
            ".env",
            "trend_analyzer/main.py",
            "requirements.txt",
            ".gitignore",
            "README.md",
        ]
        all_exist = True
        for p in paths_to_check:
            if not Path(p).exists():
                print_error(f"Missing file/directory: {p}")
                all_exist = False

        if all_exist:
            print_success("Setup validation passed.")
        else:
            print_error("Setup validation failed. Please check the errors above.")
            sys.exit(1)

    def _print_final_instructions(self) -> None:
        """Displays the final instructions and next steps for the user."""
        is_windows = sys.platform == "win32"
        activate_command = f"{self.venv_dir}\\Scripts\activate" if is_windows else f"source {self.venv_dir}/bin/activate"

        print(f"\n{Colors.GREEN}╔════════════════════════════════════════════════════════════╗")
        print("║              🎉 Setup Complete! 🎉                        ║")
        print(f"╚════════════════════════════════════════════════════════════╝{Colors.NC}")

        print(f"""
{Colors.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.NC}
{Colors.YELLOW}YOUR CUSTOM CONFIGURATION:{Colors.NC}
{Colors.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.NC}
  📊 Symbols: {Colors.GREEN}{self.config['symbols']}{Colors.NC}
  ⏰ Timeframe: {Colors.GREEN}{self.config['primary_interval']}{Colors.NC}
  🎯 Min Confidence: {Colors.GREEN}{self.config['confidence_threshold']}%{Colors.NC}
  📱 SMS Alerts: {Colors.GREEN}{'Enabled' if self.config['enable_sms'] else 'Disabled'}{Colors.NC}
{f'  📞 Phone: {Colors.GREEN}{self.config['sms_phone']}{Colors.NC}' if self.config['enable_sms'] else ''}

{Colors.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.NC}
{Colors.YELLOW}NEXT STEPS:{Colors.NC}
{Colors.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Colors.NC}
  {Colors.BLUE}1.{Colors.NC} Navigate to the project directory (you are already here).
     {Colors.GREEN}cd {self.project_name}{Colors.NC}

  {Colors.BLUE}2.{Colors.NC} Activate the Python virtual environment:
     {Colors.GREEN}{activate_command}{Colors.NC}

  {Colors.BLUE}3.{Colors.NC} {Colors.RED}CRITICAL:{Colors.NC} Edit the {Colors.YELLOW}.env{Colors.NC} file with your API keys:
     {Colors.GREEN}nano .env  # or your preferred text editor{Colors.NC}

  {Colors.BLUE}4.{Colors.NC} Run the bot:
     {Colors.GREEN}python -m trend_analyzer.main{Colors.NC}
{Colors.GREEN}
Happy Trading! 📈🚀{Colors.NC}
""")

if __name__ == "__main__":
    # Check if we are already inside the project directory
    if Path(PROJECT_NAME).exists() and Path("config.yaml").exists():
        print_error(f"It looks like you are already inside a '{PROJECT_NAME}' directory with a config.yaml.")
        print_info("This script should be run from the parent directory to create the project.")
        sys.exit(1)

    try:
        builder = ProjectBuilder(name=PROJECT_NAME, venv_dir=VENV_DIR)
        builder.run()
    except KeyboardInterrupt:
        print_error("\nSetup interrupted by user.")
        sys.exit(1)
    except Exception as e:
        print_error(f"\nAn unexpected error occurred during setup: {e}")
        # Optionally, print traceback for debugging
        # import traceback
        # traceback.print_exc()
        sys.exit(1)
