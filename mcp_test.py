import asyncio
import os
import shutil # For checking if npx/uvx exists

# Import necessary components from the Agents SDK
from agents import Agent, Runner, trace
from agents.mcp import MCPServerStdio

# Ensure npx and uvx are available in the system path
if not shutil.which("npx"):
    raise RuntimeError(
        "npx command not found. Please install Node.js and npm from https://nodejs.org/"
    )
if not shutil.which("uvx"):
    raise RuntimeError(
        "uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv"
    )

async def main():
    # --- 1. Set up the MCP Server ---

    # Get the absolute path to the directory containing sample files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(current_dir, "sample_mcp_files")

    # Configure the filesystem MCP server to run via npx
    # It will be started as a subprocess managed by MCPServerStdio
    # We point it to the 'sample_mcp_files' directory we created.
    mcp_server_filesystem = MCPServerStdio(
        name="Filesystem Server via npx", # A name for tracing/logging
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", samples_dir],
        },
        # Caching can speed things up if the tool list doesn't change often.
        # For the filesystem server, it's generally safe.
        cache_tools_list=True,
    )

    # Configure the fetch MCP server to run via uvx
    mcp_server_fetch = MCPServerStdio(
        name="Fetch Server via uvx",
        params={
            "command": "uvx",
            "args": ["mcp-server-fetch"],
        },
        cache_tools_list=True, # Caching is usually fine for fetch tools too
    )


    # --- 2. Set up the Agent ---

    # Create an Agent instance. Crucially, pass the MCP server instance
    # to the `mcp_servers` list. This makes the tools provided by the
    # server available to the agent.
    agent = Agent(
        name="FileFetchAgent",
        instructions=(
            "You are an agent that can interact with a local filesystem and fetch web content. "
            "Use the available tools (like list_directory, read_file, fetch) "
            "to answer questions based on local files or web resources."
        ),
        mcp_servers=[mcp_server_filesystem, mcp_server_fetch], # Add both servers
        # We'll use a default OpenAI model here just for the agent logic,
        # the core interaction is via the MCP tools.
        model="gpt-4o-mini",
    )

    # --- 3. Run the Agent Interactively ---

    # The MCPServerStdio instances need to be connected before use.
    # Nesting 'async with' blocks handles connect() and cleanup() for both.
    async with mcp_server_filesystem as fs_server, mcp_server_fetch as fetch_server:
        print("MCP Servers (Filesystem, Fetch) connected. Starting interactive chat...")
        print("Type 'quit' or 'exit' to end the session.")

        # Optional: Wrap the entire interactive session in a trace
        with trace("MCP Filesystem Interactive Session"):
            while True:
                try:
                    # Get user input
                    user_input = input("\nYou: ")
                    if user_input.lower() in ["quit", "exit"]:
                        print("Exiting chat.")
                        break

                    # Run the agent with the user's input
                    # The Runner handles context persistence across calls
                    result = await Runner.run(
                        starting_agent=agent,
                        input=user_input,
                    )

                    # Print the agent's final response
                    print("\nAgent:")
                    print(result.final_output)

                except KeyboardInterrupt:
                    print("\nExiting chat due to interrupt.")
                    break
                except Exception as e:
                    print(f"\nAn error occurred: {e}")
                    # Optionally, decide if the loop should continue or break on error

    print("\nChat session complete. MCP Servers disconnected.")

if __name__ == "__main__":
    # Use try-except to catch potential issues during async run, like initial connection errors
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"An error occurred during script execution: {e}")
