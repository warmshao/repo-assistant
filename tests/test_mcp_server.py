import pdb

from dotenv import load_dotenv
import asyncio
import sys
import os

sys.path.append(".")

load_dotenv()


async def test_list_tools():
    from langchain_mcp_adapters.client import MultiServerMCPClient

    async with MultiServerMCPClient(
            {
                "github": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "-e",
                        "GITHUB_PERSONAL_ACCESS_TOKEN",
                        "ghcr.io/github/github-mcp-server"
                    ],
                    "env": {
                        "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
                    }
                },
                "playwright": {
                    "command": "npx",
                    "args": [
                        "@playwright/mcp@latest",
                        # "--vision"
                    ]
                }
            }
    ) as client:
        all_tools = client.get_tools()
        pdb.set_trace()
        for i, tool in enumerate(all_tools):
            print(f"{i + 1}: {tool.name}; {tool.description}")


async def test_execute_tool():
    import json
    from langchain_mcp_adapters.client import MultiServerMCPClient
    from src import github_processor

    async with MultiServerMCPClient(
            {
                "github": {
                    "command": "docker",
                    "args": [
                        "run",
                        "-i",
                        "--rm",
                        "-e",
                        "GITHUB_PERSONAL_ACCESS_TOKEN",
                        "ghcr.io/github/github-mcp-server"
                    ],
                    "env": {
                        "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
                    }
                },
                "playwright": {
                    "command": "npx",
                    "args": [
                        "@playwright/mcp@latest",
                        # "--vision"
                    ]
                }
            }
    ) as client:
        all_tools = client.get_tools()

        repo_name = os.getenv("GITHUB_REPO")
        user_name = os.getenv("GITHUB_OWNER")

        tool_name = "list_issues"
        parameters = {
            "owner": user_name,
            "repo": repo_name,
            "state": "open",
            "sort": "updated",
            "direction": "desc"
        }

        # tool_name = "list_pull_requests"
        # parameters = {
        #     "owner": user_name,
        #     "repo": repo_name,
        #     "state": "open",
        #     "sort": "updated",
        #     "direction": "desc"
        # }

        tool_name = "get_file_contents"
        parameters = {
            "owner": "browser-use",
            "repo": "browser-use",
            "path": "README.md"
        }

        # tool_name = "get_pull_request_comments"
        # parameters = {
        #     "owner": user_name,  # The repo owner for the API call context
        #     "repo": repo_name,
        #     "pullNumber": 472
        # }

        # tool_name = "get_me"
        # parameters = {}

        # tool_name = "browser_navigate"
        # parameters = {
        #     "url": "https://docs.browser-use.com/introduction",
        # }

        for tool in all_tools:
            if tool.name == tool_name:
                break
        try:
            result = await tool.ainvoke(parameters)
            print(f"\nTool execution result for {tool_name}:")
            # result = json.loads(result)
            # print(len(result))
            # github_items = await github_processor.fetch_all_github_items(tool, parameters)
            # issue_comments = await github_processor.is_last_update_by_owner(item_number=87,
            #                                                                 item_type="pr",
            #                                                                 owner_login=user_name,
            #                                                                 repo=repo_name,
            #                                                                 tools=all_tools)
            pdb.set_trace()
        except Exception as e:
            print(f"Error executing tool {tool_name}: {e}")


if __name__ == '__main__':
    # asyncio.run(test_list_tools())
    asyncio.run(test_execute_tool())
