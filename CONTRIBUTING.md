# Contributing to JUGNU 💜

Thank you for your interest in contributing to **JUGNU**! We are excited to participate in **Winter of Code Social (WOCS) 2026** ❄️.

> [!CAUTION]
> ### 🛑 MANDATORY ISSUE ASSIGNMENT POLICY
> **DO NOT start working or open a Pull Request without being officially assigned to an issue first.**
> 1. Browse the open issues.
> 2. Leave a comment on the issue asking to be assigned.
> 3. Wait until the Project Admin (**@kismatkumari56**) officially assigns the issue to you.
> 
> **Any Pull Request opened without prior assignment will be closed immediately without review.**

---

## ❄️ Winter of Code Social (WOCS) 2026 Guidelines

### Eligibility & Leaderboard Tracking
- Make sure you are registered for WOCS at [woc.codesocial.tech](https://woc.codesocial.tech).
- Merged pull requests count towards contributor points on the [WOCS Leaderboard](https://woc.codesocial.tech/leaderboard).

### Difficulty Levels & Point System
Every eligible PR will be reviewed and assigned difficulty labels by the Project Admin or Mentors:
- **wocs** + **level 1** = **2 points** (Beginner-friendly, bug fixes, UI tweaks, documentation improvements)
- **wocs** + **level 2** = **5 points** (Moderate features, enhancements, refactoring, new UI options)
- **wocs** + **level 3** = **11 points** (Substantial features, architectural upgrades, model handling, voice integration)

> [!IMPORTANT]
> The **wocs** label and a difficulty level (**level 1**, **level 2**, or **level 3**) must be added to your PR **before** it is merged to ensure points are tracked automatically. Once merged, level assignment is final.

---

## 🤖 AI Usage Policy

In accordance with WOCS guidelines, here is our project AI policy:
- **AI-Assisted Contributions**: You are welcome to use AI tools (e.g. GitHub Copilot, ChatGPT) as assistants for brainstorming, learning, or syntax help.
- **Guidelines**:
  - You must understand every line of code you submit and be able to explain your changes during PR reviews.
  - Blindly copy-pasting unverified AI-generated code without testing or understanding is strictly prohibited.
  - Always run and test your changes locally before submitting a PR.
  - Submitting unverified or hallucinated AI code may lead to PR closure and reporting to Team Code Social.

---

## 🚀 How to Contribute (Step-by-Step)

### 1. Claim an Issue First (Required)
- Browse open issues in the [Issues tab](https://github.com/kismatkumari56/MyPersonalAssistant/issues).
- Comment on the issue asking to be assigned.
- **Wait for @kismatkumari56 to assign it to you before writing any code.**

### 2. Fork & Clone
1. Fork this repository to your GitHub account.
2. Clone your fork locally:
   `ash
   git clone https://github.com/<your-username>/MyPersonalAssistant.git
   cd MyPersonalAssistant
   `
3. Add the upstream remote:
   `ash
   git remote add upstream https://github.com/kismatkumari56/MyPersonalAssistant.git
   `

### 3. Create a Branch
`ash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bugfix-name
`

### 4. Setup & Test Locally
- Follow the setup guide in [README.md](README.md).
- Install dependencies (pip install -r requirements.txt).
- If working with Ollama, ensure ollama run llama3.2:3b is accessible.
- Test your changes:
  ```bash
  python qt_app.py
  python -m pytest
  ```

### 5. Commit & Push
- Write clear commit messages:
  `ash
  git commit -m "feat: add keyboard shortcut for send"
  `
- Push to your fork:
  `ash
  git push origin feature/your-feature-name
  `

### 6. Submit a Pull Request
- Open a PR against the main branch of kismatkumari56/MyPersonalAssistant.
- In the PR description, mention your assigned issue (e.g., Closes #5).
- Ensure you follow the PR template checklist.

---

## 📋 Code Guidelines
- Write readable, clean Python code following PEP 8 conventions.
- Never commit secrets, API keys, passwords, or personal credentials.
- Be respectful, supportive, and beginner-friendly in all discussions.

---

## 💬 Need Help?
- Ask questions in issue discussions or PR comments.
- For WOCS program queries, reach out in the Code Social Discord #wocs-help channel.

Happy Contributing! 🚀