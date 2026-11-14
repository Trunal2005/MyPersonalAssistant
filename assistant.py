"""Command-line version of JUGNU.

Only the terminal screen lives here: the greeting, the commands, and the wording
of the messages. Everything shared with the desktop app (the model, the clock, the
calculator and the request to Ollama) comes from core.py.
"""
from core import (
    ERROR_CONNECTION,
    ERROR_INVALID,
    ERROR_TIMEOUT,
    build_messages,
    calculate,
    chat,
    is_time_question,
    local_now,
import ast
import datetime
import json
import operator
import re
import sys

import requests

# Optional conversational openers/closers so polite phrasing still triggers
# local time/date replies without allowing unrelated sentences to match.
_GREETING_PREFIX = (
    r"(?:(?:hey|hi|hello|jugnu|ok|okay|please|pls|plz|sorry|wait|"
    r"excuse\s+me|bhai|yaar|ji)[,:\s]+)*"
)
_ASK_PREFIX = (
    r"(?:(?:can|could|would|will)\s+you\s+(?:please\s+)?)?"
    r"(?:(?:tell|show|give)\s+me[,:\s]+|do\s+you\s+(?:know|have)[,:\s]+)?"
)
_POLITE_SUFFIX = (
    r"(?:[,\s]+(?:please|pls|plz|right\s+now|now|today|abhi|bhai|yaar|ji|jugnu))*"
)
_TIME_OR_DATE_NOUN = (
    r"(?:date\s+(?:and|&)\s+time|time\s+(?:and|&)\s+date|"
    r"day\s+(?:and|&)\s+date|date\s+(?:and|&)\s+day|time|date)"
)

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

def ask_ai(user_message):
    result = chat(build_messages(SYSTEM_PROMPT, [{"role": "user", "content": user_message}]))

    if result.ok:
        return result.answer

    if result.error == ERROR_CONNECTION:
        return (
def ask_ai(user_message, stream=True):
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": user_message
                    }
                ],
                "stream": stream
            },
            stream=stream,
            timeout=120
        )

        response.raise_for_status()

        if stream:
            collected = []
            lines = (
                response.iter_lines()
                if getattr(response, "raw", None) is not None
                else (response._content.splitlines() if getattr(response, "_content", None) else [])
            )
            for line in lines:
                if not line:
                    continue
                try:
                    raw_str = (
                        line.decode("utf-8").strip()
                        if isinstance(line, (bytes, bytearray))
                        else str(line).strip()
                    )
                    if not raw_str:
                        continue
                    data = json.loads(raw_str)
                    content = data.get("message", {}).get("content", "")
                    if content:
                        sys.stdout.write(content)
                        sys.stdout.flush()
                        collected.append(content)
                    if data.get("done", False):
                        break
                except (json.JSONDecodeError, AttributeError):
                    continue
            if collected:
                print()
            return "".join(collected).strip()

        data = response.json()
        answer = data["message"]["content"]
        return answer.strip()

    except requests.exceptions.ConnectionError:
        msg = (
            "I cannot connect to Ollama. "
            "Please make sure Ollama is running."
        )
        if stream:
            print(msg)
        return msg

    if result.error == ERROR_TIMEOUT:
        return (
    except requests.exceptions.Timeout:
        msg = (
            "The AI is taking too long to respond. "
            "Please try again."
        )
        if stream:
            print(msg)
        return msg

    if result.error == ERROR_INVALID:
        return "An error occurred: Ollama returned an invalid response."

    return f"An error occurred: {result.detail}"
    except Exception as error:
        msg = f"An error occurred: {error}"
        if stream:
            print(msg)
        return msg


# ---------------- HELP ----------------

def show_help():
    print("\nAvailable commands:")
    print("1. time       - Show current time")
    print("2. date       - Show today's date")
    print("3. calculate  - Calculate a mathematical expression")
    print("4. help       - Show available commands")
    print("5. bye        - Exit the assistant")
    print("\nYou can also ask any general question.")


# ---------------- MAIN ASSISTANT ----------------

def run_assistant():
    greet()

    while True:
        user_input = input("\nYou: ").strip()

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

        # General AI question
        else:
            print("\nAssistant: ", end="", flush=True)
            ask_ai(user_input, stream=True)


# ---------------- START ----------------

if __name__ == "__main__":
    run_assistant()