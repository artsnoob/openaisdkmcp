import asyncio
import os
import shutil
import logging
import sys
import json
from dotenv import load_dotenv # Keep this import at the top
from contextlib import asynccontextmanager
# tty, termios, tiktoken are not directly needed here anymore, handled by submodules
import openai # Import the openai module itself for accessing openai.BadRequestError
from openai import OpenAI # Ensure openai is imported to catch openai.BadRequestError
from openai.types.responses import ResponseTextDeltaEvent # For streaming

# --- EARLY .ENV LOADING ---
# Determine the path to the .env file relative to this script and load it EARLY.
# This needs to happen BEFORE other local modules are imported if they rely on os.getenv at module level.
_script_dir_for_dotenv = os.path.dirname(os.path.abspath(__file__))
_dotenv_path_for_dotenv = os.path.join(_script_dir_for_dotenv, ".env")
_loaded_dotenv_message = ""
if os.path.exists(_dotenv_path_for_dotenv):
    load_dotenv(dotenv_path=_dotenv_path_for_dotenv, override=True)
    _loaded_dotenv_message = f"[INFO] Early loaded .env file from: {_dotenv_path_for_dotenv} (with override)"
else:
    load_dotenv(override=True) # Attempt to load from default location if specific path not found
    _loaded_dotenv_message = f"[WARNING] Early .env file not found at: {_dotenv_path_for_dotenv}. Attempted default load (with override)."
# We'll print this message after logger is configured, or use basic print if logger fails.

# --- LOCAL MODULE IMPORTS (AFTER .ENV LOAD) ---
from agents import Runner, trace # Assuming Runner is the correct class providing the run method
from mcp_local_modules.mcp_utils import Colors, setup_colored_logger, install_basic_packages, ensure_venv_exists, indent_multiline_text
from mcp_local_modules.mcp_server_config import configure_servers
from mcp_local_modules.mcp_agent_setup import setup_agent
from cli import cli_config # Now this should pick up the env var correctly
from cli.cli_ui import select_model_interactive
from cli import cli_model_handler

# --- LOGGER SETUP ---
logger = setup_colored_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

# Print the dotenv loading message using the configured logger
if _loaded_dotenv_message:
    if "[INFO]" in _loaded_dotenv_message:
        logger.info(_loaded_dotenv_message.replace("[INFO] ", ""))
    else:
        logger.warning(_loaded_dotenv_message.replace("[WARNING] ", ""))

# --- CONFIGURATION CHECKS (Now cli_config should have the correct values) ---
if not cli_config.OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY not found in .env file. Please add it.")
    print(f"{Colors.LOG_ERROR}OPENROUTER_API_KEY not found in .env file. Please add it.{Colors.ENDC}")
    sys.exit(1)

# Check for npx and uvx
if not shutil.which("npx"):
    logger.error("npx command not found. Please install Node.js and npm from https://nodejs.org/")
    print(f"{Colors.LOG_ERROR}npx command not found. Please install Node.js and npm.{Colors.ENDC}")
    sys.exit(1)
if not shutil.which("uvx"):
    logger.error("uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv")
    print(f"{Colors.LOG_ERROR}uvx command not found. Please install uv.{Colors.ENDC}")
    sys.exit(1)

# Global variables for the agent and its instructions text.
# These are modified by the model handler and setup_agent.
agent = None
agent_instructions_text: str = ""

# Function to handle Ollama models directly without using the Agent framework
async def handle_ollama_chat(model_name, msgs, logger_instance, enc):
    """
    Handles chat with Ollama models directly using the OpenAI client.
    
    Args:
        model_name: The name of the Ollama model (e.g., "phi4-mini:latest")
        msgs: The conversation history
        logger_instance: The logger instance
        enc: The tokenizer for token counting
        
    Returns:
        A tuple containing:
        - The assistant's response
        - The number of prompt tokens
        - The number of completion tokens
    """
    # Create a client for Ollama
    client = OpenAI(
        base_url=cli_config.OLLAMA_BASE_URL,
        api_key="ollama"  # Dummy API key
    )
    
    logger_instance.info(f"Using direct Ollama chat with model: {model_name}")
    
    # Convert the message format to what Ollama expects
    converted_msgs = []
    for msg in msgs:
        # Check if the message has the expected format
        if isinstance(msg, dict) and "role" in msg and "content" in msg:
            # Check if content is a string
            if isinstance(msg["content"], str):
                converted_msgs.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
            # Check if content is a list (complex message format)
            elif isinstance(msg["content"], list):
                # Extract text content from the list
                text_content = ""
                for content_item in msg["content"]:
                    if isinstance(content_item, dict) and content_item.get("type") == "text":
                        text_content += content_item.get("text", "")
                
                if text_content:
                    converted_msgs.append({
                        "role": msg["role"],
                        "content": text_content
                    })
    
    logger_instance.info(f"Converted {len(msgs)} messages to {len(converted_msgs)} messages for Ollama")
    
    try:
        # Call the Ollama API with the converted messages
        response = client.chat.completions.create(
            model=model_name,
            messages=converted_msgs,
            stream=False
        )
        
        # Get the assistant's response
        assistant_message = response.choices[0].message.content
        
        # Count tokens
        prompt_tokens = 0
        completion_tokens = 0
        
        if enc:
            # Count prompt tokens
            for msg in msgs:
                if isinstance(msg.get("content"), str):
                    prompt_tokens += len(enc.encode(msg.get("content")))
            
            # Count completion tokens
            completion_tokens = len(enc.encode(assistant_message))
        
        return assistant_message, prompt_tokens, completion_tokens
    
    except Exception as e:
        logger_instance.error(f"Error in direct Ollama chat: {e}")
        if hasattr(e, 'body'):
            logger_instance.error(f"Error details: {e.body}")
        raise

# Helper function to print details of a single raw model response step
def print_single_raw_response_step(step_number, raw_model_response, Colors_obj, logger_obj, indent_func, json_module):
    """
    Prints the details of a single raw model response step.
    step_number should be 1-based.
    """
    print(f"{Colors_obj.HEADER}Step {step_number}: Raw Model Response Type: {type(raw_model_response).__name__}{Colors_obj.ENDC}")

    if not hasattr(raw_model_response, 'output') or not isinstance(raw_model_response.output, list):
        print(f"{Colors_obj.LOG_WARNING}  Skipping raw_model_response: 'output' attribute missing or not a list.{Colors_obj.ENDC}")
        try: print(f"{Colors_obj.LOG_WARNING}    Preview: {str(raw_model_response)[:200]}...{Colors_obj.ENDC}")
        except: pass
        return

    for output_item_idx, output_item in enumerate(raw_model_response.output):
        print(f"{Colors_obj.SYSTEM_INFO}  Output Item [{output_item_idx+1}] Type: {type(output_item).__name__}{Colors_obj.ENDC}")
        item_processed_for_verbose = False

        if hasattr(output_item, 'arguments'): 
            item_processed_for_verbose = True
            tool_name_attr = getattr(output_item, 'name', None)
            if tool_name_attr is None: 
                if hasattr(output_item, 'function_call') and hasattr(output_item.function_call, 'name'):
                    tool_name_attr = output_item.function_call.name
                elif hasattr(output_item, 'tool_name'): 
                    tool_name_attr = output_item.tool_name

            # step_number is 1-based, so use step_number-1 for 0-based indexing if needed for ID generation
            tool_id_attr = getattr(output_item, 'id', f"generated_id_{step_number-1}_{output_item_idx}")
            tool_args_str = output_item.arguments

            print(f"{Colors_obj.TOOL_INFO}  Assistant Action (from Raw Response): Call Tool{Colors_obj.ENDC}")
            print(f"{Colors_obj.TOOL_INFO}    Tool Call ID: {tool_id_attr}{Colors_obj.ENDC}")
            print(f"{Colors_obj.TOOL_INFO}    Tool Name: {Colors_obj.BOLD}{tool_name_attr or 'UnknownToolName'}{Colors_obj.ENDC}")
            
            parsed_tool_args = None
            try:
                if isinstance(tool_args_str, str):
                    parsed_tool_args = json_module.loads(tool_args_str)
                elif isinstance(tool_args_str, dict): 
                    parsed_tool_args = tool_args_str
                else:
                    parsed_tool_args = {'raw_arguments': tool_args_str}
                
                pretty_args = json_module.dumps(parsed_tool_args, indent=2, ensure_ascii=False)
                print(f"{Colors_obj.AGENT_MESSAGE}    Arguments:{Colors_obj.ENDC}\n{Colors_obj.CODE_OUTPUT}{indent_func(pretty_args, '      ')}{Colors_obj.ENDC}")

                is_execute_code = tool_name_attr == 'execute_code' or \
                                    (not tool_name_attr and isinstance(parsed_tool_args, dict) and 'code' in parsed_tool_args)
                if is_execute_code and isinstance(parsed_tool_args, dict):
                    code_to_execute = parsed_tool_args.get('code')
                    if code_to_execute:
                        print(f"{Colors_obj.TOOL_INFO}      Code to be executed:{Colors_obj.ENDC}\n{Colors_obj.CODE_OUTPUT}{indent_func(code_to_execute, '        ')}{Colors_obj.ENDC}")
            
            except json_module.JSONDecodeError as je:
                logger_obj.warning(f"JSONDecodeError parsing arguments for {tool_name_attr} in Raw Response: {tool_args_str} - Error: {je}")
                print(f"{Colors_obj.AGENT_MESSAGE}    Arguments (raw string, JSON decode failed):{Colors_obj.ENDC}\n{Colors_obj.CODE_OUTPUT}{indent_func(str(tool_args_str), '      ')}{Colors_obj.ENDC}")
            except Exception as e:
                logger_obj.error(f"Error processing/displaying arguments for {tool_name_attr} in Raw Response: {tool_args_str} - Error: {e}")
                print(f"{Colors_obj.AGENT_MESSAGE}    Arguments (error displaying):{Colors_obj.ENDC}\n{Colors_obj.CODE_ERROR}{indent_func(str(tool_args_str), '      ')}{Colors_obj.ENDC}")

        elif hasattr(output_item, 'content') and isinstance(output_item.content, list) and \
                len(output_item.content) > 0 and hasattr(output_item.content[0], 'text') and \
                isinstance(output_item.content[0].text, str) :
            item_processed_for_verbose = True
            tool_response_content_str = output_item.content[0].text
            message_id = getattr(output_item, 'id', "unknown_message_id") 
            print(f"{Colors_obj.AGENT_PROMPT}  Assistant Interpreted Tool Output (from Raw Response, msg_id: {message_id}){Colors_obj.ENDC}")
            print(f"{Colors_obj.AGENT_MESSAGE}{indent_func(tool_response_content_str, '    ')}{Colors_obj.ENDC}")
        
        elif hasattr(output_item, 'text'): 
            item_processed_for_verbose = True
            print(f"{Colors_obj.AGENT_PROMPT}  Assistant Says (direct text from Raw Response):{Colors_obj.ENDC}")
            print(f"{Colors_obj.AGENT_MESSAGE}{indent_func(output_item.text, '    ')}{Colors_obj.ENDC}")
        
        if not item_processed_for_verbose:
            print(f"{Colors_obj.LOG_WARNING}    Raw Response Output item has unknown structure: {str(output_item)[:200]}...{Colors_obj.ENDC}")
        print(f"{Colors_obj.HEADER}  ---{Colors_obj.ENDC}")


async def main():
    # current_model_name and enc are local to main and updated by the model handler.
    current_model_name = cli_config.DEFAULT_MODEL
    enc = cli_config.initialize_tokenizer(current_model_name, cli_config.TIKTOKEN_MAPPING, logger)

    # agent and agent_instructions_text are module-level and modified by setup_agent and model_handler
    global agent, agent_instructions_text

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
        logger.error("Failed to create or verify virtual environment. Code execution may fail.")
        print(f"{Colors.LOG_ERROR}Failed to create or verify virtual environment. Code execution may fail.{Colors.ENDC}")
    elif venv_created:
        if install_basic_packages(logger, venv_path):
            logger.info("Basic packages installed successfully in the new virtual environment.")
        else:
            logger.warning("Failed to install basic packages. Some code execution may fail.")
            print(f"{Colors.LOG_WARNING}Failed to install basic packages. Some code execution may fail.{Colors.ENDC}")

    configured_server_instances = await configure_servers(logger, script_dir, samples_dir)
    
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
                try:
                    await server_instance.cleanup()
                except Exception as cleanup_e:
                    logger.error(f"Error during cleanup of failed server {server_instance.name}: {cleanup_e}")
    
    if not successfully_connected_servers:
        logger.error("No MCP servers connected successfully. Exiting application.")
        print(f"{Colors.LOG_ERROR}No MCP servers connected successfully. Exiting application.{Colors.ENDC}")
        return

    logger.info(f"Total successfully connected servers: {len(successfully_connected_servers)} out of {len(configured_server_instances)} configured.")
    print(f"{Colors.LOG_INFO}Total successfully connected servers: {len(successfully_connected_servers)} out of {len(configured_server_instances)} configured. Starting interactive chat...{Colors.ENDC}")

    openrouter_client = OpenAI(
        base_url=cli_config.OPENROUTER_BASE_URL,
        api_key=cli_config.OPENROUTER_API_KEY,
    )
    
    agent, agent_instructions_text = setup_agent(
        logger, 
        successfully_connected_servers, 
        samples_dir, 
        model_name=current_model_name, 
        client=openrouter_client,
        extra_headers=cli_config.EXTRA_HEADERS 
    )

    @asynccontextmanager
    async def manage_server_connections(servers_to_manage):
        try:
            yield
        finally:
            logger.info(f"Cleaning up {len(servers_to_manage)} server connection(s)...")
            for server in servers_to_manage:
                try:
                    await server.cleanup()
                    logger.info(f"Successfully cleaned up server: {server.name}")
                except Exception as e:
                    logger.error(f"Error cleaning up server {server.name}: {e}")
            logger.info("All server cleanups attempted.")

    async with manage_server_connections(successfully_connected_servers):
        current_conversation_history = []
        total_conversation_prompt_tokens = 0
        total_conversation_completion_tokens = 0
        total_conversation_cost = 0.0
        print(f"{Colors.SYSTEM_INFO}Type 'quit' or 'exit' to end, '/instructions' for prompts, '/newchat' to reset.{Colors.ENDC}")
        print(f"{Colors.SYSTEM_INFO}Type '/model' for interactive selection or '/model <model_name>' to change model.{Colors.ENDC}")
        print(f"{Colors.SYSTEM_INFO}Current model: {current_model_name}{Colors.ENDC}")
        print(f"{Colors.SYSTEM_INFO}Available models: {', '.join(cli_config.SUPPORTED_MODELS)}{Colors.ENDC}")

        with trace("MCP Interactive Session"):
            while True:
                try:
                    user_input_text = input(f"\n{Colors.BOLD}{Colors.USER_PROMPT}You ({current_model_name}): {Colors.ENDC}")
                    if user_input_text.lower() in ["quit", "exit"]:
                        print(f"{Colors.SYSTEM_INFO}Exiting chat.{Colors.ENDC}")
                        break
                    
                    if user_input_text.lower() == "/instructions":
                        print(f"\n{Colors.HEADER}--- Agent Instructions ---{Colors.ENDC}")
                        print(f"{Colors.SYSTEM_INFO}{agent_instructions_text}{Colors.ENDC}")
                        print(f"{Colors.HEADER}------------------------{Colors.ENDC}")
                        continue

                    if user_input_text.lower() == "/model":
                        prompt_title = f"{Colors.SYSTEM_INFO}Select a model (current: {current_model_name}):{Colors.ENDC}"
                        selected_model = select_model_interactive( # From cli_ui
                            prompt_title,
                            cli_config.SUPPORTED_MODELS,
                            current_model_name,
                            Colors 
                        )
                        if selected_model:
                            if selected_model != current_model_name:
                                agent, agent_instructions_text, current_model_name, enc = \
                                    await cli_model_handler.update_model_and_agent_config(
                                        selected_model,
                                        logger, successfully_connected_servers, samples_dir,
                                        openrouter_client, cli_config.EXTRA_HEADERS, 
                                        cli_config.TIKTOKEN_MAPPING, cli_config.SUPPORTED_MODELS
                                    )
                            else:
                                print(f"{Colors.SYSTEM_INFO}Model is already set to: {current_model_name}{Colors.ENDC}")
                        if selected_model is None:
                            print(f"{Colors.SYSTEM_INFO}Model selection cancelled.{Colors.ENDC}")
                        continue

                    elif user_input_text.lower().startswith("/model "):
                        parts = user_input_text.split(" ", 1)
                        if len(parts) > 1 and parts[1].strip():
                            new_model_candidate = parts[1].strip()
                            if new_model_candidate in cli_config.SUPPORTED_MODELS:
                                if new_model_candidate != current_model_name:
                                    agent, agent_instructions_text, current_model_name, enc = \
                                        await cli_model_handler.update_model_and_agent_config(
                                            new_model_candidate,
                                            logger, successfully_connected_servers, samples_dir,
                                            openrouter_client, cli_config.EXTRA_HEADERS,
                                            cli_config.TIKTOKEN_MAPPING, cli_config.SUPPORTED_MODELS
                                        )
                                else:
                                    print(f"{Colors.SYSTEM_INFO}Model is already set to: {current_model_name}{Colors.ENDC}")
                            else:
                                print(f"{Colors.LOG_ERROR}Invalid model. Supported models: {', '.join(cli_config.SUPPORTED_MODELS)}{Colors.ENDC}")
                        else:
                            print(f"{Colors.LOG_ERROR}Usage: /model (interactive) or /model <model_name>. Supported: {', '.join(cli_config.SUPPORTED_MODELS)}{Colors.ENDC}")
                        continue
                    
                    if user_input_text.lower() == "/newchat":
                        current_conversation_history = []
                        total_conversation_prompt_tokens = 0
                        total_conversation_completion_tokens = 0
                        total_conversation_cost = 0.0
                        print(f"{Colors.SYSTEM_INFO}Conversation history cleared. Totals reset. Starting fresh.{Colors.ENDC}")
                        continue

                    msgs = current_conversation_history + [{"role": "user", "content": user_input_text}]
                    
                    prompt_tokens = 0
                    if enc: 
                        for m_hist in msgs:
                            msg_content_val = m_hist.get("content")
                            if isinstance(msg_content_val, str):
                                prompt_tokens += len(enc.encode(msg_content_val))
                            elif isinstance(msg_content_val, list):
                                for content_block in msg_content_val:
                                    if isinstance(content_block, dict) and content_block.get("type") == "text":
                                        text_to_encode = content_block.get("text")
                                        if isinstance(text_to_encode, str):
                                            prompt_tokens += len(enc.encode(text_to_encode))
                    else:
                        logger.warning("Tokenizer (enc) is not initialized. Token count will be inaccurate.")

                    print(f"{Colors.SYSTEM_INFO}[tokens] prompt: {prompt_tokens}{Colors.ENDC}")
                    print(f"{Colors.SYSTEM_INFO}Agent is processing...{Colors.ENDC}")
                    
                    # Initialize a counter for streamed steps that we want to detail
                    streamed_step_counter = 0
                    # Accumulate text for final display if needed, and for history
                    final_streamed_output_text = ""
                    # Store structured events if needed for history reconstruction
                    accumulated_structured_events = []

                    try:
                        # Check if we're using an Ollama model
                        if current_model_name.startswith("ollama/"):
                            # Extract the model name without the "ollama/" prefix
                            ollama_model_name = current_model_name.split('/')[-1]
                            
                            print(f"\n{Colors.HEADER}--- Using Direct Ollama Chat (bypassing Agent) ---{Colors.ENDC}")
                            
                            try:
                                # Use our direct Ollama chat function
                                assistant_message, pt, ct = await handle_ollama_chat(
                                    ollama_model_name, 
                                    msgs, 
                                    logger, 
                                    enc
                                )
                                
                                # Print the response
                                print(f"{Colors.AGENT_MESSAGE}{assistant_message}{Colors.ENDC}")
                                
                                # Update conversation history
                                current_conversation_history = msgs + [{"role": "assistant", "content": assistant_message}]
                                
                                # Set token counts and final output
                                final_streamed_output_text = assistant_message
                                tt = pt + ct
                                
                                # Create a dummy result object with the necessary attributes
                                class DummyResult:
                                    def __init__(self, final_output, conversation_history):
                                        self.final_output = final_output
                                        self._conversation_history = conversation_history
                                        self.usage = None
                                    
                                    def to_input_list(self):
                                        return self._conversation_history
                                    
                                    async def stream_events(self):
                                        # This is a dummy implementation that doesn't actually stream
                                        # It just yields a single event with the final output
                                        class DummyEvent:
                                            def __init__(self, type, data=None):
                                                self.type = type
                                                self.data = data
                                        
                                        # Yield a dummy event to satisfy the async for loop
                                        yield DummyEvent("dummy_event")
                                        return
                                
                                result = DummyResult(assistant_message, current_conversation_history)
                                
                            except Exception as e:
                                logger.error(f"Error in direct Ollama chat: {e}")
                                raise
                                
                        else:
                            # Use the Agent framework for non-Ollama models
                            # Changed to run_streamed
                            # Pass agent as a positional argument, then input and max_turns as keyword arguments
                            result = Runner.run_streamed(
                                agent, # Positional
                                input=msgs, 
                                max_turns=30
                            )

                            print(f"\n{Colors.HEADER}--- Agent's Live Actions (Streaming) ---{Colors.ENDC}")
                        async for event in result.stream_events():
                            if event.type == "raw_response_event" and isinstance(event.data, ResponseTextDeltaEvent):
                                if event.data.delta:
                                    print(event.data.delta, end="", flush=True)
                                    final_streamed_output_text += event.data.delta
                            elif event.type == "run_item_stream_event": # Example from docs for structured items
                                # This is where we'd print more detailed step info
                                streamed_step_counter += 1
                                # print_streamed_step_details(event, streamed_step_counter, Colors, logger, indent_multiline_text, json)
                                # For now, just a basic print:
                                print(f"\n{Colors.SYSTEM_INFO}Streamed Item (Step {streamed_step_counter}): {event.item.type}{Colors.ENDC}")
                                accumulated_structured_events.append(event.item) # Store for potential history
                            elif event.type == "agent_updated_stream_event":
                                print(f"\n{Colors.SYSTEM_INFO}Agent updated to: {event.new_agent.name}{Colors.ENDC}")
                            # Add other event type handling as needed based on documentation and testing
                            # else:
                                # print(f"\nDebug Event: Type: {event.type}, Data: {event.data}")


                        # After stream is complete, print a newline if text was streamed
                        if final_streamed_output_text:
                            print() # Newline after streamed text

                        # The 'result' from run_streamed is RunResultStreaming.
                        # We need to get the final result, often by calling a method on it.
                        # Let's assume it has a way to get the final state, e.g. by awaiting the result itself
                        # or calling a specific method. The SDK docs should clarify this.
                        # For now, we'll assume `await result.get_final_result()` or similar is needed
                        # if `result.to_input_list()` or `result.usage` are not directly available
                        # on RunResultStreaming and need the run to be fully processed.
                        # This part is a placeholder and might need adjustment:
                        
                        # If RunResultStreaming itself has these, great. Otherwise, we might need:
                        # final_run_result = await result.full_run() # Or similar, per SDK docs
                        # current_conversation_history = final_run_result.to_input_list()
                        # usage_info = final_run_result.usage 
                        # For now, let's assume result (RunResultStreaming) has them directly or via a property
                        
                        # Placeholder for final output if not captured by streaming text delta
                        if not final_streamed_output_text and hasattr(result, 'final_output') and result.final_output:
                             final_streamed_output_text = result.final_output if isinstance(result.final_output, str) else str(result.final_output)


                    except openai.BadRequestError as bre:
                        logger.error(f"{Colors.LOG_ERROR}BadRequestError during Runner.run_streamed. This means the API call was malformed.{Colors.ENDC}")
                        logger.error(f"{Colors.LOG_ERROR}The input 'msgs' to Runner.run_streamed that likely caused this was:{Colors.ENDC}")
                        try:
                            pretty_msgs = json.dumps(msgs, indent=2, default=str)
                            logger.error(f"\n{Colors.CODE_ERROR}{indent_multiline_text(pretty_msgs, '  ')}{Colors.ENDC}")
                        except TypeError:
                            logger.error(f"\n{Colors.CODE_ERROR}{indent_multiline_text(str(msgs), '  ')}{Colors.ENDC}")
                        
                        error_body_str = "Could not serialize error body."
                        if bre.body:
                            try:
                                error_body_str = json.dumps(bre.body, indent=2)
                            except (TypeError, json.JSONDecodeError):
                                error_body_str = str(bre.body)
                        
                        logger.error(f"{Colors.LOG_ERROR}OpenAI API Error details (bre.body):{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(error_body_str, '  ')}{Colors.ENDC}")
                        raise 
                    
                    current_conversation_history = result.to_input_list()

                    if hasattr(result, "usage") and result.usage and \
                       hasattr(result.usage, 'prompt_tokens') and \
                       hasattr(result.usage, 'completion_tokens') and \
                       hasattr(result.usage, 'total_tokens'):
                        pt = result.usage.prompt_tokens
                        ct = result.usage.completion_tokens
                        tt = result.usage.total_tokens
                    else: 
                        final_output_str = result.final_output if isinstance(result.final_output, str) else str(result.final_output or "")
                        if enc: 
                            ct = len(enc.encode(final_output_str))
                        else:
                            ct = 0 
                            logger.warning("Tokenizer (enc) is not initialized for completion token count.")
                        pt = prompt_tokens 
                        tt = pt + ct
                    
                    cost = (pt / 1000) * cli_config.PROMPT_PRICE_PER_1K + \
                           (ct / 1000) * cli_config.COMPLETION_PRICE_PER_1K
                    
                    total_conversation_prompt_tokens += pt
                    total_conversation_completion_tokens += ct
                    total_conversation_cost += cost
                    
                    # Temporarily comment out the old detailed actions block
                    # print(f"\n{Colors.HEADER}--- Agent's Detailed Actions ---{Colors.ENDC}")
                    # if hasattr(result, 'raw_responses') and result.raw_responses:
                    #     for step_idx, raw_model_response_item in enumerate(result.raw_responses):
                    #         print_single_raw_response_step(step_idx + 1, raw_model_response_item, Colors, logger, indent_multiline_text, json)
                    # print(f"{Colors.HEADER}--- End of Agent's Detailed Actions ---{Colors.ENDC}")
                    
                    # The conversation history and final output handling will need adjustment
                    # based on how RunResultStreaming provides this information.
                    # For now, we'll use the accumulated text as the final output.
                    # And current_conversation_history might need to be reconstructed or obtained differently.
                    
                    # Attempt to get conversation history. This might need `await result.full_run()` first.
                    # This is a critical point that depends on the SDK's API for RunResultStreaming.
                    try:
                        current_conversation_history = result.to_input_list()
                        # If `result.usage` is not directly available, we might need to get it from a final result object.
                        # For now, we proceed assuming it might be there or calculated as before.
                    except AttributeError:
                        logger.warning("RunResultStreaming does not have to_input_list directly. History might be incomplete or require full_run().")
                        # Fallback: construct a minimal history or use the old one if appropriate (though likely stale)
                        # This part needs robust handling based on SDK.
                        # For now, if it fails, history printing will be affected.
                        # We might need to manually append the final_streamed_output_text to history.
                        if final_streamed_output_text:
                             current_conversation_history.append({"role": "assistant", "content": final_streamed_output_text})


                    print(f"\n{Colors.SYSTEM_INFO}--- Processed Conversation History (SDK Messages) ---{Colors.ENDC}")
                    if not current_conversation_history and hasattr(result, '_previous_result_for_history_only_for_debugging'): # Example of a potential internal
                        logger.warning("Using a debug/internal attribute for history. This is not robust.")
                        current_conversation_history = result._previous_result_for_history_only_for_debugging.to_input_list()


                    for hist_idx, hist_item in enumerate(current_conversation_history):
                        role = hist_item.get('role')
                        item_type = hist_item.get('type') 
                        
                        print(f"{Colors.HEADER}History Item {hist_idx + 1}: Role: {role if role else 'N/A'}, Type: {item_type if item_type else 'N/A'}{Colors.ENDC}")
                        
                        if role == 'user':
                            print(f"{Colors.USER_PROMPT}  Content: {hist_item.get('content')}{Colors.ENDC}")
                        
                        elif role == 'assistant' or item_type == 'function_call': 
                            assistant_content = hist_item.get('content')
                            tool_calls_list = hist_item.get('tool_calls') 
                            if not tool_calls_list and item_type == 'function_call': 
                                tool_calls_list = [hist_item] 

                            if tool_calls_list:
                                print(f"{Colors.TOOL_INFO}  Tool Calls by Assistant (from SDK History):{Colors.ENDC}")
                                for tc_idx, tc_call_item in enumerate(tool_calls_list):
                                    call_id = tc_call_item.get('id')
                                    func_name = None
                                    func_args_str = None

                                    if 'function' in tc_call_item and isinstance(tc_call_item['function'], dict): 
                                        func_details = tc_call_item.get('function', {})
                                        func_name = func_details.get('name')
                                        func_args_str = func_details.get('arguments')
                                    elif 'name' in tc_call_item and 'arguments' in tc_call_item: 
                                        func_name = tc_call_item.get('name')
                                        func_args_str = tc_call_item.get('arguments')
                                    
                                    print(f"{Colors.TOOL_INFO}    Call [{tc_idx+1}] ID: {call_id}{Colors.ENDC}")
                                    print(f"{Colors.TOOL_INFO}      Function Name: {Colors.BOLD}{func_name}{Colors.ENDC}")
                                    print(f"{Colors.AGENT_MESSAGE}      Arguments (JSON str): {func_args_str}{Colors.ENDC}")

                            if assistant_content and role == 'assistant': 
                                print(f"{Colors.AGENT_PROMPT}  Text Content: {assistant_content}{Colors.ENDC}")
                            elif not tool_calls_list and not assistant_content and role == 'assistant' :
                                 print(f"{Colors.AGENT_PROMPT}  (No text content or tool calls for assistant message){Colors.ENDC}")

                        elif role == 'tool' or item_type == 'function_call_output': 
                            tool_call_id_ref = hist_item.get('tool_call_id') or hist_item.get('call_id') 
                            tool_name_invoked = hist_item.get('name', 'UnknownToolName') 
                            
                            print(f"{Colors.TOOL_INFO}  Tool Execution Result (for Call ID: ~{tool_call_id_ref}){Colors.ENDC}")
                            if role == 'tool': 
                                 print(f"{Colors.TOOL_INFO}    Tool Name Invoked: {Colors.BOLD}{tool_name_invoked}{Colors.ENDC}")
                            
                            raw_tool_output_str = hist_item.get('content') if role == 'tool' else hist_item.get('output')

                            print(f"{Colors.TOOL_INFO}    Raw Output String from Tool System:{Colors.ENDC}")
                            print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(raw_tool_output_str, '      ')}{Colors.ENDC}")
                            
                            mcp_executor_response_str = None
                            try:
                                if isinstance(raw_tool_output_str, str):
                                    outer_parsed = json.loads(raw_tool_output_str)
                                    if isinstance(outer_parsed, dict) and outer_parsed.get('type') == 'text' and 'text' in outer_parsed:
                                        mcp_executor_response_str = outer_parsed['text']
                                        print(f"{Colors.TOOL_INFO}    Extracted MCP Executor Response String:{Colors.ENDC}")
                                        print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(mcp_executor_response_str, '      ')}{Colors.ENDC}")
                                    else: 
                                        mcp_executor_response_str = raw_tool_output_str
                                else: 
                                    mcp_executor_response_str = str(raw_tool_output_str)

                            except json.JSONDecodeError:
                                mcp_executor_response_str = raw_tool_output_str if isinstance(raw_tool_output_str, str) else str(raw_tool_output_str)
                                logger.debug(f"Raw tool output string was not JSON or not structured as expected: {raw_tool_output_str}")
                            except Exception as e:
                                logger.error(f"Error parsing outer tool output string: {e}")
                                mcp_executor_response_str = f"Error parsing outer tool output: {e}"


                            if mcp_executor_response_str:
                                print(f"{Colors.TOOL_INFO}    Final Content from MCP Executor (attempting to parse as JSON):{Colors.ENDC}")
                                try:
                                    if not isinstance(mcp_executor_response_str, str):
                                        mcp_executor_response_str = str(mcp_executor_response_str)

                                    parsed_mcp_output = json.loads(mcp_executor_response_str)
                                    pretty_mcp_output = json.dumps(parsed_mcp_output, indent=2, ensure_ascii=False)
                                    
                                    is_error_mcp_response = False
                                    if isinstance(parsed_mcp_output, dict):
                                        if parsed_mcp_output.get('status') == 'error' or parsed_mcp_output.get('isError'):
                                            is_error_mcp_response = True
                                    
                                    display_color = Colors.CODE_ERROR if is_error_mcp_response else Colors.CODE_OUTPUT
                                    print(f"{display_color}{indent_multiline_text(pretty_mcp_output, '      ')}{Colors.ENDC}")

                                    if isinstance(parsed_mcp_output, dict) and 'status' in parsed_mcp_output:
                                        print(f"{Colors.TOOL_INFO}      Parsed Details from MCP Executor Content:{Colors.ENDC}")
                                        if 'status' in parsed_mcp_output: print(f"{Colors.BOLD}        Status:{Colors.ENDC} {parsed_mcp_output['status']}")
                                        if 'file_path' in parsed_mcp_output: print(f"{Colors.BOLD}        File Path:{Colors.ENDC} {parsed_mcp_output['file_path']}")
                                        if 'generated_filename' in parsed_mcp_output: print(f"{Colors.BOLD}        Generated Filename:{Colors.ENDC} {parsed_mcp_output['generated_filename']}")
                                        out_val = parsed_mcp_output.get('output')
                                        if out_val is not None: print(f"{Colors.BOLD}        Output:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(str(out_val), '          ')}{Colors.ENDC}")
                                        err_val = parsed_mcp_output.get('error')
                                        if err_val: print(f"{Colors.BOLD}        Error:{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(err_val, '          ')}{Colors.ENDC}")
                                        msg_val = parsed_mcp_output.get('message')
                                        if msg_val and out_val is None and not err_val: print(f"{Colors.BOLD}        Message:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(msg_val, '          ')}{Colors.ENDC}")
                                except json.JSONDecodeError:
                                    print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(mcp_executor_response_str, '      ')} (Content was not valid JSON){Colors.ENDC}")
                                except Exception as e:
                                    logger.error(f"Error displaying final MCP executor content: {e}")
                                    print(f"{Colors.CODE_ERROR}{indent_multiline_text(mcp_executor_response_str, '      ')} (Error formatting: {e}){Colors.ENDC}")
                        
                        elif isinstance(hist_item, dict): 
                            print(f"{Colors.LOG_WARNING}  Other item in history (keys: {list(hist_item.keys())}):{Colors.ENDC}")
                            try:
                                print(f"{Colors.LOG_WARNING}    Full item: {json.dumps(hist_item, indent=2, default=str)}{Colors.ENDC}")
                            except TypeError: 
                                print(f"{Colors.LOG_WARNING}    Full item (raw): {hist_item}{Colors.ENDC}")

                        print(f"{Colors.HEADER}  ---{Colors.ENDC}")

                    print(f"{Colors.SYSTEM_INFO}[turn usage] prompt: {pt}, completion: {ct}, total: {tt}{Colors.ENDC}")
                    print(f"{Colors.SYSTEM_INFO}[turn cost] ${cost:.5f}{Colors.ENDC}")
                    print(f"{Colors.SYSTEM_INFO}[total usage] prompt: {total_conversation_prompt_tokens}, completion: {total_conversation_completion_tokens}, total: {total_conversation_prompt_tokens + total_conversation_completion_tokens}{Colors.ENDC}")
                    print(f"{Colors.SYSTEM_INFO}[total cost] ${total_conversation_cost:.5f}{Colors.ENDC}")
                    
                    print(f"\n{Colors.BOLD}{Colors.AGENT_PROMPT}Agent: {Colors.ENDC}")
                    # Use the accumulated streamed text as the primary final output
                    print(f"{Colors.AGENT_MESSAGE}{final_streamed_output_text or (result.final_output if hasattr(result, 'final_output') else 'No output')}{Colors.ENDC}")
                    
                except KeyboardInterrupt:
                    print(f"\n{Colors.SYSTEM_INFO}Exiting chat due to interrupt.{Colors.ENDC}")
                    break
                except Exception as e: 
                    logger.exception("An error occurred during the interactive loop.") 
                    print(f"\n{Colors.LOG_ERROR}An error occurred: {e}{Colors.ENDC}")
    
    print(f"\n{Colors.LOG_INFO}Chat session complete. MCP Servers will be disconnected.{Colors.ENDC}")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except RuntimeError as e:
        logger.error(f"Runtime error during script initialization: {e}")
        print(f"{Colors.LOG_ERROR}Runtime error: {e}{Colors.ENDC}")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"An unexpected critical error occurred during script execution: {e}", exc_info=True)
        print(f"{Colors.LOG_ERROR}An unexpected critical error occurred: {e}{Colors.ENDC}")
        sys.exit(1)
