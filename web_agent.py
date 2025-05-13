import asyncio
import os
import shutil
import logging
import sys
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import threading
import signal # For handling KeyboardInterrupt gracefully

from flask import Flask, request, jsonify, send_from_directory
import concurrent.futures # For TimeoutError with future.result()

from agents import Runner, trace, set_tracing_disabled # Import set_tracing_disabled
from mcp_utils import Colors, setup_colored_logger, install_basic_packages, ensure_venv_exists
from mcp_server_config import configure_servers
from mcp_agent_setup import setup_agent

# Attempt to disable tracing globally
set_tracing_disabled(True)

main_event_loop = None # Will store the main asyncio event loop

logger = setup_colored_logger(__name__)

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING) # Silence Flask's default server logs for cleaner output

load_dotenv()

if not shutil.which("npx"):
    logger.error("npx command not found. Please install Node.js and npm from https://nodejs.org/")
    raise RuntimeError("npx command not found.")
if not shutil.which("uvx"):
    logger.error("uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv")
    raise RuntimeError("uvx command not found.")

# --- Flask App Setup ---
app = Flask(__name__, static_folder=None) # Disable default static folder
frontend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend")

# Global variables to store agent and conversation history (simplification)
agent_instance = None
conversation_history_items = []
mcp_servers_to_manage = [] # To hold servers for cleanup

@app.route('/')
def serve_index():
    return send_from_directory(frontend_dir, 'index.html')

@app.route('/<path:path>')
def serve_static_files(path):
    return send_from_directory(frontend_dir, path)

@app.route('/api/chat', methods=['POST'])
def chat_endpoint(): # Changed to sync def
    global agent_instance, conversation_history_items, main_event_loop # Added main_event_loop
    if not agent_instance:
        return jsonify({"error": "Agent not initialized"}), 500
    if not main_event_loop: # Safety check
        logger.error("Main event loop not available for chat endpoint.")
        return jsonify({"error": "Main event loop not available"}), 500

    data = request.get_json()
    user_message = data.get('message')

    if not user_message:
        return jsonify({"error": "No message provided"}), 400

    current_turn_input = conversation_history_items + [{"role": "user", "content": user_message}]
    
    async def run_agent_async(): # Define an inner async function to run the agent logic
        # Since set_tracing_disabled(True) is active, this trace context should be a no-op.
        # Kept for consistency if tracing is re-enabled.
        with trace("WebAgentChatRequest") as web_trace_span:
            result = await Runner.run(starting_agent=agent_instance, input=current_turn_input)

            # ---- START DEBUGGING ----
            logger.info("--- Agent Run Result Inspection (Threadsafe Call) ---")
            logger.info(f"Type of result: {type(result)}")
            if hasattr(result, 'final_output'):
                logger.info(f"Result final_output: {result.final_output}")
            else:
                logger.info("Result has no final_output attribute.")

            if hasattr(result, 'raw_responses') and result.raw_responses:
                logger.info(f"Number of raw_responses: {len(result.raw_responses)}")
                for i, raw_resp_msg in enumerate(result.raw_responses):
                    logger.info(f"--- Raw Response Message {i} ---")
                    logger.info(f"Type of raw_resp_msg: {type(raw_resp_msg)}")
                    if hasattr(raw_resp_msg, 'role'):
                        logger.info(f"  raw_resp_msg.role: {getattr(raw_resp_msg, 'role')}")
                    if hasattr(raw_resp_msg, 'content'):
                        logger.info(f"  raw_resp_msg.content: {getattr(raw_resp_msg, 'content')}")
                    if hasattr(raw_resp_msg, 'name'):
                        logger.info(f"  raw_resp_msg.name: {getattr(raw_resp_msg, 'name')}")
                    if hasattr(raw_resp_msg, 'tool_call_id'):
                        logger.info(f"  raw_resp_msg.tool_call_id: {getattr(raw_resp_msg, 'tool_call_id')}")
                    if hasattr(raw_resp_msg, 'tool_calls') and getattr(raw_resp_msg, 'tool_calls'):
                        logger.info(f"  raw_resp_msg has {len(getattr(raw_resp_msg, 'tool_calls'))} tool_calls:")
                        for tc_idx, tool_call in enumerate(getattr(raw_resp_msg, 'tool_calls')):
                            logger.info(f"    Tool Call {tc_idx}:")
                            if hasattr(tool_call, 'name'):
                                logger.info(f"      Name: {getattr(tool_call, 'name')}")
                            if hasattr(tool_call, 'args'):
                                logger.info(f"      Args: {getattr(tool_call, 'args')}")
                            if hasattr(tool_call, 'id'):
                                logger.info(f"      ID: {getattr(tool_call, 'id')}")
            else:
                logger.info("No raw_responses found in result or raw_responses is empty.")
            logger.info("--- End Agent Run Result Inspection (Threadsafe Call) ---")
            # ---- END DEBUGGING ----
            
            # With tracing disabled, web_trace_span is a NoOpTrace and does not have set_metadata.
            # These lines are removed as they would cause an error.
            # if hasattr(result, 'raw_responses'):
            #      web_trace_span.set_metadata({"num_raw_responses": len(result.raw_responses) if result.raw_responses else 0})
            # if hasattr(result, 'final_output'):
            #      web_trace_span.set_metadata({"final_output_length": len(result.final_output) if result.final_output else 0})
            
            return result

    try:
        # Schedule the inner async function on the main event loop and wait for its result
        future = asyncio.run_coroutine_threadsafe(run_agent_async(), main_event_loop)
        result = future.result(timeout=70) # Wait for the result with a timeout

        conversation_history_items = result.to_input_list() # Update history
        return jsonify({"reply": result.final_output})
    except concurrent.futures.TimeoutError: # Catch timeout from future.result()
        logger.error("Timeout waiting for agent processing in main loop via run_coroutine_threadsafe.")
        return jsonify({"error": "Agent processing timed out in main loop"}), 500
    except Exception as e:
        # This will catch other exceptions from run_agent_async or run_coroutine_threadsafe
        logger.error(f"Error during agent processing (via run_coroutine_threadsafe): {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500

# --- Original Async Main Logic (Adapted) ---
async def initialize_agent_and_servers():
    global agent_instance, conversation_history_items, mcp_servers_to_manage

    script_dir = os.path.dirname(os.path.abspath(__file__))
    samples_dir = os.path.join(script_dir, "sample_mcp_files")
    samples_dir = os.path.abspath(samples_dir)
    
    print(f"{Colors.HEADER}Using sample files directory: {samples_dir}{Colors.ENDC}")

    if not os.path.exists(samples_dir):
        logger.warning(f"Sample directory does not exist: {samples_dir}, creating it.")
        os.makedirs(samples_dir, exist_ok=True)

    venv_path = os.path.join(samples_dir, "venv")
    venv_success, venv_created = ensure_venv_exists(logger, venv_path)
    
    if not venv_success:
        logger.error("Failed to create or verify virtual environment.")
    elif venv_created:
        if install_basic_packages(logger, venv_path):
            logger.info("Basic packages installed successfully.")
        else:
            logger.warning("Failed to install basic packages.")

    configured_server_instances = await configure_servers(logger, script_dir, samples_dir)
    
    successfully_connected_servers = []
    if configured_server_instances:
        logger.info(f"Attempting to connect to {len(configured_server_instances)} configured MCP server(s)...")
        for server_instance_item in configured_server_instances: # Renamed to avoid conflict
            try:
                await server_instance_item.connect()
                logger.info(f"Successfully connected to {server_instance_item.name}.")
                print(f"{Colors.LOG_INFO}Successfully connected to {server_instance_item.name}.{Colors.ENDC}")
                successfully_connected_servers.append(server_instance_item)
            except Exception as e:
                logger.error(f"Failed to connect to {server_instance_item.name}: {e}")
                print(f"{Colors.LOG_ERROR}Failed to connect to {server_instance_item.name}: {e}{Colors.ENDC}")
                try:
                    await server_instance_item.cleanup()
                except Exception as cleanup_e:
                    logger.error(f"Error during cleanup of failed server {server_instance_item.name}: {cleanup_e}")
    
    if not successfully_connected_servers:
        logger.error("No MCP servers connected successfully. Web app might not function correctly.")
        print(f"{Colors.LOG_ERROR}No MCP servers connected successfully. Web app might not function correctly.{Colors.ENDC}")
        # Decide if to exit or run with limited functionality
    else:
        logger.info(f"Total successfully connected servers: {len(successfully_connected_servers)}")
        print(f"{Colors.LOG_INFO}Total successfully connected servers: {len(successfully_connected_servers)}.{Colors.ENDC}")

    mcp_servers_to_manage = successfully_connected_servers # Store for cleanup
    agent_instance = setup_agent(logger, successfully_connected_servers, samples_dir)
    conversation_history_items = [] # Initialize conversation history for the web app

    print(f"{Colors.SYSTEM_INFO}Agent and servers initialized. Flask server will start shortly.{Colors.ENDC}")

def run_flask_app_sync(): # Renamed to indicate it's run synchronously in a thread
    # Werkzeug's reloader (debug=True or use_reloader=True) should not be used
    # when Flask is run in a thread managed by an external asyncio loop,
    # as it can lead to issues with process management and signal handling.
    print(f"{Colors.LOG_INFO}Starting Flask web server on http://127.0.0.1:5001{Colors.ENDC}")
    print(f"{Colors.SYSTEM_INFO}Open your browser and navigate to http://127.0.0.1:5001 to use the agent.{Colors.ENDC}")
    try:
        app.run(host='0.0.0.0', port=5001, debug=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Flask app encountered an error: {e}", exc_info=True)


async def cleanup_mcp_servers():
    global mcp_servers_to_manage
    if not mcp_servers_to_manage:
        logger.info("No MCP servers to clean up.")
        return
        
    logger.info(f"Cleaning up {len(mcp_servers_to_manage)} server connection(s)...")
    for server in mcp_servers_to_manage:
        try:
            if hasattr(server, 'is_connected') and not server.is_connected(): # Check if server has a connected status
                 logger.info(f"Server {server.name} is already disconnected or was never connected.")
                 continue
            await server.cleanup()
            logger.info(f"Successfully cleaned up server: {server.name}")
        except Exception as e:
            logger.error(f"Error cleaning up server {server.name}: {e}", exc_info=True)
    logger.info("All server cleanups attempted.")


async def application_lifecycle():
    global main_event_loop # Declare that we intend to modify the global variable
    shutdown_event = asyncio.Event()

    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, initiating shutdown...")
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    # For Windows, signal.SIGINT is available. signal.SIGTERM might not be.
    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler) # Ctrl+C

    flask_thread = None
    try:
        main_event_loop = asyncio.get_running_loop() # Get and store the current event loop
        await initialize_agent_and_servers()

        # Start Flask in a daemon thread
        # Daemon threads automatically exit when the main program exits
        flask_thread = threading.Thread(target=run_flask_app_sync, daemon=True)
        flask_thread.start()
        
        logger.info("Application started. Waiting for shutdown signal (Ctrl+C)...")
        await shutdown_event.wait() # Keep the main async loop alive until shutdown_event is set

    except Exception as e:
        logger.error(f"An error occurred during application lifecycle: {e}", exc_info=True)
    finally:
        logger.info("Application shutting down. Cleaning up MCP servers...")
        await cleanup_mcp_servers()
        
        if flask_thread and flask_thread.is_alive():
            logger.info("Flask thread is still alive. Note: Programmatic shutdown of Werkzeug dev server is complex.")
            # Ideally, we'd signal Flask to stop, but app.run() is blocking.
            # Since it's a daemon thread, it will exit when the main thread exits.
        
        logger.info("Application shutdown complete.")


if __name__ == "__main__":
    try:
        asyncio.run(application_lifecycle())
    except KeyboardInterrupt: # This might be caught by the signal handler instead
        logger.info("KeyboardInterrupt caught in __main__, application should be shutting down via signal handler.")
    except Exception as e:
        logger.critical(f"Critical error in __main__: {e}", exc_info=True)
