import os
import sys

import google.generativeai as genai


def analyze_reports(pylint_report_path, flake8_report_path):
    """Analyzes pylint and flake8 reports using the Gemini API and returns suggestions."""
    try:
        # Configure the Gemini API client
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            print("Error: GEMINI_API_KEY environment variable not set.")
            return "Error: GEMINI_API_KEY not configured."

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-pro")

        # Read the linter reports from the files
        try:
            with open(pylint_report_path) as f:
                pylint_report = f.read()
        except FileNotFoundError:
            pylint_report = "Pylint report not found."

        try:
            with open(flake8_report_path) as f:
                flake8_report = f.read()
        except FileNotFoundError:
            flake8_report = "Flake8 report not found."

        # If both reports are empty or non-existent, exit gracefully
        if not pylint_report.strip() and not flake8_report.strip():
            return "No linting issues found. Nothing to analyze."

        # Construct the prompt for Gemini
        prompt = f"""
        As an expert Python developer, analyze the following linter reports. 
        Provide specific, actionable code fixes for each issue. 
        For each suggestion, specify the file and line number.
        Present the output in clear, well-formatted Markdown.

        Pylint Report:
        ```
        {pylint_report}
        ```
        
        Flake8 Report:
        ```
        {flake8_report}
        ```
        """

        # Invoke the model
        response = model.generate_content(prompt)
        return response.text

    except Exception as e:
        print(f"An error occurred: {e}")
        return f"An error occurred during analysis: {e}"


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(
            "Usage: python analyze_python.py <pylint_report> <flake8_report> <output_file>"
        )
        sys.exit(1)

    pylint_file = sys.argv[1]
    flake8_file = sys.argv[2]
    output_file = sys.argv[3]

    suggestions = analyze_reports(pylint_file, flake8_file)

    with open(output_file, "w") as f:
        f.write(suggestions)

    print(f"Gemini analysis complete. Suggestions saved to {output_file}")
