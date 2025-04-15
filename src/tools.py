import pdb

from langchain_core.tools import tool
import logging
import base64
import json
import logging
from typing import Optional, Dict  # Dict is needed for type hint of the simulated result
from gitingest import ingest, ingest_async

from .utils import logger


def parse_and_decode_raw_result(result: Optional[Dict | str]) -> str:
    """Parses and recode the raw result return by get_file_contents function call. Please input the whole raw result(str) directly, do not ."""
    # --- Paste the exact _parse_and_decode logic from the class version here ---
    if result is None:
        return f"Error: Could not fetch content (simulated file not found or error)."
    # --- Start of your parsing logic ---
    if isinstance(result, str):
        try:
            data = json.loads(result)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON response for content: {result[:500]}...")
            return "Error: Content could not be processed (JSON parse error)."
    elif isinstance(result, dict):
        data = result
    else:
        logger.warning(f"Received unexpected format for content result: {type(result)}")
        return "Error: Content could not be processed (unexpected format)."

    if not data:
        # This case should ideally be caught by the None check earlier if result was None
        return "Error: Content could not be processed (no data)."

    # Check encoding and decode content
    encoding = data.get("encoding")
    content_encoded = data.get("content")  # Renamed from 'content' in your example

    if not content_encoded:
        logger.warning("API response did not contain 'content' field.")
        return "Error: Content could not be fetched (missing content field)."

    if encoding == "base64":
        try:
            logger.debug("Decoding base64 content...")
            # Ensure content_encoded is bytes for b64decode if necessary
            # (GitHub API usually returns string, b64decode handles ASCII strings)
            decoded_bytes = base64.b64decode(content_encoded)
            # Decode bytes to string, assuming UTF-8
            decoded_text = decoded_bytes.decode('utf-8')
            logger.info("Successfully decoded content.")
            return decoded_text
        except (base64.binascii.Error, ValueError) as b64_error:
            logger.error(f"Error decoding base64 content: {b64_error}")
            return "Error: Content could not be fetched (base64 decode error)."
        except UnicodeDecodeError as utf_error:
            logger.error(f"Error decoding content bytes to UTF-8: {utf_error}")
            try:
                # Fallback: try decoding with replacement characters
                return decoded_bytes.decode('utf-8', errors='replace')
            except Exception as final_decode_error:
                logger.error(f"Final decoding attempt failed: {final_decode_error}")
                return "Error: Content could not be fetched (UTF-8 decode error)."
    elif content_encoded:
        # If encoding is not base64 but content exists, return it as string
        logger.warning(
            f"Content encoding is '{encoding}', not 'base64'. Returning raw content as string.")
        return str(content_encoded)
    else:
        # This case is covered by the initial check for content_encoded
        logger.warning("Content field was present but empty.")
        return "Error: Content field is empty."


@tool
async def get_repo_structure(repo_url: str) -> str:
    """
    Get the structure(tree) of github repository.
    """
    try:
        summary, repo_structure, content = await ingest_async(repo_url)
        repo_structure = "\n".join(repo_structure.split("\n")[2:])
        return repo_structure
    except Exception as e:
        logger.error(f"Failed to fetch structure for repo: {repo_url}: {e}")
        return f"Error: Could not fetch structure for repo: {repo_url}: {e}"
