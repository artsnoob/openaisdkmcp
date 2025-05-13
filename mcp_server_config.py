import os
from agents.mcp import MCPServerStdio
from mcp_utils import Colors # For printing status messages
import os # Ensure os is imported if not already

async def configure_servers(logger, script_dir, samples_dir):
    """Configures all MCP servers and returns their instances without testing."""
    
    # Configure the MCP Code Executor server
    # logger.info("Configuring MCP Code Executor server...") # Reduced verbosity
    mcp_server_python = MCPServerStdio(
        name="MCP Code Executor",
        params={
            "command": "node",
            "args": [os.path.join(script_dir, "mcp_code_executor", "build", "index.js")],
            "env": {
                "CODE_STORAGE_DIR": samples_dir,
                "ENV_TYPE": "venv",
                "VENV_PATH": os.path.join(samples_dir, "venv"),
                "NODE_NO_WARNINGS": "1"
            }
        },
        cache_tools_list=True,
        client_session_timeout_seconds=60, # Increased timeout for code execution
    )
    
    # Configure the filesystem MCP server
    # logger.info("Configuring Filesystem MCP server...") # Reduced verbosity
    mcp_server_filesystem = MCPServerStdio(
        name="Filesystem Server via npx",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", samples_dir],
            "env": {"NODE_NO_WARNINGS": "1"}
        },
        cache_tools_list=True,
    )

    # Configure the fetch MCP server
    # logger.info("Configuring Fetch MCP server...") # Reduced verbosity
    mcp_server_fetch = MCPServerStdio(
        name="Fetch Server via uvx",
        params={
            "command": "uvx",
            "args": ["mcp-server-fetch", "--ignore-robots-txt"],
        },
        cache_tools_list=True,
    )

    # Configure the Brave Search MCP server
    # logger.info("Configuring Brave Search MCP server...") # Reduced verbosity
    mcp_server_brave = MCPServerStdio(
        name="Brave Search Server via npx",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": {
                "BRAVE_API_KEY": os.getenv("BRAVE_API_KEY"),
                "NODE_NO_WARNINGS": "1"
            },
        },
        cache_tools_list=True,
    )

    # Configure the Obsidian MCP server
    # logger.info("Configuring Obsidian MCP server...") # Reduced verbosity
    mcp_server_obsidian = MCPServerStdio(
        name="Obsidian MCP Server",
        params={
            "command": "npx",
            "args": [
                "-y",
                "mcp-obsidian",
                "/Users/milanboonstra/Library/Mobile Documents/iCloud~md~obsidian/Documents"
            ],
            "env": {"NODE_NO_WARNINGS": "1"}
        },
        cache_tools_list=True,
    )

    all_configured_servers = [
        mcp_server_python,
        mcp_server_filesystem,
        mcp_server_fetch,
        mcp_server_brave,
        mcp_server_obsidian,
    ]
    
    logger.info(f"Configured {len(all_configured_servers)} MCP server instances. Connection attempts will be made by the agent.")
    # No print message about successful connections here as connections haven't been attempted yet.

    return all_configured_servers
