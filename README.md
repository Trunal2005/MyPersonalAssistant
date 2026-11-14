# JUGNU – Personal AI Assistant 🤖

[![Winter of Code Social 2026](https://img.shields.io/badge/WOCS-2026-blue?style=for-the-badge&logo=github)](https://woc.codesocial.tech)
[![Python](https://img.shields.io/badge/Python-3.9+-yellow?style=for-the-badge&logo=python)](https://python.org)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg?style=for-the-badge)](CONTRIBUTING.md)

**JUGNU (Just an Unusually Genius Neural Utility)** is a personal desktop AI assistant built using Python, Qt (PySide6), Ollama, and Llama 3.2.

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
- **GUI**: PySide6 (Qt for Python), themed with Qt Style Sheets (`light.qss` / `dark.qss`)
- **LLM Engine**: Ollama (Llama 3.2 3B)
- **Networking**: Requests, JSON

## ⚙️ Setup Instructions

### 1. Install Python
Ensure Python 3.9+ is installed on your system.

### 2. Install Ollama
Download and install Ollama from [ollama.com](https://ollama.com/).

### 3. Download the AI Model
Open your terminal and run:
```bash
ollama pull llama3.2:3b
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run JUGNU
```bash
python qt_app.py
```

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

The test suite covers calculator operations, error handling, unsupported expressions, and time/date question detection.

**Note:** Running the tests does not require starting the Ollama server. The window tests run offscreen with `pytest-qt`, so no window opens; the app's logic (`jugnu_core.py`) is tested without any GUI.


## 👩‍💻 Project Admin

**Kismat Kumari** ([@kismatkumari56](https://github.com/kismatkumari56))

Built with curiosity 💜