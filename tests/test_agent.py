import pdb

from dotenv import load_dotenv
import asyncio
import sys
import os

sys.path.append(".")

load_dotenv()


async def test_agent():
    from src.agent import create_repo_agent
    from src.utils import get_llm_model, print_agent_step
    from src.mcp_client import setup_mcp_client_and_tools
    from src import github_processor

    mcp_tools, mcp_client = await setup_mcp_client_and_tools()
    llm = get_llm_model("openai", model_name="gpt-4o")
    repo_name = os.getenv("GITHUB_REPO")
    owner_name = os.getenv("GITHUB_OWNER")
    readme = await github_processor.fetch_readme_content(mcp_tools, owner_name, repo_name)
    agent_executor = create_repo_agent(llm=llm, tools=mcp_tools, repo_name=repo_name, repo_owner=owner_name,
                                       readme_content=readme)
    agent_input = {"messages": [("user", "Give me the content of two open issues")]}

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

    pdb.set_trace()

if __name__ == '__main__':
    asyncio.run(test_agent())
