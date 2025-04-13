# main.py
import asyncio
import pdb
import signal
import os
import time
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Import LangChain/MCP components first
from langchain_core.tools import BaseTool
from langchain_core.runnables import Runnable
from langchain_mcp_adapters.client import MultiServerMCPClient

# Import local modules. Ensure .env loading happens before config values are used.
# Best practice is often to load .env explicitly early or ensure config loads it.
# We will load and validate config within main() for clarity here.
from src.utils import logger, get_llm_model
from src.mcp_client import setup_mcp_client_and_tools
from src.agent import create_repo_agent
from src.github_processor import (
    process_issue, process_pr, fetch_all_github_items, find_tool,
    is_last_update_by_owner,
    fetch_readme_content
)

# --- Global Variables ---
# For state management and graceful shutdown
mcp_client_instance: Optional[MultiServerMCPClient] = None
background_tasks: List[asyncio.Task] = []
last_processed_issue_id: Optional[int] = None  # Track last processed ID to avoid immediate re-processing
last_processed_pr_id: Optional[int] = None


# --- Processing Loop Logic ---

async def issue_processing_loop(
        agent_executor: Runnable,
        tools: List[BaseTool],
        owner: str, repo: str, interval: int
):
    """
    Periodically fetches open issues, finds the single most relevant one
    (latest updated, not by owner, not the last processed), and processes it.
    """
    global last_processed_issue_id  # Allow modification of global tracker
    list_issues_tool = find_tool(tools, "list_issues")
    if not list_issues_tool:
        logger.error("Critical: 'list_issues' tool not found. Stopping issue processing loop.")
        return

    # Initialize next fetch time to start the first cycle immediately
    next_fetch_time = time.time()

    while True:
        # 1. Calculate wait time and sleep until the next scheduled cycle
        now = time.time()
        wait_time = next_fetch_time - now
        if wait_time > 0:
            logger.debug(f"[Issue Loop] Waiting for {wait_time:.2f} seconds until next cycle.")
            try:
                await asyncio.sleep(wait_time)
            except asyncio.CancelledError:
                logger.info("[Issue Loop] Sleep interrupted, exiting loop.")
                break  # Exit the loop cleanly if cancelled during sleep
        # If wait_time <= 0, the previous cycle took too long, start immediately

        # 2. Schedule the *next* cycle's start time based on the current time + interval
        current_fetch_start_time = time.time()
        next_fetch_time = current_fetch_start_time + interval
        logger.info(f"[Issue Loop] Starting fetch cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}. "
                    f"Next cycle planned ~{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_fetch_time))}.")

        target_issue_data: Optional[Dict[str, Any]] = None
        fetch_error = False
        try:
            # 3. Fetch all open issues, sorted descending by update time
            open_issues = await fetch_all_github_items(
                list_issues_tool,
                {"owner": owner, "repo": repo, "state": "open", "sort": "updated", "direction": "desc"}
            )
            logger.info(f"[Issue Loop] Fetched {len(open_issues)} open issues.")

            # 4. Find the first eligible issue (most recent first)
            for issue_data in open_issues:
                issue_id = issue_data.get("number")
                if not issue_id:
                    logger.warning("[Issue Loop] Skipping issue with missing number.")
                    continue

                if "issues" not in issue_data.get("html_url", ""):
                    logger.warning("[Issue Loop] Skipping issue with missing html_url.")
                    continue

                # a) Skip if it was the very last item processed in the previous cycle
                if issue_id == last_processed_issue_id:
                    logger.debug(f"[Issue Loop] Issue #{issue_id} was the last processed. Checking next.")
                    continue  # Check the next newest issue

                # b) Check if the last update (comment) was by the owner
                is_owner_update = await is_last_update_by_owner(issue_id, 'issue', owner, repo, tools)
                if is_owner_update:
                    logger.debug(f"[Issue Loop] Skipping Issue #{issue_id} (last update by owner).")
                    continue  # Owner updated last, check the next newest issue

                # c) Found an eligible target!
                target_issue_data = issue_data
                logger.info(f"[Issue Loop] Found eligible target Issue #{issue_id} to process.")
                break  # Stop searching, process this one

            # 5. Process the target issue if one was found
            if target_issue_data:
                issue_id_to_process = target_issue_data.get("number")
                try:
                    await process_issue(target_issue_data, agent_executor, owner, repo)
                    # Update tracker ONLY after successful processing attempt
                    last_processed_issue_id = issue_id_to_process
                except Exception as process_err:
                    logger.error(f"[Issue Loop] Error processing Issue #{issue_id_to_process}: {process_err}",
                                 exc_info=True)
                    # Decide if last_processed_issue_id should be reset on processing error.
                    # Resetting allows retrying it next cycle if it's still eligible.
                    last_processed_issue_id = None
            else:
                logger.info("[Issue Loop] No eligible new issues found to process in this cycle.")
                # Reset tracker if nothing was processed, so the newest is eligible next time
                last_processed_issue_id = None

        except asyncio.CancelledError:
            logger.info("[Issue Loop] Task cancelled during fetch/process.")
            break  # Exit loop cleanly
        except Exception as e:
            fetch_error = True
            logger.error(f"[Issue Loop] Error during fetch/selection: {e}", exc_info=True)
            last_processed_issue_id = None  # Reset tracker on fetch error

        if fetch_error:
            logger.warning("[Issue Loop] Fetch/selection failed. Waiting for next scheduled cycle.")
            # The loop will naturally wait until `next_fetch_time` already calculated


async def pr_processing_loop(
        agent_executor: Runnable,
        tools: List[BaseTool],
        owner: str, repo: str, interval: int
):
    """
    Periodically fetches open PRs, finds the single most relevant one
    (latest updated, not by owner, not the last processed), and processes it.
    """
    global last_processed_pr_id  # Allow modification of global tracker
    list_prs_tool = find_tool(tools, "list_pull_requests")
    if not list_prs_tool:
        logger.error("Critical: 'list_pull_requests' tool not found. Stopping PR processing loop.")
        return

    # Initialize next fetch time to start the first cycle immediately
    next_fetch_time = time.time()

    while True:
        # 1. Calculate wait time and sleep until the next scheduled cycle
        now = time.time()
        wait_time = next_fetch_time - now
        if wait_time > 0:
            logger.info(f"[PR Loop] Waiting for {wait_time:.2f} seconds until next cycle.")
            try:
                await asyncio.sleep(wait_time)
            except asyncio.CancelledError:
                logger.info("[PR Loop] Sleep interrupted, exiting loop.")
                break
        # If wait_time <= 0, start immediately

        # 2. Schedule the *next* cycle's start time
        current_fetch_start_time = time.time()
        next_fetch_time = current_fetch_start_time + interval
        logger.info(f"[PR Loop] Starting fetch cycle at {time.strftime('%Y-%m-%d %H:%M:%S')}. "
                    f"Next cycle planned ~{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(next_fetch_time))}.")

        target_pr_data: Optional[Dict[str, Any]] = None
        fetch_error = False
        try:
            # 3. Fetch all open PRs, sorted descending by update time
            open_prs = await fetch_all_github_items(
                list_prs_tool,
                {"owner": owner, "repo": repo, "state": "open", "sort": "updated", "direction": "desc"}
            )
            logger.info(f"[PR Loop] Fetched {len(open_prs)} open PRs.")

            # 4. Find the first eligible PR (most recent first)
            for pr_data in open_prs:
                pr_id = pr_data.get("number")
                if not pr_id:
                    logger.warning("[PR Loop] Skipping PR with missing number.")
                    continue

                if "pull" not in pr_data.get("html_url", ""):
                    logger.warning("[PR Loop] Skipping pr with missing html_url.")
                    continue

                # a) Skip if it was the last processed
                if pr_id == last_processed_pr_id:
                    logger.debug(f"[PR Loop] PR #{pr_id} was the last processed. Checking next.")
                    continue

                # b) Check if the last update (comment) was by the owner
                # Note: PR updates might be more complex than just comments (commits, reviews).
                # is_last_update_by_owner uses comment check, which is a good proxy.
                is_owner_update = await is_last_update_by_owner(pr_id, 'pr', owner, repo, tools)
                if is_owner_update:
                    logger.debug(f"[PR Loop] Skipping PR #{pr_id} (last update by owner).")
                    continue

                # c) Found an eligible target!
                target_pr_data = pr_data
                logger.info(f"[PR Loop] Found eligible target PR #{pr_id} to process.")
                break

            # 5. Process the target PR if one was found
            if target_pr_data:
                pr_id_to_process = target_pr_data.get("number")
                try:
                    await process_pr(target_pr_data, agent_executor, owner, repo)
                    # Update tracker ONLY after successful processing attempt
                    last_processed_pr_id = pr_id_to_process
                except Exception as process_err:
                    logger.error(f"[PR Loop] Error processing PR #{pr_id_to_process}: {process_err}", exc_info=True)
                    last_processed_pr_id = None  # Allow retry next cycle
            else:
                logger.info("[PR Loop] No eligible new PRs found to process in this cycle.")
                last_processed_pr_id = None  # Reset tracker

        except asyncio.CancelledError:
            logger.info("[PR Loop] Task cancelled during fetch/process.")
            break
        except Exception as e:
            fetch_error = True
            logger.error(f"[PR Loop] Error during fetch/selection: {e}", exc_info=True)
            last_processed_pr_id = None  # Reset tracker on fetch error

        if fetch_error:
            logger.warning("[PR Loop] Fetch/selection failed. Waiting for next scheduled cycle.")


# --- Graceful Shutdown Handler ---
async def shutdown(signal_event: asyncio.Event):
    """Initiates graceful shutdown: cancels tasks, stops MCP client."""
    if signal_event.is_set():
        return  # Shutdown already in progress
    logger.info("Shutdown signal received. Initiating graceful shutdown...")
    signal_event.set()  # Signal loops and main wait to stop

    # Cancel all running background tasks
    logger.info(f"Cancelling {len(background_tasks)} background tasks...")
    cancelled_tasks = []
    for task in background_tasks:
        if not task.done():
            task.cancel()
            cancelled_tasks.append(task)

    # Wait for tasks to finish cancelling
    # Use return_exceptions=True to prevent gather from stopping if a cancelled task raises CancelledError
    results = await asyncio.gather(*cancelled_tasks, return_exceptions=True)
    logger.debug(f"Task cancellation results: {results}")
    logger.info("Background tasks cancellation process complete.")

    # Stop the MCP client using its async context manager exit method
    global mcp_client_instance
    if mcp_client_instance:
        logger.info("Stopping MCP client...")
        try:
            # Call the async exit method correctly
            await mcp_client_instance.__aexit__(None, None, None)
            logger.info("MCP client stopped successfully.")
        except Exception as e:
            logger.error(f"Error stopping MCP client: {e}", exc_info=True)
    else:
        logger.info("MCP client was not running or not initialized.")

    logger.info("Repo Assistant shutdown complete.")


# --- Main Application Entry Point ---
async def main():
    """Sets up all components, starts processing loops, and handles shutdown."""
    logger.info("Starting Repo Assistant (Cycle-Based Processing)...")
    global mcp_client_instance, background_tasks  # Declare intent to modify globals
    signal_event = asyncio.Event()  # Event to signal shutdown initiation

    # --- Load and Validate Configuration ---
    try:
        # Fetch required configuration with error handling
        GITHUB_OWNER = os.environ["GITHUB_OWNER"]
        GITHUB_REPO = os.environ["GITHUB_REPO"]
        LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
        LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gpt-4o")
        ISSUE_INTERVAL = int(os.getenv("ISSUE_FETCH_INTERVAL_SECONDS", 300))
        PR_INTERVAL = int(os.getenv("PR_FETCH_INTERVAL_SECONDS", 300))

        # Validate intervals
        if ISSUE_INTERVAL <= 0 or PR_INTERVAL <= 0:
            raise ValueError("Fetch intervals must be positive integers.")

        logger.info(
            f"Configuration: Owner={GITHUB_OWNER}, Repo={GITHUB_REPO}, Provider={LLM_PROVIDER}, Issue Interval={ISSUE_INTERVAL}s, PR Interval={PR_INTERVAL}s")

    except KeyError as e:
        logger.critical(f"FATAL: Missing required environment variable: {e}. Check your .env file. Exiting.")
        return  # Stop execution if essential config is missing
    except ValueError as e:
        logger.critical(f"FATAL: Invalid configuration value: {e}. Check your .env file. Exiting.")
        return
    except Exception as e:
        logger.critical(f"FATAL: Unexpected error loading configuration: {e}. Exiting.", exc_info=True)
        return

    # --- Setup Signal Handlers ---
    # Use the running event loop to add signal handlers
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            # Use lambda to ensure the current signal_event is captured
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(signal_event)))
        logger.debug("Signal handlers for SIGINT and SIGTERM registered.")
    except NotImplementedError:
        logger.warning(
            "Signal handlers are not supported on this platform (e.g., some Windows setups). Manual shutdown required.")
    except Exception as e:
        logger.error(f"Error setting up signal handlers: {e}", exc_info=True)

    # --- Main Application Logic ---
    try:
        # 1. Setup MCP Client and Filtered Tools
        filtered_tools, mcp_client = await setup_mcp_client_and_tools()
        if not mcp_client:
            logger.critical("Failed to initialize MCP client. Exiting.")
            return
        mcp_client_instance = mcp_client  # Store globally for shutdown
        if not filtered_tools:
            logger.warning("MCP client initialized, but no usable tools were found. Functionality may be limited.")
            # Consider if you want to exit if tools are essential
            # return

        # 2. Fetch README Content
        readme_content = await fetch_readme_content(filtered_tools, GITHUB_OWNER, GITHUB_REPO)
        if "Error" in readme_content or "Could not" in readme_content:
            logger.warning(f"Proceeding without README content. Reason: {readme_content}")
            readme_content = "(README content unavailable)"  # Provide fallback for agent

        # 3. Setup LLM
        try:
            llm = get_llm_model(provider=LLM_PROVIDER, model_name=LLM_MODEL_NAME)
        except (ValueError, Exception) as llm_err:
            logger.critical(f"Failed to initialize LLM: {llm_err}. Exiting.", exc_info=True)
            # Cleanup MCP client if LLM fails after client start
            if mcp_client_instance: await mcp_client_instance.__aexit__(None, None, None)
            return

        # 4. Create Agent Executor
        try:
            issue_agent = create_repo_agent(llm, filtered_tools, GITHUB_OWNER, GITHUB_REPO, readme_content,
                                            is_issue_agent=True)
            if not issue_agent: raise ValueError("Issue create_repo_agent returned None")
            pr_agent = create_repo_agent(llm, filtered_tools, GITHUB_OWNER, GITHUB_REPO, readme_content,
                                         is_issue_agent=False)
            if not pr_agent: raise ValueError("PR create_repo_agent returned None")
        except Exception as agent_err:
            logger.critical(f"Failed to create agent executor: {agent_err}. Exiting.", exc_info=True)
            if mcp_client_instance: await mcp_client_instance.__aexit__(None, None, None)
            return

        # 5. Start Background Processing Loops
        logger.info("Starting background processing loops...")
        task1 = asyncio.create_task(
            issue_processing_loop(
                issue_agent, filtered_tools, GITHUB_OWNER, GITHUB_REPO, ISSUE_INTERVAL
            )
        )
        task2 = asyncio.create_task(
            pr_processing_loop(
                pr_agent, filtered_tools, GITHUB_OWNER, GITHUB_REPO, PR_INTERVAL
            )
        )
        background_tasks = [task1, task2]  # Store tasks for cancellation

        # 6. Run until shutdown signal
        logger.info("Repo Assistant setup complete and running. Waiting for shutdown signal (Ctrl+C)...")
        await signal_event.wait()  # Pause main coroutine here until event is set by shutdown()

    except asyncio.CancelledError:
        logger.info("Main task cancelled, likely during shutdown sequence.")
    except Exception as e:
        # Catch unexpected errors during the main setup/wait phase
        logger.critical(f"FATAL: Unhandled error in main execution: {e}", exc_info=True)
    finally:
        # Ensure shutdown logic runs even if main errors out or signal_event.wait() is bypassed
        if not signal_event.is_set():
            logger.warning("Main execution block finished unexpectedly. Initiating shutdown sequence...")
            # Trigger shutdown manually if it wasn't initiated by a signal
            await shutdown(signal_event)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Should be caught by signal handler, but good as a fallback message
        logger.info("KeyboardInterrupt detected in __main__. Shutdown should be handled by signal handler.")
    except Exception as main_run_err:
        # Catch errors occurring *during* asyncio.run itself
        logger.critical(f"FATAL ERROR during asyncio.run(main): {main_run_err}", exc_info=True)
