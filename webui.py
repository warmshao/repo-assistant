import json

import gradio as gr
import os
import uuid
import logging
import argparse  # Import argparse
from typing import List, Optional, Dict, Any, Sequence, Tuple

# LangChain & LangGraph components
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.tools import BaseTool
# Choose your LLM provider
# from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import add_messages
from langgraph.errors import GraphRecursionError  # To catch potential loops
from gradio.themes import Citrus, Default, Glass, Monochrome, Ocean, Origin, Soft, Base

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
from src.utils import logger, get_llm_model, load_decorated_tools_from_module
from src.mcp_client import setup_mcp_client_and_tools
from src.agent import create_repo_agent, create_repo_fqa_agent

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "gpt-4o")
ISSUE_INTERVAL = int(os.getenv("ISSUE_FETCH_INTERVAL_SECONDS", 300))
PR_INTERVAL = int(os.getenv("PR_FETCH_INTERVAL_SECONDS", 300))

llm = None
memory = None
mcp_client = None
mcp_tools = []
extra_tools = []
fqa_agent = None

# --- Gradio Theme Map ---
theme_map = {
    "Default": Default(),
    "Soft": Soft(),
    "Monochrome": Monochrome(),
    "Glass": Glass(),
    "Origin": Origin(),
    "Citrus": Citrus(),
    "Ocean": Ocean(),
    "Base": Base()
}


async def init_agent(repo_url, repo_docs_url="", reinit_agent=False):
    global llm, mcp_client, mcp_tools, memory, llm, fqa_agent, extra_tools
    if not extra_tools:
        extra_tools = load_decorated_tools_from_module("src.tools")
    if mcp_client is None or not mcp_tools:
        mcp_tools, mcp_client = await setup_mcp_client_and_tools()
    if memory is None:
        memory = MemorySaver()
    if llm is None:
        llm = get_llm_model(provider=LLM_PROVIDER, model_name=LLM_MODEL_NAME)
    if fqa_agent is None or reinit_agent:
        fqa_agent = await create_repo_fqa_agent(llm=llm, tools=mcp_tools + extra_tools, memory=memory,
                                                repo_url=repo_url,
                                                repo_docs_url=repo_docs_url)


# --- Gradio UI Creation Function ---
def create_gradio_app(theme_name: str = "Ocean", custom_css: Optional[str] = None):
    """Creates the Gradio Blocks UI with specified theme and CSS."""

    # Ensure the theme name exists in the map, default if not
    selected_theme = theme_map.get(theme_name, gr.themes.Soft())  # Default to Soft if key not found

    with gr.Blocks(theme=selected_theme, css=custom_css, title="GitHub Repo Assistant") as app:

        # State variables
        thread_id_state = gr.State(str(uuid.uuid4().hex))
        active_repo_url_state = gr.State("")
        active_docs_url_state = gr.State("")

        # Header - Apply CSS class if provided
        with gr.Row():
            gr.Markdown(
                """
                # 🤖️ Repo Assistant
                ### Ask any question to any Repository
                """,
                elem_classes=["header-text"],
            )

        with gr.Row():
            repo_url_input = gr.Textbox(label="GitHub Repository URL",
                                        value="https://github.com/browser-use/web-ui", scale=3)
            repo_docs_url_input = gr.Textbox(label="Documentation URL (Optional)",
                                             value="https://docs.browser-use.com/introduction", scale=2)

        chatbot = gr.Chatbot(label="Chat History", height=600)
        msg_input = gr.Textbox(label="Your Message", value="give me the structure of this repo", scale=4,
                               autofocus=True, show_label=False, container=False)

        with gr.Row():
            submit_button = gr.Button("Submit", variant="primary")
            clear_button = gr.Button("Clear Chat")

        # --- Event Handlers (submit_message, clear_chat - Keep from previous response) ---

        async def submit_message(
                user_message: str,
                history: List[List[str]],
                repo_url: str,
                docs_url: Optional[str],
                thread_id: str,  # thread_id_state
                active_repo_url: str,  # active_repo_url_state
                active_docs_url: Optional[str]  # active_docs_url_state
        ) -> Tuple[List[List[str]], Any, str, str, Optional[str]]:
            """Handles message submission, agent initialization/re-initialization, and streaming response."""

            history = history or []
            if not user_message.strip():
                gr.Warning("Please enter a message.")

            repo_url = repo_url.strip()
            docs_url = docs_url.strip() if docs_url else None

            if not repo_url:
                gr.Warning("Please enter a GitHub Repository URL.")

            # --- Agent Initialization / Re-initialization Check ---
            agent_needs_update = False
            global fqa_agent

            if fqa_agent is None or repo_url != active_repo_url or docs_url != active_docs_url:
                logger.info(f"URLs changed or agent not initialized. Re-initializing agent for: {repo_url}")
                await init_agent(repo_url, repo_docs_url=docs_url, reinit_agent=True)
                agent_needs_update = True
                active_repo_url = repo_url
                active_docs_url = docs_url
                # Start a new conversation thread for the new repo/context
                thread_id = str(uuid.uuid4().hex)
                logger.info(f"Started new conversation thread: {thread_id}")
                # Clear history for new repo, add initialization message
                history = [[None, f"🤖 Assistant initialized for {active_repo_url}. How can I help?"]]
                # Immediately yield the initialization message
                yield history, thread_id, active_repo_url, active_docs_url

            # Add user message to UI history
            history.append([user_message, None])  # Placeholder for agent response
            yield history, thread_id, active_repo_url, active_docs_url  # Update UI to show user message

            messages_to_send = [HumanMessage(content=user_message)]

            # --- Stream Agent Response ---
            config = {"configurable": {"thread_id": thread_id}}

            try:
                async for output_chunk in fqa_agent.astream({"messages": messages_to_send}, config=config,
                                                            stream_mode="values"):

                    current_messages = output_chunk["messages"]  # Get the last message list in the stream step
                    if isinstance(current_messages[-1], AIMessage):
                        if hasattr(current_messages[-1], "content") and current_messages[-1].content:
                            # Append only the new part of the message content if streaming tokens
                            # For now, replace the whole message for simplicity per chunk
                            full_response = current_messages[-1].content
                            history.append([None, f"\n-------------------------\n{full_response}\n"])
                            yield history, thread_id, active_repo_url, active_docs_url
                        elif hasattr(current_messages[-1], "tool_calls") and current_messages[-1].tool_calls:
                            full_response = json.dumps(current_messages[-1].tool_calls)
                            history.append([None, f"\n-------------------------\n{full_response}\n"])
                            yield history, thread_id, active_repo_url, active_docs_url
                    elif isinstance(current_messages[-1], ToolMessage):
                        if hasattr(current_messages[-1], "content") and current_messages[-1].content:
                            # Append only the new part of the message content if streaming tokens
                            # For now, replace the whole message for simplicity per chunk
                            full_response = current_messages[-1].content
                            history.append([None, f"\n-------------------------\n{full_response}\n"])
                            yield history, thread_id, active_repo_url, active_docs_url
                history.append([None, "\n---- Agent finish working!----\n"])
                yield history, thread_id, active_repo_url, active_docs_url

            except GraphRecursionError:
                logger.error(f"Recursion error detected in agent execution for thread {thread_id}.")
                error_msg = "🤖 Error: The request caused an internal loop. Please try rephrasing."
                if history[-1][1] is None:
                    history[-1].append(error_msg)
                else:
                    history[-1][1] = error_msg
                yield history, thread_id, active_repo_url, active_docs_url
            except Exception as e:
                logger.error(f"Error during agent execution for thread {thread_id}: {e}", exc_info=True)
                error_msg = f"🤖 An error occurred: {str(e)[:500]}"  # Show first 500 chars
                if history[-1][1] is None:
                    history[-1].append(error_msg)
                else:
                    history[-1][1] = error_msg
                yield history, thread_id, active_repo_url, active_docs_url

            # Final yield to ensure the last state is rendered (might be redundant with async for)
            # yield history, current_agent, thread_id, active_repo_url, active_docs_url

        async def clear_chat(thread_id: str) -> Tuple[List, str]:
            """Clears the chatbot history and starts a new memory thread."""
            logger.info(f"Clearing chat. Old thread ID: {thread_id}")
            new_thread_id = str(uuid.uuid4().hex)
            logger.info(f"Started new conversation thread after clear: {new_thread_id}")
            # Memory is implicitly cleared for the UI by changing thread_id
            return [], new_thread_id  # Return empty history and new thread ID

        # --- Connect UI Components ---
        # Use .then() for chaining actions: submit -> clear input
        submit_inputs = [msg_input, chatbot, repo_url_input, repo_docs_url_input, thread_id_state,
                         active_repo_url_state, active_docs_url_state]
        submit_outputs = [chatbot, thread_id_state, active_repo_url_state, active_docs_url_state]

        submit_event = msg_input.submit(
            fn=submit_message,
            inputs=submit_inputs,
            outputs=submit_outputs
        ).then(lambda: gr.update(value=""), None, [msg_input], queue=False)  # Clear input after submit

        submit_button.click(
            fn=submit_message,
            inputs=submit_inputs,
            outputs=submit_outputs
        ).then(lambda: gr.update(value=""), None, [msg_input], queue=False)  # Clear input after submit

        clear_button.click(
            fn=clear_chat,
            inputs=[thread_id_state],
            outputs=[chatbot, thread_id_state],
            queue=False  # Clearing should be fast
        ).then(lambda: (gr.update(), gr.update(), gr.update(value=None)),  # Clear URLs and chatbot
               None,
               [repo_url_input, repo_docs_url_input, chatbot], queue=False)

    return app


# --- Main Function for Arg Parsing and Launch ---
def main():
    parser = argparse.ArgumentParser(description="Gradio UI for GitHub Repo Assistant")
    parser.add_argument("--ip", type=str, default="127.0.0.1", help="IP address to bind to")
    parser.add_argument("--port", type=int, default=7788, help="Port to listen on")
    # Use choices from the theme_map keys
    parser.add_argument("--theme", type=str, default="Ocean", choices=theme_map.keys(), help="Theme to use for the UI")
    args = parser.parse_args()

    # Define custom CSS (optional)
    custom_css = """
    .gradio-container {
        width: 60vw !important; 
        max-width: 60% !important; 
        margin-left: auto !important;
        margin-right: auto !important;
        padding-top: 20px !important;
    }
    .header-text {
        text-align: center;
        margin-bottom: 20px; /* Reduced margin */
    }
    /* You can add more specific CSS rules here */
    """

    logger.info(f"Starting Gradio App with theme: {args.theme}")
    demo = create_gradio_app(theme_name=args.theme, custom_css=custom_css)

    logger.info(f"Launching on http://{args.ip}:{args.port}")
    demo.launch(server_name=args.ip, server_port=args.port)


if __name__ == '__main__':
    main()
