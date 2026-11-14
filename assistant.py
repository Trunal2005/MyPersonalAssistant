"""Command-line version of JUGNU.

Only the terminal screen lives here: the greeting, the commands, and the wording
of the messages. Everything shared with the desktop app (the model, the clock, the
calculator and the request to Ollama) comes from core.py.
"""
import argparse
import json
from pathlib import Path

from core import (
    ERROR_CONNECTION,
    ERROR_INVALID,
    ERROR_TIMEOUT,
    build_messages,
    calculate,
    chat,
    is_time_question,
    local_now,
)
from export_manager import export_chat
from models import (
    DEFAULT_MODEL,
    fetch_local_models,
    format_bytes,
    resolve_active_model,
)
from search_engine import SearchEngine

# calculate() and is_time_question() now live in core.py; they stay importable from here.
__all__ = ["calculate", "is_time_question", "ask_ai", "run_assistant"]

# ---------------- CONFIGURATION ----------------

SYSTEM_PROMPT = """
You are a helpful personal AI assistant.

Rules:
1. Always answer in clear and simple English only.
2. Never answer in Hindi or Hinglish.
3. Explain concepts in an easy-to-understand way.
4. Be polite, friendly, and helpful.
5. If you do not know something, say so honestly.
"""

# ---------------- GREETING ----------------

def greet():
    hour = local_now().hour

    if hour < 12:
        greeting = "Good morning!"
    elif hour < 17:
        greeting = "Good afternoon!"
    else:
        greeting = "Good evening!"

    print("\n" + "=" * 45)
    print("       MY PERSONAL AI ASSISTANT")
    print("=" * 45)
    print(greeting)
    print("I am ready to help you.")
    print("Type 'help' to see commands.")
    print("Type 'bye' to exit.")
    print("=" * 45)


# ---------------- TIME ----------------

def get_time():
    current_time = local_now().strftime("%I:%M:%S %p")
    return f"The current time is {current_time}."


# ---------------- DATE ----------------

def get_date():
    current_date = local_now().strftime("%d %B %Y")
    return f"Today's date is {current_date}."


# ---------------- AI CHAT ----------------

def ask_ai(user_message, model=None):
    result = chat(
        build_messages(SYSTEM_PROMPT, [{"role": "user", "content": user_message}]),
        model=model,
    )

    if result.ok:
        return result.answer

    if result.error == ERROR_CONNECTION:
        return (
            "I cannot connect to Ollama. "
            "Please make sure Ollama is running."
        )

    if result.error == ERROR_TIMEOUT:
        return (
            "The AI is taking too long to respond. "
            "Please try again."
        )

    if result.error == ERROR_INVALID:
        return "An error occurred: Ollama returned an invalid response."

    return f"An error occurred: {result.detail}"


def _load_history():
    try:
        with open("jugnu_history.json", "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


# ---------------- HELP ----------------

def show_help():
    print("\nAvailable commands:")
    print("1. time                  - Show current time")
    print("2. date                  - Show today's date")
    print("3. calculate <expr>      - Calculate a mathematical expression")
    print("4. /models               - List installed Ollama models")
    print("5. /model <name>         - Switch active Ollama model")
    print("6. /search <query>       - Search across conversation history")
    print("7. /export [id] <format> - Export chat to md, html, json, or txt")
    print("8. /chats                - List all saved conversation history")
    print("9. help                  - Show available commands")
    print("10. bye                  - Exit the assistant")
    print("\nYou can also ask any general question.")


# ---------------- MAIN ASSISTANT ----------------

def run_assistant(model=None):
    active_model = resolve_active_model(model or DEFAULT_MODEL)
    greet()

    while True:
        prompt_prefix = f"\nYou ({active_model}): " if active_model != DEFAULT_MODEL else "\nYou: "
        user_input = input(prompt_prefix).strip()

        if not user_input:
            continue

        command = user_input.lower()

        # Exit
        if command in ["bye", "exit", "quit", "goodbye"]:
            print("\nAssistant: Goodbye! Have a great day.")
            break

        # Help
        elif command == "help":
            show_help()

        # Time
        elif command in ["time", "what is the time", "what time is it"]:
            print("\nAssistant:", get_time())

        # Date
        elif command in ["date", "what is the date", "today's date"]:
            print("\nAssistant:", get_date())

        # Calculator
        elif command.startswith("calculate "):
            expression = user_input[10:].strip()
            print("\nAssistant:", calculate(expression))

        # List models
        elif command in ["/models", "models"]:
            print("\nAssistant: Fetching installed Ollama models...")
            models_list = fetch_local_models()
            if not models_list:
                print("No installed models found or Ollama is offline.")
            else:
                print(f"\nInstalled Models (Active: {active_model}):")
                for m in models_list:
                    star = "* " if m.name == active_model else "  "
                    print(f" {star}{m.display_name}")

        # Switch model
        elif command.startswith("/model ") or command.startswith("model ") or command.startswith("/switch "):
            parts = user_input.split(maxsplit=1)
            new_model = parts[1].strip() if len(parts) > 1 else ""
            if new_model:
                active_model = new_model
                print(f"\nAssistant: Switched active model to '{active_model}'.")
            else:
                print(f"\nAssistant: Current active model is '{active_model}'.")

        # Search conversations
        elif command.startswith("/search"):
            query = user_input[7:].strip()
            if not query:
                print("\nAssistant: Please provide a search query, e.g. /search quicksort")
            else:
                history = _load_history()
                engine = SearchEngine(history)
                results = engine.search(query, limit=10)
                if not results:
                    print(f"\nAssistant: No matches found for '{query}'.")
                else:
                    print(f"\nAssistant: Found {len(results)} match(es) for '{query}':")
                    for idx, res in enumerate(results, 1):
                        role_tag = "User" if res.role == "user" else "JUGNU"
                        time_str = f" ({res.timestamp})" if res.timestamp else ""
                        print(f"{idx}. [{res.chat_title}]{time_str} {role_tag}: {res.snippet}")

        # Export chat
        elif command.startswith("/export"):
            parts = user_input.split()
            history = _load_history()
            if not history:
                print("\nAssistant: No conversation history found to export.")
            else:
                fmt = "md"
                target_chat = history[-1]
                if len(parts) == 2:
                    fmt = parts[1].lower().lstrip(".")
                elif len(parts) >= 3:
                    cid = parts[1]
                    fmt = parts[2].lower().lstrip(".")
                    matched = next((c for c in history if c.get("id") == cid), None)
                    if matched:
                        target_chat = matched
                    else:
                        print(f"\nAssistant: Chat ID '{cid}' not found. Using most recent chat.")

                raw_title = target_chat.get("title", "chat")
                safe_title = "".join(c if c.isalnum() else "_" for c in raw_title).strip("_") or "chat"
                filename = f"jugnu_export_{safe_title}.{fmt}"
                try:
                    export_chat(target_chat, fmt, output_path=filename)
                    print(f"\nAssistant: Successfully exported '{target_chat.get('title')}' to '{filename}'.")
                except Exception as err:
                    print(f"\nAssistant: Export error: {err}")

        # List saved chats
        elif command in ["/chats", "/history"]:
            history = _load_history()
            if not history:
                print("\nAssistant: No saved chats.")
            else:
                print(f"\nSaved Chats ({len(history)}):")
                for idx, c in enumerate(history, 1):
                    msg_count = len(c.get("messages", []))
                    print(f"{idx}. [{c.get('id')[:8]}] {c.get('title', 'New Chat')} ({msg_count} messages)")

        # General AI question
        else:
            print(f"\nAssistant: Thinking ({active_model})...")
            answer = ask_ai(user_input, model=active_model)
            print("\nAssistant:", answer)


# ---------------- START ----------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="JUGNU Terminal Assistant")
    parser.add_argument("--model", type=str, default=None, help="Ollama model to use")
    args, _ = parser.parse_known_args()
    run_assistant(model=args.model)
