import pdb
from typing import List, Optional
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent
from src.prompts import ISSUE_SYSTEM_PROMPT_TEMPLATE, PR_SYSTEM_PROMPT_TEMPLATE, README_CONTENT_PLACEHOLDER
from src.utils import logger
from gitingest import ingest, ingest_async

async def create_repo_agent(
        llm: BaseChatModel,
        tools: List[BaseTool],
        repo_owner: str,
        repo_name: str,
        readme_content: str,
        is_issue_agent: bool = True
) -> Optional[Runnable]:
    """
    Creates and configures a LangChain ReAct agent for repository assistance tasks.

    Args:
        llm: The initialized language model instance.
        tools: The list of available LangChain tools (from MCP).
        repo_owner: The owner of the target GitHub repository.
        repo_name: The name of the target GitHub repository.
        readme_content: The fetched content of the repository's README.md.

    Returns:
        A LangChain Runnable (agent executor) instance, or None if creation fails.
    """
    logger.info("Creating LangChain ReAct agent executor...")

    if not llm:
        logger.error("LLM instance is required to create an agent.")
        return None
    if not tools:
        logger.warning("No tools provided to the agent. It might lack capabilities.")
        return None

    # Prepare the system prompt with dynamic repository info and README content
    try:
        github_url = f"https://github.com/{repo_owner}/{repo_name}"
        summary, repo_structure, content = await ingest_async(github_url)
        if is_issue_agent:
            system_prompt = ISSUE_SYSTEM_PROMPT_TEMPLATE.format(
                repo_owner=repo_owner,
                repo_name=repo_name,
                repo_structure=repo_structure
            ).replace(README_CONTENT_PLACEHOLDER, readme_content if readme_content else "(README content unavailable)")
        else:
            system_prompt = PR_SYSTEM_PROMPT_TEMPLATE.format(
                repo_owner=repo_owner,
                repo_name=repo_name,
                repo_structure=repo_structure
            ).replace(README_CONTENT_PLACEHOLDER, readme_content if readme_content else "(README content unavailable)")
    except KeyError as e:
        logger.error(f"Failed to format system prompt - missing key: {e}")
        return None

    try:
        # create_react_agent sets up the necessary agent executor runnable
        # It internally manages the ReAct loop (Thought, Action, Observation)
        agent_executor = create_react_agent(
            llm,
            tools,
            prompt=system_prompt  # Applies the system message to the conversation history
        )
        logger.info("LangChain ReAct agent executor created successfully.")
        return agent_executor
    except ImportError:
        logger.error(
            "Failed to create agent: 'langgraph' package not found or 'create_react_agent' unavailable. Please install/update langgraph.")
        return None
    except Exception as e:
        logger.error(f"Failed to create LangChain agent: {e}", exc_info=True)
        return None
