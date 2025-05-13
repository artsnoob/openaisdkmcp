import os
import asyncio
from agents.mcp import MCPServerStdio
from mcp_utils import Colors # For printing status messages

async def test_single_server(logger, server_name, server_instance):
    """Test a single MCP server connection."""
    # logger.info(f"Testing connection to {server_name}...") # Reduced verbosity
    try:
        async with server_instance: # MCPServerStdio instances are async context managers
            # logger.info(f"Successfully connected to {server_name}!") # Reduced verbosity
            # print(f"{Colors.LOG_INFO}Successfully connected to {server_name}!{Colors.ENDC}") # Reduced verbosity
            return True
    except Exception as e:
        logger.error(f"Failed to connect to {server_name}: {e}")
        print(f"{Colors.LOG_ERROR}Failed to connect to {server_name}: {e}{Colors.ENDC}")
        return False

async def configure_and_test_servers(logger, script_dir, samples_dir):
    """Configures all MCP servers and tests their connections."""
    
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

    # Test each server individually
    # logger.info("Testing individual server connections...") # Reduced verbosity
    
    # Test connections concurrently
    results = await asyncio.gather(
        test_single_server(logger, "MCP Code Executor", mcp_server_python),
        test_single_server(logger, "Filesystem Server", mcp_server_filesystem),
        test_single_server(logger, "Fetch Server", mcp_server_fetch),
        test_single_server(logger, "Brave Search Server", mcp_server_brave),
        return_exceptions=True # To handle individual test failures
    )

    python_success, fs_success, fetch_success, brave_success = [
        r if isinstance(r, bool) else False for r in results # Ensure False on exception
    ]
        
    all_servers = {
        "python": mcp_server_python,
        "filesystem": mcp_server_filesystem,
        "fetch": mcp_server_fetch,
        "brave": mcp_server_brave,
    }
    
    success_map = {
        "python": python_success,
        "filesystem": fs_success,
        "fetch": fetch_success,
        "brave": brave_success,
    }

    working_servers = [all_servers[name] for name, success in success_map.items() if success]
    
    if not working_servers:
        logger.error("No MCP servers connected successfully. Exiting.")
        # Consider raising an exception or returning a specific status
        return [] 
    
    # logger.info(f"Successfully connected to {len(working_servers)} out of {len(all_servers)} servers.") # Reduced verbosity
    print(f"{Colors.LOG_INFO}Successfully connected to {len(working_servers)} out of {len(all_servers)} MCP servers.{Colors.ENDC}")

    return working_servers
