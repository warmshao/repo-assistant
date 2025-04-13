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

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
logger = logging.getLogger("RepoAssistant")


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
