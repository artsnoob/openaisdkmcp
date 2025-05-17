import asyncio
import os
import shutil
import logging
import sys
import argparse
import json
from dotenv import load_dotenv
from contextlib import asynccontextmanager

from agents import Runner, trace

from mcp_utils import Colors, setup_colored_logger, install_basic_packages, ensure_venv_exists, indent_multiline_text
from mcp_server_config import configure_servers
from mcp_agent_setup import setup_agent

logger = setup_colored_logger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)

load_dotenv()

if not shutil.which("npx"):
    logger.error("npx command not found. Please install Node.js and npm from https://nodejs.org/")
    raise RuntimeError("npx command not found.")
if not shutil.which("uvx"):
    logger.error("uvx command not found. Please ensure uvx (part of uv) is installed and in your PATH. See https://github.com/astral-sh/uv")
    raise RuntimeError("uvx command not found.")

parser = argparse.ArgumentParser(description="Run the MCP Agent CLI.")
parser.add_argument(
    "-v", "--verbose",
    action="store_true",
    help="Enable verbose output, showing detailed agent actions and tool interactions."
)

async def main():
    cli_args = parser.parse_args()

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

    agent, agent_instructions_text = setup_agent(logger, successfully_connected_servers, samples_dir)
    
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
        print(f"{Colors.SYSTEM_INFO}Type 'quit' or 'exit' to end the session. Type '/instructions' to see agent prompts.{Colors.ENDC}")
        current_conversation_history = [] # Renamed to avoid confusion with the module name

        with trace("MCP Interactive Session"):
            while True:
                try:
                    user_input_text = input(f"\n{Colors.BOLD}{Colors.USER_PROMPT}You: {Colors.ENDC}")
                    if user_input_text.lower() in ["quit", "exit"]:
                        print(f"{Colors.SYSTEM_INFO}Exiting chat.{Colors.ENDC}")
                        break
                    
                    if user_input_text.lower() == "/instructions":
                        print(f"\n{Colors.HEADER}--- Agent Instructions ---{Colors.ENDC}")
                        print(f"{Colors.SYSTEM_INFO}{agent_instructions_text}{Colors.ENDC}")
                        print(f"{Colors.HEADER}------------------------{Colors.ENDC}")
                        continue

                    print(f"{Colors.SYSTEM_INFO}Agent is processing...{Colors.ENDC}")
                    current_turn_input = current_conversation_history + [{"role": "user", "content": user_input_text}]
                    result = await Runner.run(starting_agent=agent, input=current_turn_input)
                    current_conversation_history = result.to_input_list() 

                    if cli_args.verbose:
                        print(f"\n{Colors.HEADER}--- Agent's Detailed Actions (Verbose) ---{Colors.ENDC}")
                        # 1. Log Raw Model Responses (as before)
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
                                        # ... (rest of the assistant tool call display logic - unchanged) ...
                                        tool_name_attr = getattr(output_item, 'name', None)
                                        if tool_name_attr is None:
                                            if hasattr(output_item, 'function_call') and hasattr(output_item.function_call, 'name'):
                                                tool_name_attr = output_item.function_call.name
                                            elif hasattr(output_item, 'tool_name'): 
                                                tool_name_attr = output_item.tool_name

                                        tool_id_attr = getattr(output_item, 'id', f"generated_id_{step_idx}_{output_item_idx}")
                                        tool_args_str = output_item.arguments

                                        print(f"{Colors.TOOL_INFO}  Assistant Action: Call Tool{Colors.ENDC}")
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
                                            logger.warning(f"JSONDecodeError parsing arguments for {tool_name_attr}: {tool_args_str} - Error: {je}")
                                            print(f"{Colors.AGENT_MESSAGE}    Arguments (raw string, JSON decode failed):{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(str(tool_args_str), '      ')}{Colors.ENDC}")
                                        except Exception as e:
                                            logger.error(f"Error processing/displaying arguments for {tool_name_attr}: {tool_args_str} - Error: {e}")
                                            print(f"{Colors.AGENT_MESSAGE}    Arguments (error displaying):{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(str(tool_args_str), '      ')}{Colors.ENDC}")

                                    elif hasattr(output_item, 'content') and isinstance(output_item.content, list) and \
                                         len(output_item.content) > 0 and hasattr(output_item.content[0], 'text') and \
                                         isinstance(output_item.content[0].text, str) :
                                        item_processed_for_verbose = True
                                        # ... (rest of the tool response display from ModelResponse's ResponseOutputMessage content - unchanged) ...
                                        tool_response_content_str = output_item.content[0].text
                                        message_id = getattr(output_item, 'id', "unknown_message_id") 
                                        tool_call_id_for_response = "unknown_tool_call_id"
                                        tool_name_for_response = "UnknownTool (from ResponseOutputMessage)"
                                        temp_history_for_linking = result.to_input_list() 
                                        for hist_msg in reversed(temp_history_for_linking):
                                            if hist_msg.get('role') == 'assistant' and hist_msg.get('tool_calls'):
                                                if hist_msg.get('tool_calls')[0].get('id'):
                                                    tool_call_id_for_response = hist_msg.get('tool_calls')[0].get('id')
                                                    called_func_info = hist_msg.get('tool_calls')[0].get('function', {})
                                                    tool_name_for_response = called_func_info.get('name', tool_name_for_response)
                                                break 

                                        print(f"{Colors.TOOL_INFO}  Tool Execution Result (for call ~{tool_call_id_for_response}, tool ~{tool_name_for_response}, msg_id: {message_id}){Colors.ENDC}")
                                        is_error_response = False
                                        parsed_content_dict = None
                                        try:
                                            parsed_content_dict = json.loads(tool_response_content_str)
                                            if isinstance(parsed_content_dict, dict):
                                                status = parsed_content_dict.get('status')
                                                if status == 'error' or parsed_content_dict.get('isError'):
                                                    is_error_response = True
                                                pretty_content = json.dumps(parsed_content_dict, indent=2, ensure_ascii=False)
                                                display_color = Colors.CODE_ERROR if is_error_response else Colors.CODE_OUTPUT
                                                print(f"{display_color}{indent_multiline_text(pretty_content, '    ')}{Colors.ENDC}")

                                                if 'status' in parsed_content_dict: 
                                                    print(f"{Colors.TOOL_INFO}    Parsed Details:{Colors.ENDC}")
                                                    if 'status' in parsed_content_dict: print(f"{Colors.BOLD}      Status:{Colors.ENDC} {parsed_content_dict['status']}")
                                                    if 'file_path' in parsed_content_dict: print(f"{Colors.BOLD}      File Path:{Colors.ENDC} {parsed_content_dict['file_path']}")
                                                    if 'generated_filename' in parsed_content_dict: print(f"{Colors.BOLD}      Generated Filename:{Colors.ENDC} {parsed_content_dict['generated_filename']}")
                                                    out_val = parsed_content_dict.get('output')
                                                    if out_val: print(f"{Colors.BOLD}      Output:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(out_val, '        ')}{Colors.ENDC}")
                                                    err_val = parsed_content_dict.get('error')
                                                    if err_val: print(f"{Colors.BOLD}      Error:{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(err_val, '        ')}{Colors.ENDC}")
                                                    msg_val = parsed_content_dict.get('message')
                                                    if msg_val and not out_val and not err_val: print(f"{Colors.BOLD}      Message:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(msg_val, '        ')}{Colors.ENDC}")
                                            else: 
                                                print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(str(tool_response_content_str), '    ')}{Colors.ENDC}")
                                        except json.JSONDecodeError: 
                                            print(f"{Colors.AGENT_MESSAGE}  Tool Response Text (not JSON):{Colors.ENDC}") 
                                            print(f"{Colors.AGENT_MESSAGE}{indent_multiline_text(tool_response_content_str, '    ')}{Colors.ENDC}")
                                        except Exception as e:
                                            logger.error(f"Error displaying tool response content: {e}")
                                            print(f"{Colors.CODE_ERROR}{indent_multiline_text(str(tool_response_content_str), '    ')} (Error parsing details: {e}){Colors.ENDC}")
                                    
                                    elif hasattr(output_item, 'text'):
                                        item_processed_for_verbose = True
                                        # ... (rest of assistant text display logic - unchanged) ...
                                        print(f"{Colors.AGENT_PROMPT}  Assistant Says (direct text output):{Colors.ENDC}")
                                        print(f"{Colors.AGENT_MESSAGE}{indent_multiline_text(output_item.text, '    ')}{Colors.ENDC}")
                                    
                                    if not item_processed_for_verbose:
                                        print(f"{Colors.LOG_WARNING}    Output item has unknown structure for verbose display: {str(output_item)[:200]}...{Colors.ENDC}")
                                    print(f"{Colors.HEADER}  ---{Colors.ENDC}")
                        
                        # 2. Log the processed conversation_history_items to see the tool's direct output
                        print(f"\n{Colors.SYSTEM_INFO}--- Processed Conversation History (for direct tool output) ---{Colors.ENDC}")
                        for hist_idx, hist_item in enumerate(current_conversation_history): # Use the updated history
                            role = hist_item.get('role')
                            print(f"{Colors.HEADER}History Item {hist_idx + 1}: Role: {role}{Colors.ENDC}")
                            if role == 'user':
                                print(f"{Colors.USER_PROMPT}  Content: {hist_item.get('content')}{Colors.ENDC}")
                            elif role == 'assistant':
                                if hist_item.get('tool_calls'):
                                    # This is the OpenAI structure for tool_calls in history
                                    print(f"{Colors.TOOL_INFO}  Tool Calls (OpenAI format):{Colors.ENDC}")
                                    for tc_idx, tc_call in enumerate(hist_item.get('tool_calls')):
                                        func_details = tc_call.get('function', {})
                                        print(f"{Colors.TOOL_INFO}    Call [{tc_idx+1}] ID: {tc_call.get('id')}{Colors.ENDC}")
                                        print(f"{Colors.TOOL_INFO}      Function Name: {Colors.BOLD}{func_details.get('name')}{Colors.ENDC}")
                                        print(f"{Colors.AGENT_MESSAGE}      Arguments: {func_details.get('arguments')}{Colors.ENDC}")
                                if hist_item.get('content'): # Assistant's text response
                                    print(f"{Colors.AGENT_PROMPT}  Content: {hist_item.get('content')}{Colors.ENDC}")
                            elif role == 'tool':
                                print(f"{Colors.TOOL_INFO}  Tool Response (for Tool Call ID: {hist_item.get('tool_call_id')}){Colors.ENDC}")
                                print(f"{Colors.TOOL_INFO}    Tool Name Used: {Colors.BOLD}{hist_item.get('name')}{Colors.ENDC}")
                                tool_content_str = hist_item.get('content', '')
                                print(f"{Colors.TOOL_INFO}    Content (This should be the direct JSON from MCP server):{Colors.ENDC}")
                                try:
                                    # Attempt to parse and pretty-print if it's JSON
                                    parsed_tool_output = json.loads(tool_content_str)
                                    pretty_tool_output = json.dumps(parsed_tool_output, indent=2, ensure_ascii=False)
                                    
                                    # Check for error status within the parsed JSON
                                    is_error_tool_response = False
                                    if isinstance(parsed_tool_output, dict):
                                        if parsed_tool_output.get('status') == 'error' or parsed_tool_output.get('isError'):
                                            is_error_tool_response = True
                                    
                                    display_color = Colors.CODE_ERROR if is_error_tool_response else Colors.CODE_OUTPUT
                                    print(f"{display_color}{indent_multiline_text(pretty_tool_output, '      ')}{Colors.ENDC}")

                                    # Also show the detailed breakdown if it matches mcp_code_executor structure
                                    if isinstance(parsed_tool_output, dict) and 'status' in parsed_tool_output:
                                        print(f"{Colors.TOOL_INFO}      Parsed Details from Tool Content:{Colors.ENDC}")
                                        if 'status' in parsed_tool_output: print(f"{Colors.BOLD}        Status:{Colors.ENDC} {parsed_tool_output['status']}")
                                        if 'file_path' in parsed_tool_output: print(f"{Colors.BOLD}        File Path:{Colors.ENDC} {parsed_tool_output['file_path']}")
                                        if 'generated_filename' in parsed_tool_output: print(f"{Colors.BOLD}        Generated Filename:{Colors.ENDC} {parsed_tool_output['generated_filename']}")
                                        out_val = parsed_tool_output.get('output')
                                        if out_val: print(f"{Colors.BOLD}        Output:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(out_val, '          ')}{Colors.ENDC}")
                                        err_val = parsed_tool_output.get('error')
                                        if err_val: print(f"{Colors.BOLD}        Error:{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(err_val, '          ')}{Colors.ENDC}")
                                        msg_val = parsed_tool_output.get('message')
                                        if msg_val and not out_val and not err_val: print(f"{Colors.BOLD}        Message:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(msg_val, '          ')}{Colors.ENDC}")

                                except json.JSONDecodeError:
                                    # If not JSON, print as raw string
                                    print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(tool_content_str, '      ')}{Colors.ENDC}")
                                except Exception as e:
                                    logger.error(f"Error displaying tool content from history: {e}")
                                    print(f"{Colors.CODE_ERROR}{indent_multiline_text(tool_content_str, '      ')} (Error formatting: {e}){Colors.ENDC}")
                            print(f"{Colors.HEADER}  ---{Colors.ENDC}")
                        print(f"{Colors.HEADER}--- End of Agent's Detailed Actions ---{Colors.ENDC}")
                    
                    # Non-verbose summary
                    else:
                        # ... (non-verbose summary logic - unchanged) ...
                        tool_names_used_in_turn = set()
                        start_index_for_turn = 0
                        for i in range(len(current_conversation_history) - 1, -1, -1):
                            if current_conversation_history[i].get('role') == 'user':
                                start_index_for_turn = i
                                break
                        
                        for i in range(start_index_for_turn, len(current_conversation_history)):
                            hist_item = current_conversation_history[i]
                            if hist_item.get('role') == 'assistant' and hist_item.get('tool_calls'):
                                for tc in hist_item.get('tool_calls'):
                                    func_details = tc.get('function', {})
                                    tool_name = func_details.get('name')
                                    if tool_name:
                                        tool_names_used_in_turn.add(tool_name)
                            elif hist_item.get('role') == 'tool' and hist_item.get('name'):
                                tool_names_used_in_turn.add(hist_item.get('name'))
                        
                        tool_names_used_in_turn.discard(None)

                        if tool_names_used_in_turn:
                             print(f"\n{Colors.TOOL_INFO}[Tools Used This Turn: {', '.join(sorted(list(tool_names_used_in_turn)))}]{Colors.ENDC}")

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