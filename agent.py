import asyncio
import os
import shutil # For checking if npx/uvx exists
import logging
import sys
from dotenv import load_dotenv
from contextlib import asynccontextmanager # Import asynccontextmanager

# Import necessary components from the Agents SDK
from agents import Runner, trace # Agent and MCPServerStdio will be imported via new modules

# Import from our new modules
from mcp_utils import Colors, setup_colored_logger, install_basic_packages, ensure_venv_exists
from mcp_server_config import configure_servers # UPDATED IMPORT
from mcp_agent_setup import setup_agent

# Set up logging using the utility function
logger = setup_colored_logger(__name__)

# Disable httpx logging which is causing the messages during typing
logging.getLogger("httpx").setLevel(logging.WARNING)
# Disable OpenAI API logging
logging.getLogger("openai").setLevel(logging.WARNING)

# Load environment variables from .env file
load_dotenv()

# Ensure npx and uvx are available in the system path
if not shutil.which("npx"):
    logger.error("npx command not found. Please install Node.js and npm from https://nodejs.org/")
    raise RuntimeError("npx command not found.")
if not shutil.which("uvx"):
    logger.error("uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv")
    raise RuntimeError("uvx command not found.")

async def main():
    # --- 1. Initial Setup ---
    script_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(script_dir, "sample_mcp_files")
    samples_dir = os.path.abspath(samples_dir)
    
    # logger.info(f"Sample files directory: {samples_dir}") # Reduced verbosity
    print(f"{Colors.HEADER}Using sample files directory: {samples_dir}{Colors.ENDC}") # Keep this one for clarity

    if not os.path.exists(samples_dir):
        logger.warning(f"Sample directory does not exist: {samples_dir}, creating it.")
        os.makedirs(samples_dir, exist_ok=True)
        # logger.info(f"Created sample directory: {samples_dir}") # Reduced verbosity

    # Ensure the virtual environment exists and install packages if new
    venv_path = os.path.join(samples_dir, "venv")
    venv_success, venv_created = ensure_venv_exists(logger, venv_path)
    
    if not venv_success:
        logger.error("Failed to create or verify virtual environment. Code execution may fail.")
        print(f"{Colors.LOG_ERROR}Failed to create or verify virtual environment. Code execution may fail.{Colors.ENDC}")
    elif venv_created:
        # logger.info("New virtual environment created, installing basic packages...") # Reduced verbosity
        if install_basic_packages(logger, venv_path): # Pass logger to install_basic_packages
            logger.info("Basic packages installed successfully in the new virtual environment.")
            # print(f"{Colors.LOG_INFO}Basic packages installed successfully in the new virtual environment.{Colors.ENDC}") # Reduced verbosity
        else:
            logger.warning("Failed to install basic packages. Some code execution may fail.")
            print(f"{Colors.LOG_WARNING}Failed to install basic packages. Some code execution may fail.{Colors.ENDC}")

    # --- 2. Configure MCP Servers ---
    configured_server_instances = await configure_servers(logger, script_dir, samples_dir)
    
    # --- 2a. Connect to Configured Servers ---
    successfully_connected_servers = []
    if configured_server_instances:
        logger.info(f"Attempting to connect to {len(configured_server_instances)} configured MCP server(s)...")
        for server_instance in configured_server_instances:
            try:
                await server_instance.connect()
                logger.info(f"Successfully connected to {server_instance.name}.")
                print(f"{Colors.LOG_INFO}Successfully connected to {server_instance.name}.{Colors.ENDC}")
                successfully_connected_servers.append(server_instance)
            except Exception as e:
                logger.error(f"Failed to connect to {server_instance.name}: {e}")
                print(f"{Colors.LOG_ERROR}Failed to connect to {server_instance.name}: {e}{Colors.ENDC}")
                # Attempt to clean up if connection failed partway
                try:
                    await server_instance.cleanup()
                except Exception as cleanup_e:
                    logger.error(f"Error during cleanup of failed server {server_instance.name}: {cleanup_e}")
    
    if not successfully_connected_servers:
        logger.error("No MCP servers connected successfully. Exiting application.")
        print(f"{Colors.LOG_ERROR}No MCP servers connected successfully. Exiting application.{Colors.ENDC}")
        return # Exit if no servers are working
    
    logger.info(f"Total successfully connected servers: {len(successfully_connected_servers)} out of {len(configured_server_instances)} configured.")
    print(f"{Colors.LOG_INFO}Total successfully connected servers: {len(successfully_connected_servers)} out of {len(configured_server_instances)} configured. Starting interactive chat...{Colors.ENDC}")

    # --- 3. Set up the Agent ---
    agent = setup_agent(logger, successfully_connected_servers, samples_dir) # Use successfully_connected_servers
    
    # --- 4. Run the Agent Interactively ---
    # logger.info("Starting interactive session...") # Reduced verbosity
    
    # Context manager for server connections
    @asynccontextmanager # Decorate with asynccontextmanager
    async def manage_server_connections(servers_to_manage): # servers_to_manage are already connected
        # Connections are now handled before this context manager is entered.
        # logger.info(f"All {len(servers_to_manage)} working MCP servers are already connected.") # Redundant with previous log
        try:
            yield # This is where the interactive loop will run
        finally:
            logger.info(f"Cleaning up {len(servers_to_manage)} server connection(s)...")
            for server in servers_to_manage:
                try:
                    await server.cleanup()
                    logger.info(f"Successfully cleaned up server: {server.name}")
                except Exception as e:
                    logger.error(f"Error cleaning up server {server.name}: {e}")
            logger.info("All server cleanups attempted.")

    async with manage_server_connections(successfully_connected_servers): # Use successfully_connected_servers
        print(f"{Colors.SYSTEM_INFO}Type 'quit' or 'exit' to end the session.{Colors.ENDC}")
        conversation_history_items = []

        with trace("MCP Interactive Session"):
            while True:
                try:
                    user_input_text = input(f"\n{Colors.BOLD}{Colors.USER_PROMPT}You: {Colors.ENDC}")
                    if user_input_text.lower() in ["quit", "exit"]:
                        print(f"{Colors.SYSTEM_INFO}Exiting chat.{Colors.ENDC}")
                        break

                    current_turn_input = conversation_history_items + [{"role": "user", "content": user_input_text}]
                    result = await Runner.run(starting_agent=agent, input=current_turn_input)
                    conversation_history_items = result.to_input_list()

                    # --- Extract and Print Tool Usage and Details ---
                    tool_names_used = set()
                    tool_details = []
                    
                    if hasattr(result, 'raw_responses') and result.raw_responses:
                        for response in result.raw_responses:
                            if hasattr(response, 'output') and isinstance(response.output, list):
                                for output_item in response.output:
                                    if hasattr(output_item, 'name') and hasattr(output_item, 'type') and getattr(output_item, 'type') == 'function_call':
                                        tool_name = getattr(output_item, 'name', None)
                                        if tool_name:
                                            tool_names_used.add(str(tool_name))
                                            if tool_name in ['execute_code', 'install_dependencies', 'check_installed_packages']:
                                                if hasattr(output_item, 'arguments') and output_item.arguments:
                                                    try:
                                                        import json
                                                        parsed_args = json.loads(output_item.arguments)
                                                        tool_details.append({'tool': tool_name, 'arguments': parsed_args})
                                                    except json.JSONDecodeError:
                                                        logger.error(f"Failed to parse tool arguments for {tool_name}: {output_item.arguments}")
                                                        tool_details.append({'tool': tool_name, 'arguments': {'raw_arguments_error': output_item.arguments}})
                            
                            if hasattr(response, 'content') and isinstance(response.content, list):
                                for content_item in response.content:
                                    if hasattr(content_item, 'text') and content_item.text:
                                        try:
                                            import json
                                            response_data = json.loads(content_item.text)
                                            if isinstance(response_data, dict):
                                                if 'status' in response_data and ('output' in response_data or 'error' in response_data):
                                                    print(f"\n{Colors.HEADER}--- Code Execution Result ---{Colors.ENDC}")
                                                    print(f"{Colors.BOLD}Status:{Colors.ENDC} {response_data['status']}")
                                                    if 'file_path' in response_data: print(f"{Colors.BOLD}File:{Colors.ENDC} {response_data['file_path']}")
                                                    if 'output' in response_data: print(f"{Colors.BOLD}Output:{Colors.ENDC}\n  {Colors.CODE_OUTPUT}{response_data['output']}{Colors.ENDC}")
                                                    if 'error' in response_data: print(f"{Colors.BOLD}Error:{Colors.ENDC}\n  {Colors.CODE_ERROR}{response_data['error']}{Colors.ENDC}")
                                                    print(f"{Colors.HEADER}---------------------------{Colors.ENDC}")
                                            else: # Non-dict JSON response
                                                print(f"\n{Colors.HEADER}--- Tool Response ---{Colors.ENDC}")
                                                print(f"  {Colors.CODE_OUTPUT}{response_data}{Colors.ENDC}")
                                                print(f"{Colors.HEADER}-------------------{Colors.ENDC}")
                                        except Exception:
                                            pass # Not JSON or not a code execution response

                    if tool_names_used:
                        print(f"\n{Colors.TOOL_INFO}[Tools Used: {', '.join(sorted(list(tool_names_used)))}]{Colors.ENDC}")
                    
                    for detail in tool_details:
                        if detail['tool'] == 'execute_code' and 'code' in detail['arguments']:
                            print(f"\n{Colors.TOOL_INFO}--- Code Executed ---{Colors.ENDC}")
                            print(f"  {Colors.AGENT_MESSAGE}{detail['arguments']['code']}{Colors.ENDC}")
                            print(f"{Colors.TOOL_INFO}-------------------{Colors.ENDC}")
                        elif detail['tool'] == 'install_dependencies' and 'packages' in detail['arguments']:
                            print(f"\n{Colors.TOOL_INFO}--- Packages Installed ---{Colors.ENDC}")
                            print(f"  {Colors.AGENT_MESSAGE}{', '.join(detail['arguments']['packages'])}{Colors.ENDC}")
                            print(f"{Colors.TOOL_INFO}------------------------{Colors.ENDC}")
                    # --- End Extract and Print ---

                    print(f"\n{Colors.BOLD}{Colors.AGENT_PROMPT}Agent: {Colors.ENDC}")
                    print(f"{Colors.AGENT_MESSAGE}{result.final_output}{Colors.ENDC}")

                except KeyboardInterrupt:
                    print(f"\n{Colors.SYSTEM_INFO}Exiting chat due to interrupt.{Colors.ENDC}")
                    break
                except Exception as e:
                    logger.exception("An error occurred during the interactive loop.") # Log with stack trace
                    print(f"\n{Colors.LOG_ERROR}An error occurred: {e}{Colors.ENDC}")
    
    # logger.info("Chat session complete.") # Reduced verbosity
    print(f"\n{Colors.LOG_INFO}Chat session complete. MCP Servers will be disconnected.{Colors.ENDC}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e: # Catch specific RuntimeErrors like npx/uvx not found
        logger.error(f"Runtime error during script initialization: {e}")
        print(f"{Colors.LOG_ERROR}Runtime error: {e}{Colors.ENDC}")
    except Exception as e:
        logger.exception(f"An unexpected error occurred during script execution: {e}")
        print(f"{Colors.LOG_ERROR}An unexpected error occurred: {e}{Colors.ENDC}")
