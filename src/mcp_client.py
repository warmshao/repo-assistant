import os
import asyncio
import base64
import pdb
from typing import List, Tuple, Optional
from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from src.utils import logger
import base64
import json
import logging
from typing import Optional, Dict, Any, Type
from langchain_core.tools import BaseTool
from pydantic.v1 import BaseModel, Field
from langchain_core.runnables import RunnableConfig

from . import utils, tools


class DecodingWrapperTool(BaseTool):
    """
    Wraps the 'get_file_contents' tool to decode its Base64 output,
    accepting owner, repo, path, and optional branch arguments.
    """
    original_tool: BaseTool  # Holds the instance of the original get_file_contents tool

    name: str = "get_readable_file_content"  # Or keep original name if preferred? Let's use a new one.
    description: str = (  # Updated description for LLM
        "Retrieves the DECODED text content of a specific file or directory from a specified GitHub repository. "
        "Requires repository 'owner', 'repo' name, and the 'path' to the file/directory. "
        "Optionally specify a 'branch'."
    )

    # --- Define args_schema matching the original tool ---
    class GetFileContentInput(BaseModel):
        owner: str = Field(description="Repository owner (username or organization)")
        repo: str = Field(description="Repository name")
        path: str = Field(description="Path to file/directory within the repository")
        branch: Optional[str] = Field(default=None,
                                      description="Optional: Branch to get contents from (defaults to repository's default branch)")

    args_schema: Type[BaseModel] = GetFileContentInput

    # Pydantic handles __init__ to accept 'original_tool'

    def _run(
            self,
            owner: str,
            repo: str,
            path: str,
            branch: Optional[str] = None,
            config: Optional[RunnableConfig] = None,
            **kwargs: Any  # Added kwargs for robustness
    ) -> str:
        """Wraps sync run, calls original with all args, then decodes."""
        logger.info(f"Executing wrapper _run for {self.name}: owner={owner}, repo={repo}, path={path}, branch={branch}")

        # Prepare arguments for the original tool call
        tool_input = {"owner": owner, "repo": repo, "path": path}
        if branch:
            tool_input["branch"] = branch

        # Use the public .run() method for better handling of config/callbacks
        # Pass arguments as keyword arguments matching the args_schema
        try:
            raw_result = self.original_tool.run(
                tool_input=tool_input,  # Pass as a dict if original tool expects that
                # Or pass directly as kwargs if supported:
                # owner=owner, repo=repo, path=path, branch=branch,
                config=config,
                **kwargs  # Pass any extra kwargs
            )
        except Exception as e:
            logger.error(f"Error calling original tool's run method: {e}", exc_info=True)
            # Handle error appropriately, e.g., return an error message
            return f"Error: Failed to execute underlying tool - {e}"

        # Decode the result
        return tools.parse_and_decode_raw_result(raw_result)

    async def _arun(
            self,
            owner: str,
            repo: str,
            path: str,
            branch: Optional[str] = None,
            config: Optional[RunnableConfig] = None,
            **kwargs: Any  # Accept extra kwargs
    ) -> str:
        """Wraps async run, calls original with all args, then decodes."""
        logger.info(
            f"Executing wrapper _arun for {self.name}: owner={owner}, repo={repo}, path={path}, branch={branch}")

        # Prepare arguments for the original tool call
        tool_input = {"owner": owner, "repo": repo, "path": path}
        if branch:
            tool_input["branch"] = branch

        # Use the public .arun() method
        try:
            raw_result = await self.original_tool.arun(
                tool_input=tool_input,  # Pass as a dict if original tool expects that
                # Or pass directly as kwargs if supported:
                # owner=owner, repo=repo, path=path, branch=branch,
                config=config,
                **kwargs  # Pass any extra kwargs
            )
        except Exception as e:
            logger.error(f"Error calling original tool's arun method: {e}", exc_info=True)
            # Handle error appropriately
            return f"Error: Failed to execute underlying tool's async method - {e}"

        # Decode the result
        return tools.parse_and_decode_raw_result(raw_result)


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

        combined_tools: List[BaseTool] = []
        original_tool_instance = None

        # Find the original tool instance
        for tool in all_tools_list:
            if tool.name == "get_file_contents":  # Or isinstance check
                original_tool_instance = tool
                break  # Found it

        if original_tool_instance:
            logger.info(f"Wrapping original '{original_tool_instance.name}' with decoding wrapper.")
            # Create the wrapper instance, passing the original tool
            decoding_wrapper = DecodingWrapperTool(original_tool=original_tool_instance)

            # Rebuild the tool list, replacing the original with the wrapper
            for tool in all_tools_list:
                if tool is original_tool_instance:
                    combined_tools.append(decoding_wrapper)  # Add the wrapper instead
                else:
                    combined_tools.append(tool)  # Add other tools
        else:
            logger.warning("Original 'get_file_contents' tool not found. Cannot wrap.")
            combined_tools = all_tools_list

        return combined_tools, client

    except Exception as e:
        logger.error(f"Failed to setup MCP client or fetch tools: {e}", exc_info=True)
        return [], None
