# Repo Assistant 🤖✨

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An AI-powered GitHub repository assistant designed to help maintainers automate the handling of Issues and Pull Requests (PRs).

**Core Features:**

*   **Smart Issue Processing:**
    *   Automatically identifies and closes spam or off-topic Issues, leaving a stern comment 🚫.
    *   Attempts to understand and respond to valid Issues, potentially using project README context and external search to provide initial help or ask for clarification 🤔.
*   **Constructive PR Feedback:**
    *   Automatically reviews PR descriptions, scope, and adherence to basic standards.
    *   Leaves positive comments on well-formed PRs, encouraging contributors 👍.
    *   Provides polite and constructive feedback on PRs needing improvement (e.g., unclear description, overly large scope) ✍️.
    *   **Note:** This assistant is strictly limited and **will never** merge PRs.
*   **Prioritization:** Processes the most recently updated Issues and PRs first.
*   **Customizable:**
    *   Supports various Large Language Model (LLM) providers (OpenAI, Azure OpenAI, DeepSeek, Gemini, Ollama, etc.).
    *   Allows configuration of scan frequency and exclusion of specific GitHub tools.

## How It Works ⚙️

Repo Assistant leverages the following powerful tools and technologies:

1.  **LangChain & LangGraph:** Acts as the core framework, orchestrating the LLM, tools, and processing logic.
2.  **MCP (Multi-agent Communication Protocol) Adapters:**
    *   `github-mcp-server`: Runs via Docker, providing a toolset for interacting with the GitHub API (fetching info, commenting, closing issues, etc.).
    *   `playwright-mcp`: Provides capabilities for browser interaction, used for searching external information or performing actions not feasible via the GitHub API when needed.
3.  **Large Language Models (LLM):** Provides the understanding, analysis, and text generation capabilities, using different models based on configuration.

The assistant periodically scans the specified GitHub repository for the latest open Issues and PRs. For each eligible item (not last updated by the repository owner), it invokes the configured LLM Agent. Combining the project's README context and the available MCP tools, the agent analyzes the item and performs the predefined actions (commenting or closing).

## Getting Started 🚀

**Prerequisites:**

*   Python 3.11+
*   [uv](https://github.com/astral-sh/uv) (for package management and virtual environments)
*   Docker (to run `github-mcp-server`)
*   Node.js / npm / npx (to run `playwright-mcp`, if enabled)

**Installation Steps:**

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/warmshao/repo-assistant.git # Replace with your repository URL
    cd repo-assistant
    ```

2.  **Set up Virtual Environment and Sync Dependencies:**
    ```bash
    uv venv # Create a virtual environment (.venv)
    uv sync # Install dependencies from requirements.txt/pyproject.toml
    source .venv/bin/activate # Activate environment (Linux/macOS)
    # Or: .venv\Scripts\activate (Windows)
    ```

3.  **Configure Environment Variables:**
    Create a `.env` file in the root directory of the project and fill in the following details (modify according to your setup):

    ```dotenv
    # .env

    # --- GitHub Settings ---
    # The owner (username or organization) of the repository you want the assistant to manage
    GITHUB_OWNER=your_github_username_or_org
    # The name of the repository you want the assistant to manage
    GITHUB_REPO=your_repository_name
    # Your GitHub Personal Access Token (Classic)
    # Must have 'repo' or 'public_repo' scope to allow reading/writing Issues/PRs (including commenting)
    GITHUB_PERSONAL_ACCESS_TOKEN=ghp_YOUR_VALID_GITHUB_TOKEN_HERE

    # --- Processing Settings ---
    # Interval (in seconds) to check for new Issues
    ISSUE_FETCH_INTERVAL_SECONDS=300
    # Interval (in seconds) to check for new PRs
    PR_FETCH_INTERVAL_SECONDS=300
    # Maximum items per page when fetching from GitHub API (max 100)
    MAX_ITEMS_PER_PAGE=30

    # --- Tool Filtering ---
    # (Optional) Exclude specific GitHub tools (comma-separated base names)
    # Default excludes potentially dangerous or less relevant tools
    EXCLUDED_GITHUB_TOOLS=merge_pull_request,create_repository,fork_repository,push_files,create_branch,create_or_update_file,update_pull_request_branch

    # --- LLM Settings ---
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
    *   Please ensure you generate a **Classic Token**.
    *   When generating the token, you **must** select the **`repo`** scope (if the repository is private or you want to manage all repositories) or the **`public_repo`** scope (if you only manage public repositories). These scopes include the necessary permissions to read and write Issues and PRs (including adding comments).
    *   **Setting an expiration date** for the token is a crucial security practice.
    *   **Protect your token like a password!** Do not commit it to your codebase.

4.  **Run the Assistant:**
    Make sure your Docker daemon is running. Then, in your terminal with the virtual environment activated, run:
    ```bash
    python main.py
    ```

The assistant should now start running and check your repository at the configured intervals! 🎉 Monitor the terminal output for activity logs. Press `Ctrl+C` to stop the assistant gracefully.

## Contributing ❤️

Issues, feature requests, and pull requests are welcome!

## License 📄

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.