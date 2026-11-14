# JUGNU – Personal AI Assistant 🤖

[![Winter of Code Social 2026](https://img.shields.io/badge/WOCS-2026-blue?style=for-the-badge&logo=github)](https://woc.codesocial.tech)
[![Python](https://img.shields.io/badge/Python-3.8+-yellow?style=for-the-badge&logo=python)](https://python.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)

**JUGNU (Just an Unusually Genius Neural Utility)** is a personal desktop AI assistant built using Python, Tkinter, Ollama, and Llama 3.2.

JUGNU is designed to provide a simple and friendly AI chat experience while exploring practical AI and Machine Learning applications on the desktop.

---

## ❄️ Winter of Code Social (WOCS) 2026

JUGNU is an official participating project in **Winter of Code Social (WOCS) 2026**! 🎉

- 🌐 **WOCS Website**: [woc.codesocial.tech](https://woc.codesocial.tech)
- 🏆 **Leaderboard**: [woc.codesocial.tech/leaderboard](https://woc.codesocial.tech/leaderboard)
- 📖 **Contributor Guide**: Please read [CONTRIBUTING.md](CONTRIBUTING.md) before submitting pull requests!

### WOCS Difficulty Levels
Contributors can earn points on the leaderboard based on merged PRs tagged with:
- level 1 (2 points) - Beginner-friendly fixes, UI tweaks, doc updates.
- level 2 (5 points) - Feature enhancements, refactoring, new UI options.
- level 3 (11 points) - Advanced features, voice/model integration, major architecture upgrades.

---

## ✨ Features

- 💬 AI-powered chat using local Llama 3.2 via Ollama
- 📝 Persistent chat history
- ➕ New Chat & Clear Current Chat options
- 🌓 Dark and Light Mode support
- 🖋️ Markdown in replies: bold, italic, headings, lists, quotes, inline code and code blocks with a Copy button (`markdown_render.py`)
- 🌐 Interface and AI replies in English or Hinglish (switch with the Language button; add more in `strings.py`)
- 🕒 Current Date and Time support
- 🤖 Custom welcome screen with mascot

## 🛠️ Tech Stack

- **Language**: Python
- **GUI**: Tkinter / ttk
- **LLM Engine**: Ollama (Llama 3.2 3B)
- **Networking**: Requests, JSON

## 🗂️ Project Structure

JUGNU has two front ends, a desktop window and a terminal version, that share one core:

| File | What it does |
| --- | --- |
| `desktop_app.py` | The desktop window (Tkinter): screens, chat history, themes, voice, buttons |
| `assistant.py` | The terminal version: greeting, commands and its own wording |
| `core.py` | **Shared by both.** Model name and Ollama address, clock helpers, safe calculator, "what time is it?" detector, `build_messages()` and `chat()` (the one place that talks to Ollama) |
| `strings.py` | All text shown in the window, in English and Hinglish |
| `markdown_render.py` | Turns Markdown in replies into styled text for the chat bubbles |
| `tts.py` | Offline voice output |
| `history_lock.py` | Stops two windows from using the same chat history |
| `tests/` | Automated tests (`test_core.py` covers the shared core) |

If something must behave the same in the window and in the terminal, it belongs in `core.py`. Wording and layout stay in the file that shows them.

## ⚙️ Setup Instructions

### 1. Install Python
Ensure Python 3.8+ is installed on your system.

### 2. Install Ollama
Download and install Ollama from [ollama.com](https://ollama.com/).

### 3. Download the AI Model
Open your terminal and run:
`ash
ollama pull llama3.2:3b
`

### 4. Install Dependencies
`ash
pip install requests
`

### 5. Run JUGNU
`ash
python desktop_app.py
`

Prefer the terminal? Run `python assistant.py` instead. It uses the same core.

---

## 🤝 Contributing

We welcome contributions of all levels!

Check out our [Open Issues](https://github.com/kismatkumari56/MyPersonalAssistant/issues) to find something you'd like to work on, and review [CONTRIBUTING.md](CONTRIBUTING.md) for full instructions and our AI policy.

---

## 🧪 Running Tests

JUGNU uses `pytest` for automated testing.

### 1. Install development dependencies

```bash
pip install -r requirements-dev.txt
```

### 2. Run all tests

```bash
python -m pytest -v
```

### 3. Run a specific test file

```bash
python -m pytest tests/test_calculator.py -v
```

```bash
python -m pytest tests/test_time_question.py -v
```

The test suite covers calculator operations, error handling, unsupported expressions, time/date question detection, and the shared core (`core.py`: building messages, talking to Ollama, and reporting errors).

**Note:** Running the tests does not require launching the Tkinter desktop application or starting the Ollama server.


## 👩‍💻 Project Admin

**Kismat Kumari** ([@kismatkumari56](https://github.com/kismatkumari56))

Built with curiosity 💜