import asyncio
import os
import shutil # For checking if npx/uvx exists
import logging
import sys
import venv
import subprocess

# Define ANSI color codes
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Custom Formatter for logging
class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Colors.OKBLUE,
        logging.INFO: Colors.OKGREEN,
        logging.WARNING: Colors.WARNING,
        logging.ERROR: Colors.FAIL,
        logging.CRITICAL: Colors.FAIL + Colors.BOLD,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, Colors.ENDC)
        record.levelname = f"{color}{record.levelname}{Colors.ENDC}"
        record.name = f"{Colors.OKBLUE}{record.name}{Colors.ENDC}"
        # Apply color to the whole message for simplicity here, or customize further
        # record.msg = f"{color}{record.msg}{Colors.ENDC}" # This would color the whole message
        return super().format(record)

# Set up logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Keep our script's logs at INFO level

# Create console handler and set level to debug
ch = logging.StreamHandler()
ch.setLevel(logging.INFO) # Or logging.DEBUG for more verbose output

# Create formatter
formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add formatter to ch
ch.setFormatter(formatter)

# Add ch to logger
logger.addHandler(ch)
logger.propagate = False # Prevent duplicate logs if root logger is also configured

# Disable httpx logging which is causing the messages during typing
logging.getLogger("httpx").setLevel(logging.WARNING)
# Disable OpenAI API logging
logging.getLogger("openai").setLevel(logging.WARNING)

# Import necessary components from the Agents SDK
from agents import Agent, Runner, trace
from agents.mcp.server import MCPServerStdio # Updated import path

# Ensure npx and uvx are available in the system path
if not shutil.which("npx"):
    raise RuntimeError(
        "npx command not found. Please install Node.js and npm from https://nodejs.org/"
    )
if not shutil.which("uvx"):
    raise RuntimeError(
        "uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv"
    )

def install_basic_packages(venv_path):
    """Install basic packages in the virtual environment."""
    logger.info("Installing basic packages in the virtual environment...")
    
    # Determine the pip executable path based on the platform
    if os.name == 'nt':  # Windows
        pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
    else:  # Unix/Linux/Mac
        pip_path = os.path.join(venv_path, "bin", "pip")
    
    # Check if pip exists
    if not os.path.exists(pip_path):
        logger.error(f"Pip not found at {pip_path}")
        return False
    
    # Basic packages to install
    packages = ["feedparser", "requests", "beautifulsoup4", "pandas", "matplotlib"]
    
    try:
        # Install packages
        cmd = [pip_path, "install"] + packages
        logger.info(f"Running command: {' '.join(cmd)}")
        
        # Run the command and capture output
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Print output in real-time
        stdout, stderr = process.communicate()
        
        if stdout:
            logger.info(f"Pip install output: {stdout}")
        if stderr:
            logger.warning(f"Pip install warnings/errors: {stderr}")
        
        if process.returncode != 0:
            logger.error(f"Failed to install packages. Return code: {process.returncode}")
            return False
        
        logger.info("Basic packages installed successfully")
        return True
    except Exception as e:
        logger.error(f"Error installing packages: {e}")
        return False

def ensure_venv_exists(venv_path):
    """Create a virtual environment if it doesn't exist."""
    created_new = False
    
    if os.path.exists(venv_path) and os.path.isdir(venv_path):
        # Check if it's a valid venv by looking for key files
        if os.path.exists(os.path.join(venv_path, "Scripts", "activate")) or \
           os.path.exists(os.path.join(venv_path, "bin", "activate")):
            logger.info(f"Virtual environment already exists at {venv_path}")
            return True, False  # exists, not newly created
    
    # Create the virtual environment
    logger.info(f"Creating virtual environment at {venv_path}...")
    try:
        venv.create(venv_path, with_pip=True)
        logger.info(f"Virtual environment created successfully at {venv_path}")
        created_new = True
        return True, created_new  # success, newly created
    except Exception as e:
        logger.error(f"Failed to create virtual environment: {e}")
        return False, False  # failed, not created

async def test_single_server(server_name, server_instance):
    """Test a single MCP server connection."""
    logger.info(f"Testing connection to {server_name}...")
    try:
        # We can't set timeout directly as it's not supported
        async with server_instance:
            logger.info(f"Successfully connected to {server_name}!")
            return True
    except Exception as e:
        logger.error(f"Failed to connect to {server_name}: {e}")
        return False

async def main():
    # --- 1. Set up the MCP Server ---

    # Get the absolute path to the directory containing sample files
    # Use an explicit path to ensure files are always saved in the correct location
    # Calculate samples_dir relative to the parent directory (the project root)
    parent_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(os.path.dirname(parent_dir), "sample_mcp_files")
    # Ensure this is the absolute path: C:\Users\milanb\code\openaisdkmcp\sample_mcp_files
    samples_dir = os.path.abspath(samples_dir)
    
    logger.info(f"Sample files directory: {samples_dir}")
    # Print the absolute path to verify it's correct
    print(f"{Colors.HEADER}Using sample files directory: {samples_dir}{Colors.ENDC}")
    
    if not os.path.exists(samples_dir):
        logger.warning(f"Sample directory does not exist: {samples_dir}")
        os.makedirs(samples_dir, exist_ok=True)
        logger.info(f"Created sample directory: {samples_dir}")

    # script_dir is the directory of the current script (mcp)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # parent_dir is the project root
    parent_dir = os.path.dirname(script_dir)
    
    # Ensure the virtual environment exists
    venv_path = os.path.join(samples_dir, "venv")
    venv_success, venv_created = ensure_venv_exists(venv_path)
    
    if not venv_success:
        logger.error("Failed to create or verify virtual environment. Code execution may fail.")
        print(f"{Colors.FAIL}Failed to create or verify virtual environment. Code execution may fail.{Colors.ENDC}")
    elif venv_created:
        # If we created a new venv, install basic packages
        logger.info("New virtual environment created, installing basic packages...")
        if install_basic_packages(venv_path):
            logger.info("Basic packages installed successfully in the new virtual environment.")
            print(f"{Colors.OKGREEN}Basic packages installed successfully in the new virtual environment.{Colors.ENDC}")
        else:
            logger.warning("Failed to install basic packages. Some code execution may fail.")
            print(f"{Colors.WARNING}Failed to install basic packages. Some code execution may fail.{Colors.ENDC}")
    
    # Configure the MCP Code Executor server
    logger.info("Configuring MCP Code Executor server...")
    mcp_server_python = MCPServerStdio(
        name="MCP Code Executor", # A name for tracing/logging
        params={
            "command": "node", # Assuming node is in PATH
            # Path to mcp_code_executor is relative to the project root (parent_dir)
            "args": [os.path.join(parent_dir, "mcp_code_executor", "build", "index.js")],
            "env": {
                "CODE_STORAGE_DIR": samples_dir,
                "ENV_TYPE": "venv",
                "VENV_PATH": os.path.join(samples_dir, "venv")
            }
        },
        cache_tools_list=True,
    )
    
    # Configure the filesystem MCP server to run via npx
    logger.info("Configuring Filesystem MCP server...")
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
    logger.info("Configuring Fetch MCP server...")
    mcp_server_fetch = MCPServerStdio(
        name="Fetch Server via uvx",
        params={
            "command": "uvx",
            "args": ["mcp-server-fetch", "--ignore-robots-txt"],
        },
        cache_tools_list=True, # Caching is usually fine for fetch tools too
    )

    # Configure the Brave Search MCP server
    logger.info("Configuring Brave Search MCP server...")
    mcp_server_brave = MCPServerStdio(
        name="Brave Search Server via npx",
        params={
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-brave-search"],
            "env": {"BRAVE_API_KEY": "BSAj4ws7fq7C9gy7K5_9g-y7MPX_gF4"},
        },
        cache_tools_list=True, # Caching is likely safe here too
    )

    # Configure the RSS Feed MCP server
    logger.info("Configuring RSS Feed MCP server...")
    mcp_server_rss = MCPServerStdio(
        name="RSS Feed Server", # A name for tracing/logging
        params={
            "command": "node", # Assuming node is in PATH
            "args": [os.path.join(script_dir, "rss-feed-server", "rss-feed-server", "build", "rss-feed-server", "index.js")],
        },
        cache_tools_list=True,
    )

    # Test each server individually
    logger.info("Testing individual server connections...")
    
    python_success = await test_single_server("MCP Code Executor", mcp_server_python)
    fs_success = await test_single_server("Filesystem Server", mcp_server_filesystem)
    fetch_success = await test_single_server("Fetch Server", mcp_server_fetch)
    brave_success = await test_single_server("Brave Search Server", mcp_server_brave)
    rss_success = await test_single_server("RSS Feed Server", mcp_server_rss)
    
    # Only proceed with servers that connected successfully
    working_servers = []
    if fs_success:
        working_servers.append(mcp_server_filesystem)
    if fetch_success:
        working_servers.append(mcp_server_fetch)
    if brave_success:
        working_servers.append(mcp_server_brave)
    if rss_success:
        working_servers.append(mcp_server_rss)
    if python_success:
        working_servers.append(mcp_server_python)
    
    if not working_servers:
        logger.error("No MCP servers connected successfully. Exiting.")
        return
    
    logger.info(f"Successfully connected to {len(working_servers)} out of 5 servers.")


    # --- 2. Set up the Agent ---
    logger.info("Setting up the Agent...")
    
    # Create an Agent instance with only the working servers
    agent = Agent(
        name="FileFetchSearchRssCodeExecutorAgent", # Updated agent name
        instructions=(
            "You are an agent that can interact with a local filesystem, fetch web content, perform web searches using Brave Search, get RSS feed content, and execute code using the MCP Code Executor. "
            f"When using filesystem tools, always save new files to the directory: {samples_dir} "
            "This is the only directory the filesystem MCP server has access to. "
            "Use the available tools (like list_directory, read_file, write_file, fetch, brave_search, get_rss_feed, execute_code, install_dependencies, check_installed_packages) "
            "to answer questions based on local files, web resources, current events, RSS feeds, or by executing code."
        ),
        mcp_servers=working_servers,  # Only use servers that connected successfully
        # We'll use a default OpenAI model here just for the agent logic,
        # the core interaction is via the MCP tools.
        model="gpt-4o-mini",
    )

    # --- 3. Run the Agent Interactively ---
    logger.info("Starting interactive session...")
    
    # Create a context manager for all working servers
    async def connect_servers():
        for server in working_servers:
            await server.connect()
        return working_servers
        
    async def cleanup_servers():
        for server in working_servers:
            try:
                await server.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up server {server.name}: {e}")
    
    try:
        # Connect all working servers
        await connect_servers()
        
        print(f"{Colors.OKGREEN}MCP Servers connected ({len(working_servers)} of 5). Starting interactive chat...{Colors.ENDC}")
        print(f"{Colors.OKCYAN}Type 'quit' or 'exit' to end the session.{Colors.ENDC}")

        conversation_history_items = [] # Initialize conversation history

        # Optional: Wrap the entire interactive session in a trace
        with trace("MCP Interactive Session"): # Updated trace name
            while True:
                try:
                    # Get user input
                    user_input_text = input(f"\n{Colors.BOLD}You: {Colors.ENDC}")
                    if user_input_text.lower() in ["quit", "exit"]:
                        print(f"{Colors.WARNING}Exiting chat.{Colors.ENDC}")
                        break

                    # Prepare the input for the current turn by appending the new user message to the history
                    current_turn_input = conversation_history_items + [{"role": "user", "content": user_input_text}]

                    # Run the agent with the full conversation history for this turn
                    result = await Runner.run(
                        starting_agent=agent,
                        input=current_turn_input,
                    )

                    # Update conversation_history_items for the next turn using the result
                    conversation_history_items = result.to_input_list()

                    # --- Extract and Print Tool Usage and Details from raw_responses ---
                    tool_names_used = set()
                    tool_details = []
                    
                    if hasattr(result, 'raw_responses') and result.raw_responses:
                        for response in result.raw_responses:
                            # Check if the response object has an 'output' attribute and it's a list
                            if hasattr(response, 'output') and isinstance(response.output, list):
                                for output_item in response.output:
                                    # Check if the item looks like a tool call
                                    if hasattr(output_item, 'name') and \
                                       hasattr(output_item, 'type') and \
                                       getattr(output_item, 'type') == 'function_call':
                                        tool_name = getattr(output_item, 'name', None)
                                        if tool_name:
                                            tool_names_used.add(str(tool_name))
                                            
                                            # For code execution tools, extract and log more details
                                            if tool_name in ['execute_code', 'install_dependencies', 'check_installed_packages']:
                                                if hasattr(output_item, 'arguments') and output_item.arguments:
                                                    tool_details.append({
                                                        'tool': tool_name,
                                                        'arguments': output_item.arguments
                                                    })
                            
                            # Check for tool responses
                            if hasattr(response, 'content') and isinstance(response.content, list):
                                for content_item in response.content:
                                    if hasattr(content_item, 'text') and content_item.text:
                                        try:
                                            # Try to parse as JSON to extract structured information
                                            import json
                                            response_data = json.loads(content_item.text)
                                            
                                            # Ensure response_data is a dictionary before accessing keys
                                            if isinstance(response_data, dict):
                                                # If this is a code execution response, log it
                                                if 'status' in response_data and ('output' in response_data or 'error' in response_data):
                                                    print(f"\n{Colors.HEADER}--- Code Execution Result ---{Colors.ENDC}")
                                                    print(f"{Colors.BOLD}Status:{Colors.ENDC} {response_data['status']}")
                                                    
                                                    if 'file_path' in response_data:
                                                        print(f"{Colors.BOLD}File:{Colors.ENDC} {response_data['file_path']}")
                                                    
                                                    if 'output' in response_data:
                                                        print(f"{Colors.BOLD}Output:{Colors.ENDC}")
                                                        print(f"{Colors.OKGREEN}{response_data['output']}{Colors.ENDC}")
                                                    
                                                    if 'error' in response_data:
                                                        print(f"{Colors.BOLD}Error:{Colors.ENDC}")
                                                        print(f"{Colors.FAIL}{response_data['error']}{Colors.ENDC}")
                                                    
                                                    print(f"{Colors.HEADER}---------------------------{Colors.ENDC}")
                                            else:
                                                # Handle case where response_data is not a dictionary
                                                print(f"\n{Colors.HEADER}--- Code Execution Result ---{Colors.ENDC}")
                                                print(f"{Colors.BOLD}Response:{Colors.ENDC}")
                                                print(f"{Colors.OKGREEN}{response_data}{Colors.ENDC}")
                                                print(f"{Colors.HEADER}---------------------------{Colors.ENDC}")
                                        except Exception:
                                            # Not JSON or not a code execution response, ignore
                                            pass

                    if tool_names_used:
                        print(f"\n{Colors.OKCYAN}[Tools Used: {', '.join(sorted(list(tool_names_used)))}]{Colors.ENDC}")
                    
                    # Log detailed tool usage for debugging
                    for detail in tool_details:
                        if detail['tool'] == 'execute_code' and 'code' in detail['arguments']:
                            print(f"\n{Colors.HEADER}--- Code Executed ---{Colors.ENDC}")
                            print(f"{Colors.OKBLUE}{detail['arguments']['code']}{Colors.ENDC}")
                            print(f"{Colors.HEADER}-------------------{Colors.ENDC}")
                        elif detail['tool'] == 'install_dependencies' and 'packages' in detail['arguments']:
                            print(f"\n{Colors.HEADER}--- Packages Installed ---{Colors.ENDC}")
                            print(f"{Colors.OKBLUE}{', '.join(detail['arguments']['packages'])}{Colors.ENDC}")
                            print(f"{Colors.HEADER}------------------------{Colors.ENDC}")
                    # --- End Extract and Print ---

                    # Print the agent's final response
                    print(f"\n{Colors.BOLD}Agent:{Colors.ENDC}")
                    print(f"{Colors.OKBLUE}{result.final_output}{Colors.ENDC}")

                except KeyboardInterrupt:
                    print(f"\n{Colors.WARNING}Exiting chat due to interrupt.{Colors.ENDC}")
                    break
                except Exception as e:
                    print(f"\n{Colors.FAIL}An error occurred: {e}{Colors.ENDC}")
                    # Optionally, decide if the loop should continue or break on error
    except Exception as e:
        logger.error(f"Error during interactive session: {e}")
    finally:
        # Clean up servers
        await cleanup_servers()
        print(f"\n{Colors.OKGREEN}Chat session complete. MCP Servers disconnected.{Colors.ENDC}")

if __name__ == "__main__":
    # Use try-except to catch potential issues during async run, like initial connection errors
    try:
        asyncio.run(main())
    except Exception as e:
        logger.exception(f"An error occurred during script execution: {e}")
        print(f"{Colors.FAIL}An error occurred during script execution: {e}{Colors.ENDC}")
