# src/mcp_client.py
import os
import asyncio
import base64
import pdb
from typing import List, Tuple, Optional
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from src.utils import logger


async def setup_mcp_client_and_tools() -> Tuple[Optional[List[BaseTool]], Optional[MultiServerMCPClient]]:
    """
    Initializes the MultiServerMCPClient, connects to servers, fetches tools,
    filters them, and returns a flat list of usable tools and the client instance.

    Returns:
        A tuple containing:
        - list[BaseTool]: The filtered list of usable LangChain tools.
        - MultiServerMCPClient | None: The initialized and started client instance, or None on failure.
    """
    GITHUB_TOKEN = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
    if not GITHUB_TOKEN:
        logger.error("GitHub token is missing. Cannot start MCP client.")
        return [], None

    # Configuration for the MCP servers to connect to
    server_config = {
        "github": {
            "command": "docker",
            "args": [
                "run", "-i", "--rm",
                "-e", "GITHUB_PERSONAL_ACCESS_TOKEN",
                "ghcr.io/github/github-mcp-server"  # Assumes Docker is installed and running
            ],
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": GITHUB_TOKEN
            },
            "transport": "stdio",  # Explicitly state stdio for command-based servers
        },
        "playwright": {
            "command": "npx",  # Assumes npx (Node.js) is installed and in PATH
            "args": [
                "@playwright/mcp@latest",  # Use latest or pin a specific version
                # "--vision" # Uncomment if vision features are needed and supported
            ],
            "transport": "stdio",
            # Add any necessary environment variables for playwright if needed
            # "env": {}
        }
    }

    logger.info("Initializing MultiServerMCPClient...")
    all_tools_list: List[BaseTool] = []

    try:
        client = MultiServerMCPClient(server_config)
        await client.__aenter__()
        tools_by_server = client.get_tools()
        # Filter and flatten the tools list
        for tool in tools_by_server:
            if not hasattr(tool, 'name'):  # Basic check for valid tool object
                logger.warning(f"Skipping invalid tool object from server: {tool}")
                continue

            EXCLUDED_GITHUB_TOOLS = os.getenv("EXCLUDED_GITHUB_TOOLS", [])
            is_excluded = False
            if tool.name in EXCLUDED_GITHUB_TOOLS:
                is_excluded = True
                logger.info(f"Excluding GitHub tool based on config: {tool.name}")

            if not is_excluded:
                all_tools_list.append(tool)
                logger.debug(f"Included tool: {tool.name}")

        logger.info(f"Total usable tools collected: {len(all_tools_list)}")
        # Return the list of tools and the active client instance
        return all_tools_list, client

    except Exception as e:
        logger.error(f"Failed to setup MCP client or fetch tools: {e}", exc_info=True)
        return [], None
