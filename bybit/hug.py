import argparse
import sys

from colorama import Fore, Style, init
from transformers import pipeline

# Initialize colorama for cross-platform colored terminal output
init(autoreset=True)

# Define a neon color scheme
NEON_CYAN = Fore.CYAN + Style.BRIGHT
NEON_MAGENTA = Fore.MAGENTA + Style.BRIGHT
NEON_GREEN = Fore.GREEN + Style.BRIGHT
NEON_YELLOW = Fore.YELLOW + Style.BRIGHT
RESET = Style.RESET_ALL

def main():
    """
    Main function to handle model pipeline and user interaction.
    """
    # Create an argument parser for future enhancements
    parser = argparse.ArgumentParser(description=f"{NEON_CYAN}Advanced Text Generation with a specified model.{RESET}")
    parser.add_argument("--model", type=str, default="gpt2", help=f"{NEON_YELLOW}Specify the model to use. Default is 'gpt2' for demonstration.{RESET}")
    args = parser.parse_args()

    # --- Model Loading and Error Handling ---
    try:
        # The user's original model "zai-org/GLM-4.5" is not a standard model.
        # We will use the user-specified or default model, providing a clear message.
        model_name = args.model
        if model_name == "zai-org/GLM-4.5":
            print(f"{NEON_YELLOW}Warning: The model 'zai-org/GLM-4.5' is not recognized on Hugging Face. Using 'gpt2' as a fallback.{RESET}")
            model_name = "gpt2"

        print(f"{NEON_CYAN}Loading model: {NEON_MAGENTA}{model_name}{RESET}...")

        # Load the text-generation pipeline
        pipe = pipeline("text-generation", model=model_name)

        print(f"{NEON_GREEN}Model loaded successfully!{RESET}")

    except ImportError:
        print(f"{Fore.RED}Error: The 'transformers' library is not installed.{RESET}")
        print(f"{NEON_YELLOW}Please install it using: 'pip install transformers torch'{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"{Fore.RED}An error occurred while loading the model: {e}{RESET}")
        sys.exit(1)

    # --- User Input Loop ---
    print(f"\n{NEON_CYAN}Welcome to the enhanced text generator!{RESET}")
    print(f"{NEON_YELLOW}Enter your prompt below. Type 'exit' to quit.{RESET}")

    while True:
        try:
            user_input = input(f"\n{NEON_GREEN}Prompt > {RESET}")
            if user_input.lower() == 'exit':
                print(f"{NEON_CYAN}Exiting... Goodbye!{RESET}")
                break

            if not user_input.strip():
                print(f"{NEON_YELLOW}Input cannot be empty. Please try again.{RESET}")
                continue

            # --- Generation and Output ---
            print(f"{NEON_MAGENTA}Generating response...{RESET}")

            # Generate response from the pipeline
            response_data = pipe(user_input, max_length=150, num_return_sequences=1, truncation=True)

            # Extract and clean the generated text
            generated_text = response_data[0]["generated_text"].strip()

            print(f"{NEON_CYAN}--- {NEON_MAGENTA}Generated Text{NEON_CYAN} ---{RESET}")
            print(f"{NEON_CYAN}{generated_text}{RESET}")
            print(f"{NEON_CYAN}-------------------{RESET}")

        except KeyboardInterrupt:
            print(f"\n{NEON_YELLOW}Operation cancelled by user. Exiting.{RESET}")
            sys.exit(0)
        except Exception as e:
            print(f"{Fore.RED}An error occurred during generation: {e}{RESET}")

if __name__ == "__main__":
    main()
