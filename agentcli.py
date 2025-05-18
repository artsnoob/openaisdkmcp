import asyncio
import os
import shutil
import logging
import sys
# import argparse # No longer needed for verbosity flag
import json
from dotenv import load_dotenv
from contextlib import asynccontextmanager
import tty # For raw terminal mode
import termios # For terminal attributes

# ─── NEW IMPORTS ──────────────────────────────────────────────────────────────
import tiktoken
from openai import OpenAI # Ensure openai is imported to catch openai.BadRequestError
# ─── END NEW IMPORTS ──────────────────────────────────────────────────────────

from agents import Runner, trace

from mcp_utils import Colors, setup_colored_logger, install_basic_packages, ensure_venv_exists, indent_multiline_text
from mcp_server_config import configure_servers
from mcp_agent_setup import setup_agent

logger = setup_colored_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    logger.error("OPENROUTER_API_KEY not found in .env file. Please add it.")
    raise ValueError("OPENROUTER_API_KEY not found in .env file.")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
# Optional: Replace with your actual site URL and name for better OpenRouter ranking
YOUR_SITE_URL = os.getenv("OPENROUTER_REFERRER_URL", "http://localhost")
YOUR_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "MCP Agent")

EXTRA_HEADERS = {
    "HTTP-Referer": YOUR_SITE_URL,
    "X-Title": YOUR_SITE_NAME,
}

if not shutil.which("npx"):
    logger.error("npx command not found. Please install Node.js and npm from https://nodejs.org/")
    raise RuntimeError("npx command not found.")
if not shutil.which("uvx"):
    logger.error("uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv")
    raise RuntimeError("uvx command not found.")

# ─── MODEL AND TOKENIZER SETUP ──────────────────────────────────────────────────
SUPPORTED_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4.1-mini", # Note: This might be a typo and should be gpt-4-mini or similar, verify on OpenRouter
    "google/gemini-2.5-flash-preview", # Corrected from gemini-flash-1.5-preview
]
DEFAULT_MODEL = "openai/gpt-4o-mini"
current_model_name = DEFAULT_MODEL

# Mapping for supported models to tiktoken base model names or direct encoding names
TIKTOKEN_MAPPING = {
    "openai/gpt-4o-mini": ("model", "gpt-4o"),
    "openai/gpt-4.1-mini": ("model", "gpt-4o"), # Assuming gpt-4o compatibility for tokenization
    "google/gemini-2.5-flash-preview": ("encoding", "cl100k_base"), # Approximation, Gemini has its own tokenizer
}

# Tokenizer - using gpt-4o-mini as a general default for display purposes.
# Actual tokenization for billing might differ per model on OpenRouter.
_map_type, _map_value = TIKTOKEN_MAPPING.get(DEFAULT_MODEL, ("model", "gpt-4o")) # Default to gpt-4o model if not in map
if _map_type == "encoding":
    ENC = tiktoken.get_encoding(_map_value)
else: # _map_type == "model"
    ENC = tiktoken.encoding_for_model(_map_value)

# Pricing - This will become more complex if we want accurate per-model pricing.
# For now, using gpt-4o-mini prices as a placeholder.
# TODO: Implement dynamic pricing based on current_model_name
PROMPT_PRICE_PER_1K = 0.00015  # gpt-4o-mini input price
COMPLETION_PRICE_PER_1K = 0.0006   # gpt-4o-mini output price
# ─── END MODEL AND TOKENIZER SETUP ──────────────────────────────────────────────

# ─── HELPER FUNCTION FOR INTERACTIVE MODEL SELECTION ───────────────────────────
def select_model_interactive(prompt_title, options, active_model_value, colors_module):
    old_settings = termios.tcgetattr(sys.stdin.fileno())
    try:
        tty.setraw(sys.stdin.fileno())
        
        if not options:
            sys.stdout.write(f"{colors_module.LOG_ERROR}No models available for selection.{colors_module.ENDC}\r\n")
            sys.stdout.flush()
            sys.stdin.read(1) # Wait for a key press
            return None

        try:
            current_selection_index = options.index(active_model_value)
        except ValueError:
            current_selection_index = 0 # Default to first if current active model not in list

        while True:
            # Clear screen or redraw in place (using ANSI codes)
            sys.stdout.write("\033c") # Clears the screen
            
            sys.stdout.write(f"{prompt_title}\r\n")
            sys.stdout.write(f"{colors_module.SYSTEM_INFO}Use ARROW UP/DOWN to navigate, ENTER to select, ESC to cancel.{colors_module.ENDC}\r\n\r\n")

            for i, option in enumerate(options):
                prefix = "> " if i == current_selection_index else "  "
                
                display_option_text = option
                if option == active_model_value:
                    display_option_text += " (current)"
                
                if i == current_selection_index:
                    sys.stdout.write(f"{colors_module.USER_PROMPT}{prefix}{colors_module.BOLD}{display_option_text}{colors_module.ENDC}{colors_module.ENDC}\r\n")
                else:
                    sys.stdout.write(f"{colors_module.SYSTEM_INFO}{prefix}{display_option_text}{colors_module.ENDC}\r\n")
            sys.stdout.flush()

            char = sys.stdin.read(1)

            if char == '\x1b':  # Escape character
                # Try to read the rest of an escape sequence
                next_char1 = sys.stdin.read(1)
                if next_char1 == '[': # Potential arrow key (e.g., \x1b[A)
                    next_char2 = sys.stdin.read(1)
                    if next_char2 == 'A':  # Up arrow
                        current_selection_index = (current_selection_index - 1 + len(options)) % len(options)
                    elif next_char2 == 'B':  # Down arrow
                        current_selection_index = (current_selection_index + 1) % len(options)
                    # Ignore other CSI sequences for simplicity
                else: # Likely just the ESC key pressed (\x1b followed by something not '[' or nothing)
                    sys.stdout.write("\033c") # Clear screen
                    sys.stdout.flush()
                    return None # Cancelled
            elif char == '\r' or char == '\n':  # Enter key
                sys.stdout.write("\033c") # Clear screen
                sys.stdout.flush()
                return options[current_selection_index]
            elif char == '\x03': # Ctrl+C
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings) # Restore before raising
                raise KeyboardInterrupt
            # Ignore other characters
    finally:
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
# ─── END HELPER FUNCTION ───────────────────────────────────────────────────────

# ─── HELPER FUNCTION FOR UPDATING MODEL CONFIGURATION ──────────────────────────
async def _update_model_and_agent_config(new_model_name, logger_instance, servers_list, base_samples_dir, http_client, headers, tiktoken_map, supported_list):
    global current_model_name, ENC # These are global and will be modified
    
    if new_model_name not in supported_list:
        logger_instance.error(f"Internal error: Attempted to switch to an unsupported model: {new_model_name}")
        # This should ideally not be reached if called correctly
        return agent, agent_instructions_text # Return existing agent state

    logger_instance.info(f"Changing model from {current_model_name} to {new_model_name}")
    
    old_model_for_message = current_model_name
    current_model_name = new_model_name # Update global

    # Re-initialize agent with the new model
    # Note: setup_agent is synchronous, but we are in an async function.
    # If setup_agent becomes async, add await. For now, it's fine.
    new_agent_instance, new_instructions = setup_agent(
        logger_instance, 
        servers_list, 
        base_samples_dir, 
        model_name=current_model_name, 
        client=http_client,
        extra_headers=headers
    )
    
    _map_type, _map_value = tiktoken_map.get(current_model_name, (None, None))

    if "claude" in current_model_name: # Specific handling for Claude models
        ENC = tiktoken.encoding_for_model("gpt-4") # Use gpt-4 tokenizer for Claude
        logger_instance.info(f"Using 'gpt-4' base model for tiktoken with Claude model: {current_model_name}")
    elif _map_type == "encoding":
        ENC = tiktoken.get_encoding(_map_value)
        logger_instance.info(f"Using '{_map_value}' encoding for {current_model_name}.")
    elif _map_type == "model":
        ENC = tiktoken.encoding_for_model(_map_value)
        logger_instance.info(f"Using '{_map_value}' base model for tiktoken with {current_model_name}.")
    else: # Fallback for models not in TIKTOKEN_MAPPING and not Claude
        logger_instance.warning(f"No specific tiktoken mapping for {current_model_name}. Attempting 'cl100k_base' encoding.")
        try:
            ENC = tiktoken.get_encoding("cl100k_base")
        except Exception as e_enc:
            logger_instance.error(f"Failed to get 'cl100k_base' as fallback for {current_model_name}: {e_enc}. Using 'gpt2' encoding.")
            ENC = tiktoken.get_encoding("gpt2") # A very basic fallback
            
    print(f"{Colors.SYSTEM_INFO}Model changed from {old_model_for_message} to: {current_model_name}{Colors.ENDC}")
    # TODO: Implement dynamic pricing update if model changes (original TODO)
    
    return new_agent_instance, new_instructions
# ─── END HELPER FUNCTION ───────────────────────────────────────────────────────


async def main():
    global current_model_name, ENC # Allow modification of global model name and encoder
    # These will be set by _update_model_and_agent_config and used by the main loop
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

    # Initialize OpenAI client for OpenRouter
    openrouter_client = OpenAI(
        base_url=OPENROUTER_BASE_URL,
        api_key=OPENROUTER_API_KEY,
    )
    # Pass client, initial model, and extra_headers to setup_agent
    agent, agent_instructions_text = setup_agent(
        logger, 
        successfully_connected_servers, 
        samples_dir, 
        model_name=current_model_name, 
        client=openrouter_client,
        extra_headers=EXTRA_HEADERS 
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
        print(f"{Colors.SYSTEM_INFO}Available models: {', '.join(SUPPORTED_MODELS)}{Colors.ENDC}")

        with trace("MCP Interactive Session"):
            while True:
                try:
                    # Ensure agent and agent_instructions_text are defined before this loop if they can be modified by it
                    # They are initialized before the async with manage_server_connections block

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
                        selected_model = select_model_interactive(
                            prompt_title,
                            SUPPORTED_MODELS,
                            current_model_name,
                            Colors # Pass the Colors class/module
                        )
                        if selected_model:
                            if selected_model != current_model_name:
                                agent, agent_instructions_text = await _update_model_and_agent_config(
                                    selected_model,
                                    logger, successfully_connected_servers, samples_dir,
                                    openrouter_client, EXTRA_HEADERS, TIKTOKEN_MAPPING, SUPPORTED_MODELS
                                )
                            else:
                                print(f"{Colors.SYSTEM_INFO}Model is already set to: {current_model_name}{Colors.ENDC}")
                        # If selected_model is None, it means cancellation, so do nothing.
                        # The select_model_interactive function handles clearing its own UI.
                        # We need to reprint the prompt for the next input.
                        # The loop continues, and input() will be called again.
                        # To ensure the chat prompt is clean, we might need a redraw or just let it be.
                        # For now, let the main loop's input() reprint the prompt.
                        if selected_model is None: # Explicitly print a cancellation message if desired
                            print(f"{Colors.SYSTEM_INFO}Model selection cancelled.{Colors.ENDC}")
                        continue # Always continue to get fresh input prompt

                    elif user_input_text.lower().startswith("/model "):
                        parts = user_input_text.split(" ", 1)
                        if len(parts) > 1 and parts[1].strip():
                            new_model_candidate = parts[1].strip()
                            if new_model_candidate in SUPPORTED_MODELS:
                                if new_model_candidate != current_model_name:
                                    agent, agent_instructions_text = await _update_model_and_agent_config(
                                        new_model_candidate,
                                        logger, successfully_connected_servers, samples_dir,
                                        openrouter_client, EXTRA_HEADERS, TIKTOKEN_MAPPING, SUPPORTED_MODELS
                                    )
                                else:
                                    print(f"{Colors.SYSTEM_INFO}Model is already set to: {current_model_name}{Colors.ENDC}")
                            else:
                                print(f"{Colors.LOG_ERROR}Invalid model. Supported models: {', '.join(SUPPORTED_MODELS)}{Colors.ENDC}")
                        else:
                            print(f"{Colors.LOG_ERROR}Usage: /model (interactive) or /model <model_name>. Supported: {', '.join(SUPPORTED_MODELS)}{Colors.ENDC}")
                        continue
                    
                    if user_input_text.lower() == "/newchat":
                        current_conversation_history = []
                        total_conversation_prompt_tokens = 0
                        total_conversation_completion_tokens = 0
                        total_conversation_cost = 0.0
                        print(f"{Colors.SYSTEM_INFO}Conversation history cleared. Totals reset. Starting fresh.{Colors.ENDC}")
                        continue

                    # MODIFIED: Naive truncation commented out for debugging
                    # current_conversation_history = current_conversation_history[-8:]
                    msgs = current_conversation_history + [{"role": "user", "content": user_input_text}]
                    
                    prompt_tokens = 0
                    for m_hist in msgs:
                        msg_content_val = m_hist.get("content")
                        if isinstance(msg_content_val, str):
                            prompt_tokens += len(ENC.encode(msg_content_val))
                        elif isinstance(msg_content_val, list):
                            for content_block in msg_content_val:
                                if isinstance(content_block, dict) and content_block.get("type") == "text":
                                    text_to_encode = content_block.get("text")
                                    if isinstance(text_to_encode, str):
                                        prompt_tokens += len(ENC.encode(text_to_encode))
                    
                    print(f"{Colors.SYSTEM_INFO}[tokens] prompt: {prompt_tokens}{Colors.ENDC}")
                    print(f"{Colors.SYSTEM_INFO}Agent is processing...{Colors.ENDC}")
                    
                    # ─── RUN AGENT (WITH IMPROVED ERROR LOGGING) ──────────────────────
                    try:
                        # Pass the OpenRouter client and extra_headers to Runner.run or ensure Agent uses them
                        # This part depends on how Runner.run and Agent are structured.
                        # For now, assuming Agent was configured with the client and model by setup_agent.
                        # If Runner.run needs explicit client/headers, this call needs modification.
                        # The `model` parameter in `Runner.run` might also need to be set to `current_model_name`.
                        # The `extra_body` and `extra_headers` are usually passed at client.chat.completions.create()
                        # This implies the Agent's internal call to the LLM needs to be modified.
                        # For now, the client passed to setup_agent is pre-configured with base_url and api_key.
                        # The extra_headers would need to be passed deeper.
                        # Let's assume the Agent class handles passing extra_headers if the client is an OpenAI client instance.
                        
                        # The Runner.run method in the original smithy Agent uses agent.client.chat.completions.create
                        # If our Agent class has a `client` attribute (the one we passed in setup_agent),
                        # and if it uses `self.client.chat.completions.create`, we need to ensure it can pass `extra_headers`.
                        # This might require modification of the Agent class in `agents.py`.
                        # For now, we proceed with the assumption that `setup_agent` configures the agent correctly.
                        # The model name is passed to the Agent constructor via setup_agent.
                        
                        result = await Runner.run(
                            starting_agent=agent, 
                            input=msgs, 
                            max_turns=30,
                            # The following are conceptual if Runner.run needs them directly.
                            # model=current_model_name, # If Agent doesn't get model from its constructor
                            # api_key=OPENROUTER_API_KEY, # If client isn't passed/used
                            # base_url=OPENROUTER_BASE_URL, # If client isn't passed/used
                            # extra_headers=EXTRA_HEADERS # This is the most complex part without seeing agents.py
                        )
                    except openai.BadRequestError as bre:
                        logger.error(f"{Colors.LOG_ERROR}BadRequestError during Runner.run. This means the API call was malformed.{Colors.ENDC}")
                        logger.error(f"{Colors.LOG_ERROR}The input 'msgs' to Runner.run that likely caused this was:{Colors.ENDC}")
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
                    # ─── END RUN AGENT ───────────────────────────────────────────────────
                    
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
                        ct = len(ENC.encode(final_output_str))
                        pt = prompt_tokens 
                        tt = pt + ct
                    
                    cost = (pt / 1000) * PROMPT_PRICE_PER_1K + (ct / 1000) * COMPLETION_PRICE_PER_1K
                    
                    total_conversation_prompt_tokens += pt
                    total_conversation_completion_tokens += ct
                    total_conversation_cost += cost
                    
                    print(f"\n{Colors.HEADER}--- Agent's Detailed Actions ---{Colors.ENDC}")
                    if hasattr(result, 'raw_responses') and result.raw_responses:
                        for step_idx, raw_model_response in enumerate(result.raw_responses):
                            print(f"{Colors.HEADER}Step {step_idx + 1}: Raw Model Response Type: {type(raw_model_response).__name__}{Colors.ENDC}")

                            if not hasattr(raw_model_response, 'output') or not isinstance(raw_model_response.output, list):
                                print(f"{Colors.LOG_WARNING}  Skipping raw_model_response: 'output' attribute missing or not a list.{Colors.ENDC}")
                                try: print(f"{Colors.LOG_WARNING}    Preview: {str(raw_model_response)[:200]}...{Colors.ENDC}")
                                except: pass
                                continue

                            for output_item_idx, output_item in enumerate(raw_model_response.output):
                                print(f"{Colors.SYSTEM_INFO}  Output Item [{output_item_idx+1}] Type: {type(output_item).__name__}{Colors.ENDC}")
                                item_processed_for_verbose = False

                                if hasattr(output_item, 'arguments'): 
                                    item_processed_for_verbose = True
                                    tool_name_attr = getattr(output_item, 'name', None)
                                    if tool_name_attr is None: 
                                        if hasattr(output_item, 'function_call') and hasattr(output_item.function_call, 'name'):
                                            tool_name_attr = output_item.function_call.name
                                        elif hasattr(output_item, 'tool_name'): 
                                            tool_name_attr = output_item.tool_name

                                    tool_id_attr = getattr(output_item, 'id', f"generated_id_{step_idx}_{output_item_idx}")
                                    tool_args_str = output_item.arguments

                                    print(f"{Colors.TOOL_INFO}  Assistant Action (from Raw Response): Call Tool{Colors.ENDC}")
                                    print(f"{Colors.TOOL_INFO}    Tool Call ID: {tool_id_attr}{Colors.ENDC}")
                                    print(f"{Colors.TOOL_INFO}    Tool Name: {Colors.BOLD}{tool_name_attr or 'UnknownToolName'}{Colors.ENDC}")
                                    
                                    parsed_tool_args = None
                                    try:
                                        if isinstance(tool_args_str, str):
                                            parsed_tool_args = json.loads(tool_args_str)
                                        elif isinstance(tool_args_str, dict): 
                                            parsed_tool_args = tool_args_str
                                        else:
                                            parsed_tool_args = {'raw_arguments': tool_args_str}
                                        
                                        pretty_args = json.dumps(parsed_tool_args, indent=2, ensure_ascii=False)
                                        print(f"{Colors.AGENT_MESSAGE}    Arguments:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(pretty_args, '      ')}{Colors.ENDC}")

                                        is_execute_code = tool_name_attr == 'execute_code' or \
                                                          (not tool_name_attr and isinstance(parsed_tool_args, dict) and 'code' in parsed_tool_args)
                                        if is_execute_code and isinstance(parsed_tool_args, dict):
                                            code_to_execute = parsed_tool_args.get('code')
                                            if code_to_execute:
                                                print(f"{Colors.TOOL_INFO}      Code to be executed:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(code_to_execute, '        ')}{Colors.ENDC}")
                                    
                                    except json.JSONDecodeError as je:
                                        logger.warning(f"JSONDecodeError parsing arguments for {tool_name_attr} in Raw Response: {tool_args_str} - Error: {je}")
                                        print(f"{Colors.AGENT_MESSAGE}    Arguments (raw string, JSON decode failed):{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(str(tool_args_str), '      ')}{Colors.ENDC}")
                                    except Exception as e:
                                        logger.error(f"Error processing/displaying arguments for {tool_name_attr} in Raw Response: {tool_args_str} - Error: {e}")
                                        print(f"{Colors.AGENT_MESSAGE}    Arguments (error displaying):{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(str(tool_args_str), '      ')}{Colors.ENDC}")

                                elif hasattr(output_item, 'content') and isinstance(output_item.content, list) and \
                                     len(output_item.content) > 0 and hasattr(output_item.content[0], 'text') and \
                                     isinstance(output_item.content[0].text, str) :
                                    item_processed_for_verbose = True
                                    tool_response_content_str = output_item.content[0].text
                                    message_id = getattr(output_item, 'id', "unknown_message_id") 
                                    print(f"{Colors.AGENT_PROMPT}  Assistant Interpreted Tool Output (from Raw Response, msg_id: {message_id}){Colors.ENDC}")
                                    print(f"{Colors.AGENT_MESSAGE}{indent_multiline_text(tool_response_content_str, '    ')}{Colors.ENDC}")
                                
                                elif hasattr(output_item, 'text'): 
                                    item_processed_for_verbose = True
                                    print(f"{Colors.AGENT_PROMPT}  Assistant Says (direct text from Raw Response):{Colors.ENDC}")
                                    print(f"{Colors.AGENT_MESSAGE}{indent_multiline_text(output_item.text, '    ')}{Colors.ENDC}")
                                
                                if not item_processed_for_verbose:
                                    print(f"{Colors.LOG_WARNING}    Raw Response Output item has unknown structure: {str(output_item)[:200]}...{Colors.ENDC}")
                                print(f"{Colors.HEADER}  ---{Colors.ENDC}") 
                    
                    print(f"\n{Colors.SYSTEM_INFO}--- Processed Conversation History (SDK Messages) ---{Colors.ENDC}")
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
                    
                    print(f"{Colors.HEADER}--- End of Agent's Detailed Actions ---{Colors.ENDC}")
                    
                    print(f"\n{Colors.BOLD}{Colors.AGENT_PROMPT}Agent: {Colors.ENDC}")
                    print(f"{Colors.AGENT_MESSAGE}{result.final_output}{Colors.ENDC}")
                    
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
