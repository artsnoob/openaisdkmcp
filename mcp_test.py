import asyncio
import os
import shutil # For checking if npx exists

# Import necessary components from the Agents SDK
from agents import Agent, Runner, trace
from agents.mcp import MCPServerStdio

# Ensure npx is available in the system path
if not shutil.which("npx"):
    raise RuntimeError(
        "npx command not found. Please install Node.js and npm from https://nodejs.org/"
    )

async def main():
    # --- 1. Set up the MCP Server ---

    # Get the absolute path to the directory containing sample files
    current_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(current_dir, "sample_mcp_files")

    # Configure the filesystem MCP server to run via npx
    # It will be started as a subprocess managed by MCPServerStdio
    # We point it to the 'sample_mcp_files' directory we created.
    mcp_server_stdio = MCPServerStdio(
        name="Filesystem Server via npx", # A name for tracing/logging
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", samples_dir],
        },
        # Caching can speed things up if the tool list doesn't change often.
        # For the filesystem server, it's generally safe.
        cache_tools_list=True,
    )

    # --- 2. Set up the Agent ---

    # Create an Agent instance. Crucially, pass the MCP server instance
    # to the `mcp_servers` list. This makes the tools provided by the
    # server available to the agent.
    agent = Agent(
        name="FileAgent",
        instructions=(
            "You are an agent that can interact with a local filesystem. "
            "Use the available tools (like list_directory, read_file) "
            "to answer questions based ONLY on the files provided."
        ),
        mcp_servers=[mcp_server_stdio],
        # We'll use a default OpenAI model here just for the agent logic,
        # the core interaction is via the MCP tools.
        model="gpt-4o-mini",
    )

    # --- 3. Run the Agent Interactively ---

    # The MCPServerStdio needs to be connected before use.
    # The 'async with' block handles connect() and cleanup() automatically.
    async with mcp_server_stdio as server:
        print("MCP Server connected. Starting interactive chat...")
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
                    # The Runner should handle context persistence across calls
                    result = await Runner.run(
                        starting_agent=agent,
                        input=user_input,
                        # Context is implicitly managed by the Runner/Agent instance
                        # context=None, # No need to manage context manually here
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

    print("\nChat session complete. MCP Server disconnected.")

if __name__ == "__main__":
    # Use try-except to catch potential issues during async run, like initial connection errors
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"An error occurred during script execution: {e}")
