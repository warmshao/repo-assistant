import base64
import os
import pdb
import time
from os import access
from pathlib import Path
from typing import Dict, Optional
import requests
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from pydantic import SecretStr
import logging
from langchain_anthropic import ChatAnthropic
from langchain_mistralai import ChatMistralAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama
from langchain_openai import AzureChatOpenAI, ChatOpenAI
from langchain_aws import ChatBedrock
import random
import json
import re
from typing import Optional, Tuple
from langchain_core.tools import BaseTool
import inspect
import importlib

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger("RepoAssistant")
for logger_ in [
    'WDM',
    'httpx',
    'selenium',
    'playwright',
    'urllib3',
    'asyncio',
    'langchain',
    'openai',
    'httpcore',
    'charset_normalizer',
    'anthropic._base_client',
    'PIL.PngImagePlugin',
    'trafilatura.htmlprocessing',
    'trafilatura',
]:
    third_party = logging.getLogger(logger_)
    third_party.setLevel(logging.ERROR)
    third_party.propagate = False


def load_decorated_tools_from_module(module_name: str) -> List[BaseTool]:
    """
    Dynamically imports a module and discovers ONLY tools created using the
    @tool decorator (i.e., instances of BaseTool found at the module level,
    excluding class definitions themselves).

    Args:
        module_name: The name of the Python module to load (e.g., 'tool').

    Returns:
        A list of BaseTool objects created by the @tool decorator found in the module.
        Returns an empty list if the module cannot be imported or no such tools are found.
    """
    tools_list: List[BaseTool] = []
    try:
        # Dynamically import the module
        module = importlib.import_module(module_name)
        logger.info(f"Successfully imported module: {module_name}")

        # Inspect the module members
        for name, obj in inspect.getmembers(module):
            # --- Core Check ---
            # 1. Is the object an instance of BaseTool? (decorated functions become instances)
            # 2. Is the object NOT a class itself? (to exclude BaseTool subclasses)
            if isinstance(obj, BaseTool) and not inspect.isclass(obj):
                # This combination strongly suggests it's an instance created by @tool
                # at the module level.
                tools_list.append(obj)
                logger.info(f"Found @tool decorated tool: {name} (type: {type(obj).__name__})")

    except ModuleNotFoundError:
        logger.error(f"Module '{module_name}' not found. Cannot load custom tools.")
        return []  # Return empty list on error
    except ImportError as e:
        logger.error(f"Failed to import module '{module_name}': {e}", exc_info=True)
        return []  # Return empty list on error
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading tools from {module_name}: {e}", exc_info=True)
        return []  # Return empty list on error

    if not tools_list:
        logger.warning(f"No tools created with @tool decorator found in module: {module_name}")

    return tools_list


def extract_github_owner_repo(url: str) -> Optional[Tuple[str, str]]:
    """
    Extracts the owner and repository name from various GitHub URL formats using regex.

    Handles formats like:
    - https://github.com/owner/repo
    - http://github.com/owner/repo
    - https://www.github.com/owner/repo
    - git@github.com:owner/repo.git
    - https://github.com/owner/repo.git
    - https://github.com/owner/repo/tree/branch
    - https://github.com/owner/repo/issues/123

    Args:
        url: The GitHub URL string.

    Returns:
        A tuple containing (owner, repo_name) if extraction is successful,
        otherwise None.
    """
    if not url:
        return None, None

    # Regex to capture owner and repo name from various GitHub URL patterns
    # Breakdown:
    # (?:https?://)?     - Optional http:// or https://
    # (?:www\.)?         - Optional www.
    # github\.com        - Matches 'github.com' literally (dot escaped)
    # [: /]              - Matches either ':' (for SSH) or '/' (for HTTP/S)
    # ([a-zA-Z0-9_-]+)   - Capture group 1: Owner (alphanumeric, underscore, hyphen)
    # /                  - Separator
    # ([a-zA-Z0-9_.-]+?) - Capture group 2: Repo name (alphanumeric, underscore, hyphen, dot), non-greedy
    # (?:\.git)?         - Optional non-capturing group for '.git' suffix
    # (?:/.*)?           - Optional non-capturing group for trailing slash and anything after (like /tree/..., /issues/...)
    # $                  - Anchors the match to the end of relevant part (though search makes it flexible)

    # Simpler regex focusing on the core part after github.com[:/]
    # This is often more robust as it doesn't need to match the start perfectly
    pattern = r'github\.com[:/]([a-zA-Z0-9_-]+)/([a-zA-Z0-9_.-]+)'

    match = re.search(pattern, url, re.IGNORECASE)  # Use search to find pattern anywhere, ignore case

    if match:
        owner = match.group(1)
        repo_name = match.group(2)

        # Remove trailing '.git' if present
        if repo_name.lower().endswith('.git'):
            repo_name = repo_name[:-4]  # Slice off the last 4 characters ('.git')
        return owner, repo_name
    else:
        return None, None


def get_llm_model(provider: str, **kwargs):
    seed = kwargs.get("seed", random.randint(0, int(1e8)))

    if provider == "openai":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("OPENAI_ENDPOINT", "https://api.openai.com/v1")
        else:
            base_url = kwargs.get("base_url")

        if not kwargs.get("api_key", ""):
            api_key = os.getenv("OPENAI_API_KEY", "")
        else:
            api_key = kwargs.get("api_key")

        return ChatOpenAI(
            model=kwargs.get("model_name", "gpt-4o"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=base_url,
            api_key=api_key,
            seed=seed
        )
    elif provider == "alibaba":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("DASHSCOPE_ENDPOINT", "https://dashscope.aliyuncs.com/compatible-mode/v1")
        else:
            base_url = kwargs.get("base_url")

        if not kwargs.get("api_key", ""):
            api_key = os.getenv("DASHSCOPE_API_KEY", "")
        else:
            api_key = kwargs.get("api_key")

        return ChatOpenAI(
            model=kwargs.get("model_name", "qwen-vl-max"),
            temperature=kwargs.get("temperature", 0.0),
            base_url=base_url,
            api_key=api_key,
            seed=seed
        )
    elif provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=kwargs.get("model_name", "gemini-2.5-pro-preview-03-25"),
            temperature=kwargs.get("temperature", 0.0),
        )
    elif provider == "ollama":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434")
        else:
            base_url = kwargs.get("base_url")

        return ChatOllama(
            model=kwargs.get("model_name", "qwen2.5:14b"),
            temperature=kwargs.get("temperature", 0.0),
            num_ctx=kwargs.get("num_ctx", 16000),
            num_predict=kwargs.get("num_predict", 1024),
            base_url=base_url,
            seed=seed
        )
    elif provider == "azure_openai":
        if not kwargs.get("base_url", ""):
            base_url = os.getenv("AZURE_OPENAI_ENDPOINT", "")
        else:
            base_url = kwargs.get("base_url")

        if not kwargs.get("api_key", ""):
            api_key = os.getenv("AZURE_OPENAI_API_KEY", "")
        else:
            api_key = kwargs.get("api_key")
        return AzureChatOpenAI(
            model=kwargs.get("model_name", "gpt-4o"),
            temperature=kwargs.get("temperature", 0.0),
            api_version="2025-01-01-preview",
            azure_endpoint=base_url,
            api_key=api_key,
            seed=seed
        )
    else:
        raise ValueError(f"Unsupported provider: {provider}")


def print_agent_step(event_data: dict):
    """Logs key events from the agent's streaming process for observability."""
    kind = event_data.get("event")
    name = event_data.get("name", "")
    tags = event_data.get("tags", [])
    data = event_data.get("data", {})

    log_prefix = f"[Agent Event: {kind} | Name: {name}]"

    if kind == "on_tool_start":
        input_data = data.get("input")
        # Attempt to parse input for better logging, fallback to raw string
        try:
            # Handle cases where input might already be a dict or a JSON string
            if isinstance(input_data, str):
                input_parsed = json.loads(input_data)
                input_log = json.dumps(input_parsed, indent=2)
            elif isinstance(input_data, dict):
                input_log = json.dumps(input_data, indent=2)
            else:
                input_log = str(input_data)  # Fallback
        except (json.JSONDecodeError, TypeError):
            input_log = str(input_data)  # Fallback if parsing fails
        logger.info(f"{log_prefix} Starting Tool with args:\n{input_log}")

    elif kind == "on_tool_end":
        output_data = data.get("output", "N/A")
        # Truncate potentially long tool outputs for cleaner logs
        output_log = (str(output_data)[:300] + '...') if len(str(output_data)) > 300 else str(output_data)
        logger.info(f"{log_prefix} Finished Tool -> Output (truncated): {output_log}")

    # elif kind == "on_chat_model_end":  # Or on_llm_end depending on exact event stream
    #     # LLM finished generating a response (could be final answer or tool request)
    #     output = data.get("output", {})
    #     if hasattr(output, 'content'):
    #         logger.debug(f"{log_prefix} LLM Response: {output.content[:100]}...")  # Debug level for LLM turns
    #
    # elif kind == "on_chain_end":
    #     # Log when the main agent chain/graph finishes
    #     output = data.get("output", {})
    #     # The final answer structure depends on the agent implementation (e.g., LangGraph)
    #     if isinstance(output, dict) and "messages" in output:
    #         final_messages = output.get("messages", [])
    #         if final_messages and hasattr(final_messages[-1], 'content'):
    #             final_answer = final_messages[-1].content
    #             logger.info(f"{log_prefix} Final Answer: {final_answer}")
    #         else:
    #             logger.info(f"{log_prefix} Ended, but couldn't extract final message content.")
    #     else:
    #         # Fallback for simpler chain outputs
    #         logger.info(f"{log_prefix} Ended. Raw Output: {str(output)[:200]}...")
