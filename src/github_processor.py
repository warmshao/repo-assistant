import asyncio
import json
import os
import base64
import pdb
from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from src.prompts import ISSUE_PROCESSING_USER_PROMPT_TEMPLATE, PR_PROCESSING_USER_PROMPT_TEMPLATE
from src.utils import logger, print_agent_step


# --- Tool Finding Helper ---
def find_tool(tools: List[BaseTool], tool_name: str) -> Optional[BaseTool]:
    """Finds a tool by its base name in the list of available tools."""
    for tool in tools:
        # Check against potential prefix (e.g., servername__) and base name
        if tool.name == tool_name or tool.name.endswith(f"__{tool_name}"):
            return tool
    logger.warning(f"Tool '{tool_name}' not found in the available tools list.")
    return None


# --- GitHub Item Pagination Helper ---
async def fetch_all_github_items(tool: BaseTool, base_params: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Fetches all items (like issues or PRs) from a GitHub list endpoint
    using the provided MCP tool, handling pagination automatically.

    Args:
        tool: The LangChain tool instance corresponding to the GitHub list API
              (e.g., list_issues, list_pull_requests).
        base_params: A dictionary of parameters for the tool, excluding 'page'
                     and 'perPage'.

    Returns:
        A list containing all fetched items dictionaries, or an empty list on error.
    """
    all_items = []
    page = 1
    if not tool:
        logger.error("Cannot fetch items: Tool not provided.")
        return []
    MAX_ITEMS_PER_PAGE = int(os.getenv("MAX_ITEMS_PER_PAGE", 30))
    while True:
        try:
            params_for_page = {
                **base_params,
                "page": page,
                "perPage": MAX_ITEMS_PER_PAGE
            }
            logger.info(
                f"Fetching page {page} for {tool.name} with params: { {k: v for k, v in base_params.items()} }")  # Log base params only once maybe
            page_results = await tool.ainvoke(params_for_page)
            if page_results and isinstance(page_results, str):
                page_results = json.loads(page_results)
            if isinstance(page_results, list):
                items_on_page = page_results
            elif isinstance(page_results, dict):
                # Handle common structures where items might be nested
                if isinstance(page_results.get("content"), list):
                    items_on_page = page_results["content"]
                elif isinstance(page_results.get("items"), list):  # Common in search results
                    items_on_page = page_results["items"]
                else:
                    logger.warning(
                        f"Tool {tool.name} returned dict, but no 'content' or 'items' list found: {list(page_results.keys())}")
                    break  # Unknown structure
            else:
                logger.warning(
                    f"Unexpected result type from {tool.name} page {page}: {type(page_results)}. Stopping pagination.")
                break  # Stop if the format is not a list or expected dict

            if not items_on_page:
                logger.info(
                    f"No more items found on page {page} for {tool.name}. Total items fetched: {len(all_items)}")
                break  # Stop when an empty list is returned

            all_items.extend(items_on_page)
            logger.info(f"Fetched {len(items_on_page)} items on page {page}. Total so far: {len(all_items)}")

            # Check if this was the last page (GitHub returns fewer than per_page)
            if len(items_on_page) < MAX_ITEMS_PER_PAGE:
                logger.info(
                    f"Last page reached for {tool.name} (received {len(items_on_page)}, requested {MAX_ITEMS_PER_PAGE}).")
                break

            page += 1
            # Optional: Add a small delay between page requests to be polite to the API
            await asyncio.sleep(0.5)

        except Exception as e:
            logger.error(f"Error fetching page {page} for {tool.name}: {e}", exc_info=True)
            break  # Stop pagination on error
    return all_items


async def fetch_readme_content(tools: List[BaseTool], owner: str, repo: str) -> str:
    """
    Fetches the README.md content using the get_file_contents tool,
    parsing the JSON response and decoding the base64 content.
    """
    readme_tool: Optional[BaseTool] = None
    tool_name_to_find = "get_file_contents"
    for tool in tools:
        # Adjust name check if the adapter adds prefixes
        if tool.name == tool_name_to_find or tool.name.endswith(f"__{tool_name_to_find}"):
            readme_tool = tool
            break

    if not readme_tool:
        logger.warning(f"Could not find '{tool_name_to_find}' tool to fetch README.")
        return "README content could not be fetched (tool not found)."

    try:
        logger.info(f"Fetching README.md for {owner}/{repo} using tool: {readme_tool.name}")
        result = await readme_tool.ainvoke({
            "owner": owner,
            "repo": repo,
            "path": "README.md"
        })

        # --- NEW LOGIC TO PARSE JSON and DECODE BASE64 ---
        if not result:
            logger.warning("Received empty result when fetching README.")
            return "README content could not be fetched (empty result)."

        # The result might be a JSON string or already a dictionary
        data: Optional[Dict] = None
        if isinstance(result, str):
            try:
                data = json.loads(result)
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON response for README: {result[:500]}...")  # Log snippet
                return "README content could not be fetched (JSON parse error)."
        elif isinstance(result, dict):
            data = result
        else:
            logger.warning(f"Received unexpected format for README result: {type(result)}")
            return "README content could not be fetched (unexpected format)."

        if not data:
            return "README content could not be fetched (no data)."  # Should not happen if parsing worked

        # Check encoding and decode content
        encoding = data.get("encoding")
        content_encoded = data.get("content")

        if encoding == "base64" and content_encoded:
            try:
                logger.debug("Decoding base64 README content...")
                decoded_bytes = base64.b64decode(content_encoded)
                # Decode bytes to string, assuming UTF-8
                readme_text = decoded_bytes.decode('utf-8')
                logger.info("Successfully decoded README content.")
                return readme_text
            except (base64.binascii.Error, ValueError) as b64_error:
                logger.error(f"Error decoding base64 content for README: {b64_error}")
                return "README content could not be fetched (base64 decode error)."
            except UnicodeDecodeError as utf_error:
                logger.error(f"Error decoding README content bytes to UTF-8: {utf_error}")
                # Fallback: try decoding with replacement characters or return raw bytes notice?
                try:
                    return decoded_bytes.decode('utf-8', errors='replace')
                except:
                    return "README content could not be fetched (UTF-8 decode error)."
        elif content_encoded:
            # If encoding is not base64 but content exists, maybe it's plain text?
            logger.warning(
                f"README content encoding is '{encoding}', not 'base64'. Returning raw content if it's a string.")
            return str(content_encoded) if isinstance(content_encoded, (
                str, int, float)) else "README content could not be processed (non-base64)."
        else:
            logger.warning("README response did not contain 'content' field.")
            return "README content could not be fetched (missing content field)."
        # --- END OF NEW LOGIC ---

    except Exception as e:
        logger.error(f"Error invoking '{readme_tool.name}' tool for README: {e}", exc_info=True)
        return f"Error fetching README: {e}"


async def is_last_update_by_owner(
        item_number: int,
        item_type: str,  # 'issue' or 'pr'
        owner_login: str,
        repo: str,
        tools: List[BaseTool]
) -> bool:
    """
    Checks if the latest comment on an issue or PR was made by the repository owner.
    Returns True if the last comment is by the owner, False otherwise or if comments can't be fetched/parsed.
    """
    logger.debug(f"Checking last comment author for {item_type} #{item_number} against owner '{owner_login}'")

    # You could also use 'get_pull_request_comments' specifically for PRs if available and preferred
    if item_type == "pr":
        # comment_tool_name = "get_pull_request_comments"
        comment_tool_name = "get_issue_comments"
        params = {
            "owner": owner_login,  # The repo owner for the API call context
            "repo": repo,
            "issue_number": item_number
        }
    else:
        comment_tool_name = "get_issue_comments"
        params = {
            "owner": owner_login,  # The repo owner for the API call context
            "repo": repo,
            "issue_number": item_number
        }
    comments_tool = find_tool(tools, comment_tool_name)
    if not comments_tool:
        logger.warning(
            f"Cannot check last comment author for {item_type} #{item_number}: Tool '{comment_tool_name}' not found.")
        return False  # Cannot determine, assume not owner to avoid skipping valid items

    try:
        logger.debug(f"Invoking {comments_tool.name} with params: {params}")
        comments_result = await comments_tool.ainvoke(params)

        # --- Parse comments_result (might be list or dict wrapping list) ---
        comments_list = []
        if isinstance(comments_result, list):
            comments_list = comments_result
        elif isinstance(comments_result, dict) and isinstance(comments_result.get("content"), list):
            comments_list = comments_result["content"]
        elif isinstance(comments_result, str):  # Handle potential JSON string response
            try:
                parsed_res = json.loads(comments_result)
                if isinstance(parsed_res, list):
                    comments_list = parsed_res
            except json.JSONDecodeError:
                logger.warning(
                    f"Could not parse string response from {comments_tool.name} for {item_type} #{item_number}")
        # ------------------------------------------------------------------
        if not comments_list:
            logger.debug(f"No comments found for {item_type} #{item_number}. Assuming not owner.")
            return False  # No comments, so owner couldn't be the last commenter

        # The first comment in the list should be the latest
        latest_comment = comments_list[-1]
        last_commenter_login = latest_comment.get("user", {}).get("login")

        if not last_commenter_login:
            logger.warning(f"Could not determine author of the latest comment for {item_type} #{item_number}.")
            return False  # Cannot determine, assume not owner

        logger.debug(f"Latest comment on {item_type} #{item_number} by '{last_commenter_login}'.")
        is_owner = last_commenter_login.lower() == owner_login.lower()
        if is_owner:
            logger.info(f"Skipping {item_type} #{item_number}: Last comment was by owner '{owner_login}'.")
        return is_owner

    except Exception as e:
        logger.error(f"Error checking last comment for {item_type} #{item_number}: {e}", exc_info=True)
        return False  # Error occurred, assume not owner to be safe


# --- Issue Processor ---
async def process_issue(
        issue_data: Dict[str, Any],
        agent_executor: Runnable,
        owner: str,
        repo: str
):
    """
    Processes a single issue by formatting the user prompt and invoking the
    ReAct agent to perform the complete analysis and required actions.
    """
    issue_number = issue_data.get("number")
    if not issue_number:
        logger.error(f"Skipping issue processing: Missing 'number' in issue data: {issue_data}")
        return

    logger.info(f"===== Processing Issue #{issue_number} =====")

    # Prepare the user prompt with specific issue details
    try:
        user_prompt_content = ISSUE_PROCESSING_USER_PROMPT_TEMPLATE.format(
            issue_number=issue_number,
            issue_title=issue_data.get("title", "(No Title)"),
            issue_url=issue_data.get("html_url", ""),
            issue_author=issue_data.get("user", {}).get("login", "unknown_author"),
            issue_labels=", ".join([label.get("name", "") for label in issue_data.get("labels", [])]) or "None",
            issue_body=issue_data.get("body", "") if issue_data.get("body") else "(No Description)",
            repo_name=repo
        )
    except KeyError as e:
        logger.error(f"Failed to format issue prompt for #{issue_number} - missing key: {e}. Skipping.")
        return

    # Construct the input message list for the agent
    agent_input = {"messages": [("user", user_prompt_content)]}

    try:
        logger.info(f"Invoking agent for Issue #{issue_number}...")
        # final_answer = f"(Agent did not produce final answer for Issue #{issue_number})"  # Default/fallback

        # Stream events to observe the agent's process (tool calls, thoughts)
        # final_answer = await agent_executor.ainvoke(agent_input)
        async for event in agent_executor.astream_events(agent_input):
            print_agent_step(event)  # Log intermediate steps via utility function
            # Capture the final answer from the main chain's end event
            if event.get("event") == "on_chain_end":  # Adjust based on agent type if needed
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "messages" in output:
                    final_messages = output.get("messages", [])
                    if final_messages and hasattr(final_messages[-1], 'content'):
                        final_answer = final_messages[-1].content

        # Log the agent's final summary/confirmation message
        logger.info(f"Agent finished processing Issue #{issue_number}. Final confirmation: {final_answer}")
        # NOTE: Actions (commenting, closing) are performed by the agent itself via tool calls during the stream.

    except Exception as e:
        logger.error(f"Unhandled error during agent invocation for Issue #{issue_number}: {e}", exc_info=True)
        # Depending on the error, you might want to retry or flag the issue.
    finally:
        logger.info(f"===== Finished processing Issue #{issue_number} =====")


# --- PR Processor ---
async def process_pr(
        pr_data: Dict[str, Any],
        agent_executor: Runnable,
        owner: str,
        repo: str
):
    """
    Processes a single PR by formatting the user prompt and invoking the
    ReAct agent to perform the complete analysis and required actions (commenting only).
    """
    pr_number = pr_data.get("number")
    if not pr_number:
        logger.error(f"Skipping PR processing: Missing 'number' in PR data: {pr_data}")
        return

    logger.info(f"===== Processing PR #{pr_number} =====")

    # Prepare the user prompt with specific PR details
    try:
        user_prompt_content = PR_PROCESSING_USER_PROMPT_TEMPLATE.format(
            pr_number=pr_number,
            pr_title=pr_data.get("title", "(No Title)"),
            pr_url=pr_data.get("html_url", ""),
            pr_author=pr_data.get("user", {}).get("login", "unknown_author"),
            pr_head_branch=pr_data.get("head", {}).get("ref", "unknown_branch"),
            pr_base_branch=pr_data.get("base", {}).get("ref", "unknown_branch"),
            pr_body=pr_data.get("body", "") if pr_data.get("body") else "(No Description)",
            repo_name=repo
        )
    except KeyError as e:
        logger.error(f"Failed to format PR prompt for #{pr_number} - missing key: {e}. Skipping.")
        return

    # Construct the input message list for the agent
    agent_input = {"messages": [("user", user_prompt_content)]}

    try:
        logger.info(f"Invoking agent for PR #{pr_number}...")
        # final_answer = f"(Agent did not produce final answer for PR #{pr_number})"  # Default/fallback

        # final_answer = await agent_executor.ainvoke(agent_input)
        # Stream events to observe the agent's process
        async for event in agent_executor.astream_events(agent_input):
            print_agent_step(event)  # Log intermediate steps
            # Capture the final answer
            if event.get("event") == "on_chain_end":
                output = event.get("data", {}).get("output", {})
                if isinstance(output, dict) and "messages" in output:
                    final_messages = output.get("messages", [])
                    if final_messages and hasattr(final_messages[-1], 'content'):
                        final_answer = final_messages[-1].content

        # Log the agent's final summary/confirmation message
        logger.info(f"Agent finished processing PR #{pr_number}. Final confirmation: {final_answer}")
        # NOTE: The comment action is performed by the agent itself via a tool call.

    except Exception as e:
        logger.error(f"Unhandled error during agent invocation for PR #{pr_number}: {e}", exc_info=True)
    finally:
        logger.info(f"===== Finished processing PR #{pr_number} =====")
