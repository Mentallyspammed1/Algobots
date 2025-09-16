import os
import sys

import google.generativeai as genai


def get_gemini_api_key():
    """Retrieves the Gemini API key from environment variables."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.", file=sys.stderr)
        sys.exit(1)
    return api_key

def generate_tag(text_to_tag: str) -> str:
    """Generates a tag for the given text using the Gemini API.
    In a real scenario, this would send the text to Gemini and get a tag.
    For this example, we'll simulate the interaction.
    """
    api_key = get_gemini_api_key()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemini-pro')

    try:
        # In a real application, you'd send a prompt to Gemini like:
        # response = model.generate_content(f"Generate a concise, single-word tag for the following text: '{text_to_tag}'")
        # return response.text.strip()

        # For now, we'll simulate a response
        if "trading" in text_to_tag.lower() or "market" in text_to_tag.lower():
            return "Trading"
        if "error" in text_to_tag.lower() or "issue" in text_to_tag.lower():
            return "Troubleshooting"
        return "General"
    except Exception as e:
        print(f"Error interacting with Gemini API: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python gemini_api_tagger.py <text_to_tag>", file=sys.stderr)
        sys.exit(1)

    input_text = sys.argv[1]
    tag = generate_tag(input_text)
    print(f"Generated Tag: {tag}")
