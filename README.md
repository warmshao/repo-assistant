# Repo Assistant: Ask any question to any Repository✨

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Repo Assistant is a versatile AI-powered GitHub tool offering two main capabilities:

1.  **Interactive Repository Q&A (Web UI):** Ask questions about **any** public GitHub repository! Enter a repository URL, and the assistant will help you understand the code, documentation, issues, and more. 💡
2.  **Automated Maintainer Assistance:** Designed to help maintainers automate the handling of Issues and Pull Requests (PRs) in their *own* repositories.

---

## Key Features 🌟

**1. Interactive Repository Q&A (via Web UI):**

*   **Deep Understanding:** Ask questions about the repository's purpose, code structure, specific files, dependencies, setup instructions, open issues, or documentation.
*   **Conversational Context:** Engage in **multi-turn conversations**! Ask follow-up questions, refine your queries, and explore topics in depth, as the assistant remembers the context of your current chat session.
*   **Easy Interface:** Simple Gradio-based web UI for seamless interaction.

**2. Automated Maintainer Assistance (via `main.py`):**

*   **Smart Issue Processing:**
    *   Automatically identifies and closes spam or off-topic Issues, leaving a stern comment 🚫.
    *   Attempts to understand and respond to valid Issues, potentially using project README context and external search to provide initial help or ask for clarification 🤔.
*   **Constructive PR Feedback:**
    *   Automatically reviews PR descriptions, scope, and adherence to basic standards.
    *   Leaves positive comments on well-formed PRs, encouraging contributors 👍.
    *   Provides polite and constructive feedback on PRs needing improvement (e.g., unclear description, overly large scope) ✍️.

## Demo 🎥

<video src="https://github.com/user-attachments/assets/c398fd19-f971-420f-95b2-1788f517ed2e" controls="controls" width="500" height="300">Your browser does not support this video!</video>

Watch a video demonstrating both the interactive web UI and the automated maintainer assistant features.

## How It Works ⚙️

Repo Assistant leverages the following powerful tools and technologies for both modes:

1.  **LangChain & LangGraph:** Acts as the core framework, orchestrating the Agent(ReAct), LLM, tools, state management, and processing logic for both the automated assistant and the interactive web UI.
2.  **MCP (Multi-agent Communication Protocol) Adapters:**
    *   [github-mcp-server](https://github.com/github/github-mcp-server) : Runs via Docker, providing a toolset for interacting with the GitHub API (fetching info, searching code/issues, commenting, closing issues, etc.). **Required for both modes.**
    *   [playwright-mcp](https://github.com/microsoft/playwright-mcp) : Provides capabilities for browser interaction (navigating sites, reading content, searching). Used by both modes when external web information is needed.
3.  **Large Language Models (LLM):** Provides the understanding, analysis, and text generation capabilities, using different models based on configuration.


## Getting Started 🚀

**Prerequisites:**

*   Python 3.11+
*   [uv](https://github.com/astral-sh/uv) (for package management and virtual environments)
*   Docker (to run `github-mcp-server`)
*   Node.js / npm / npx (to run `playwright-mcp`, if enabled/needed)

**Installation Steps:**

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/warmshao/repo-assistant.git
    cd repo-assistant
    ```

2.  **Set up Virtual Environment and Sync Dependencies:**
    *(Ensure `gradio` is listed in your `requirements.txt` or `pyproject.toml`)*
    ```bash
    uv sync # Install dependencies
    source .venv/bin/activate # Activate environment (Linux/macOS)
    # Or: .venv\Scripts\activate (Windows)
    ```

3.  **Configure Environment Variables:**
    Copy `.env.example` to `.env` in the root directory of the project and fill in the following details. Note which settings apply to which mode.

    ```dotenv
    # .env

    # --- GitHub Settings ---
    # Required by BOTH modes IF using github-mcp tools that need authentication
    # (e.g., reading private repos, making comments/changes). May not be strictly
    # needed by the web UI IF it only reads public repos AND only uses tools
    # that don't require auth, but recommended for full functionality.
    # Your GitHub Personal Access Token (Classic)
    # Must have 'repo' or 'public_repo' scope.
    GITHUB_PERSONAL_ACCESS_TOKEN=ghp_YOUR_VALID_GITHUB_TOKEN_HERE

    # --- Settings Primarily for Maintainer Assistant (`main.py`) ---
    # The owner of the SPECIFIC repository for automated processing
    GITHUB_OWNER=your_github_username_or_org
    # The name of the SPECIFIC repository for automated processing
    GITHUB_REPO=your_repository_name
    # Interval (in seconds) to check for new Issues in the specific repo
    ISSUE_FETCH_INTERVAL_SECONDS=300
    # Interval (in seconds) to check for new PRs in the specific repo
    PR_FETCH_INTERVAL_SECONDS=300
    # Maximum items per page when fetching from GitHub API (max 100)
    MAX_ITEMS_PER_PAGE=30
    # (Optional) Exclude specific GitHub tools for the automated assistant
    EXCLUDED_GITHUB_TOOLS=merge_pull_request,create_repository,fork_repository,push_files,create_branch,create_or_update_file,update_pull_request_branch

    # --- LLM Settings (Required by BOTH modes) ---
    # Choose your LLM provider (e.g., openai, deepseek, azure_openai, gemini, ollama)
    LLM_PROVIDER=openai
    # Specify the model name (ensure compatibility with the provider)
    LLM_MODEL_NAME=gpt-4o
    # Your LLM API Key (set the corresponding environment variable based on the provider)
    OPENAI_API_KEY=sk-YOUR_OPENAI_KEY_HERE
    # DEEPSEEK_API_KEY=sk-YOUR_DEEPSEEK_KEY_HERE
    # AZURE_OPENAI_API_KEY=...
    # AZURE_OPENAI_ENDPOINT=...
    # GOOGLE_API_KEY=...
    # OLLAMA_BASE_URL=http://localhost:11434 # If using Ollama
    ```

    **Important Note - GITHUB_PERSONAL_ACCESS_TOKEN:**
    *   Generate a **Classic Token**.
    *   Select the **`repo`** scope (for private/all repos) or **`public_repo`** scope (for public repos only). These include permissions for reading/writing Issues & PRs.
    *   **Set an expiration date** for security.
    *   **Protect your token!** Do not commit it.

4.  **Run the Assistant:**
    Choose the mode you want to run:

    *   **A) To run the Automated Maintainer Assistant (for the repo in `.env`):**
        ```bash
        python main.py
        ```
        Monitor the terminal for logs about Issue/PR processing. Press `Ctrl+C` to stop.

    *   **B) To run the Interactive Repository Q&A Web UI:**
        ```bash
        python webui.py
        ```
        This will start the Gradio web server, typically at `http://127.0.0.1:7788` (check terminal output for the exact URL). Open this URL in your browser to use the interactive assistant. You can usually specify IP/port via command-line args to `app.py` (e.g., `python app.py --ip 0.0.0.0 --port 8000`). Press `Ctrl+C` in the terminal to stop the server.

Enjoy using your AI-powered GitHub Assistant! 🎉

## Contributing ❤️

Issues, feature requests, and pull requests are welcome!

## License 📄

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.