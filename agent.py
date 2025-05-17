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
# Assuming agents.Message and agents.ToolCall might be useful for type hinting or checking
# from agents import Message as AgentsMessage
# from agents.tools.entities import ToolCall as AgentsToolCall

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
        conversation_history_items = []

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
                    current_turn_input = conversation_history_items + [{"role": "user", "content": user_input_text}]
                    result = await Runner.run(starting_agent=agent, input=current_turn_input)
                    conversation_history_items = result.to_input_list()

                    if cli_args.verbose:
                        print(f"\n{Colors.HEADER}--- Agent's Detailed Actions (Verbose) ---{Colors.ENDC}")
                        if hasattr(result, 'raw_responses') and result.raw_responses:
                            for step_idx, raw_item in enumerate(result.raw_responses):
                                print(f"{Colors.HEADER}Step {step_idx + 1}: Type: {type(raw_item).__name__}{Colors.ENDC}")

                                item_role = None
                                item_content = None
                                item_tool_calls_list = None # For assistant requests (list of tool call objects)
                                item_tool_call_id = None    # For tool responses (single ID)
                                item_name_for_tool_response = None # For tool responses (name of the tool that was called)

                                # Check if raw_item is like an OpenAI SDK ChatCompletion object
                                if hasattr(raw_item, 'choices') and raw_item.choices and hasattr(raw_item.choices[0], 'message'):
                                    message_detail = raw_item.choices[0].message
                                    item_role = message_detail.role
                                    item_content = message_detail.content
                                    if hasattr(message_detail, 'tool_calls') and message_detail.tool_calls:
                                        item_tool_calls_list = message_detail.tool_calls # List of ChatCompletionMessageToolCall
                                    print(f"{Colors.SYSTEM_INFO}  Parsed as OpenAI SDK ChatCompletion structure.{Colors.ENDC}")
                                # Check if raw_item is like an agents.Message object
                                elif hasattr(raw_item, 'role'):
                                    item_role = raw_item.role
                                    item_content = raw_item.content
                                    if hasattr(raw_item, 'tool_calls') and raw_item.tool_calls:
                                        item_tool_calls_list = raw_item.tool_calls # List of agents.ToolCall
                                    if hasattr(raw_item, 'tool_call_id'):
                                        item_tool_call_id = raw_item.tool_call_id
                                    if hasattr(raw_item, 'name'): # 'name' is present for tool role messages
                                        item_name_for_tool_response = raw_item.name
                                    print(f"{Colors.SYSTEM_INFO}  Parsed as agents.Message structure.{Colors.ENDC}")
                                else:
                                    print(f"{Colors.LOG_WARNING}  Skipping raw_response item: Unknown structure.{Colors.ENDC}")
                                    try:
                                        print(f"{Colors.LOG_WARNING}    Item preview: {str(raw_item)[:200]}...{Colors.ENDC}")
                                    except: pass
                                    continue
                                
                                print(f"{Colors.TOOL_INFO}  Role: {Colors.BOLD}{item_role}{Colors.ENDC}")

                                if item_role == "assistant" and item_tool_calls_list:
                                    print(f"{Colors.TOOL_INFO}  Decision: Call tools ({len(item_tool_calls_list)} tool_call(s)){Colors.ENDC}")
                                    for tool_call_idx, tc_obj in enumerate(item_tool_calls_list):
                                        tool_name, tool_args_str, tool_id = None, None, None
                                        
                                        if hasattr(tc_obj, 'function'): # OpenAI ChatCompletionMessageToolCall
                                            tool_name = tc_obj.function.name
                                            tool_args_str = tc_obj.function.arguments
                                            tool_id = tc_obj.id
                                        elif hasattr(tc_obj, 'name') and hasattr(tc_obj, 'args'): # agents.ToolCall
                                            tool_name = tc_obj.name
                                            tool_args_str = tc_obj.args # args might be pre-parsed dict or str
                                            tool_id = tc_obj.id
                                        else:
                                            print(f"{Colors.LOG_WARNING}    Unknown tool_call object structure: {tc_obj}{Colors.ENDC}")
                                            continue

                                        print(f"{Colors.TOOL_INFO}    Tool Call [{tool_call_idx+1}] ID: {tool_id}{Colors.ENDC}")
                                        print(f"{Colors.TOOL_INFO}    Tool Name: {Colors.BOLD}{tool_name}{Colors.ENDC}")
                                        
                                        parsed_tool_args = None
                                        try:
                                            if isinstance(tool_args_str, str):
                                                parsed_tool_args = json.loads(tool_args_str)
                                            elif isinstance(tool_args_str, dict): # If args is already a dict (e.g. from agents.ToolCall)
                                                parsed_tool_args = tool_args_str
                                            else: # Fallback if not string or dict
                                                parsed_tool_args = {'raw_arguments': tool_args_str}


                                            pretty_args = json.dumps(parsed_tool_args, indent=2, ensure_ascii=False)
                                            print(f"{Colors.AGENT_MESSAGE}    Arguments:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(pretty_args, '      ')}{Colors.ENDC}")

                                            if tool_name == 'execute_code' and isinstance(parsed_tool_args, dict):
                                                code_to_execute = parsed_tool_args.get('code')
                                                if code_to_execute:
                                                    print(f"{Colors.TOOL_INFO}      Code to be executed:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(code_to_execute, '        ')}{Colors.ENDC}")
                                        
                                        except json.JSONDecodeError as je:
                                            logger.warning(f"JSONDecodeError parsing arguments for {tool_name}: {tool_args_str} - Error: {je}")
                                            print(f"{Colors.AGENT_MESSAGE}    Arguments (raw string, JSON decode failed):{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(str(tool_args_str), '      ')}{Colors.ENDC}")
                                        except Exception as e:
                                            logger.error(f"Error processing/displaying arguments for {tool_name}: {tool_args_str} - Error: {e}")
                                            print(f"{Colors.AGENT_MESSAGE}    Arguments (error displaying):{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(str(tool_args_str), '      ')}{Colors.ENDC}")

                                elif item_role == "tool":
                                    tool_display_name = item_name_for_tool_response or "UnknownTool" # Use 'name' from agents.Message if available
                                    print(f"{Colors.TOOL_INFO}  Tool Response (for Tool Call ID: {item_tool_call_id}, Tool Name: {Colors.BOLD}{tool_display_name}{Colors.ENDC})")
                                    
                                    is_error_response = False
                                    parsed_content_dict = None
                                    try:
                                        if isinstance(item_content, str):
                                            parsed_content_dict = json.loads(item_content)
                                        elif isinstance(item_content, dict): # If already a dict
                                            parsed_content_dict = item_content
                                        
                                        if parsed_content_dict and isinstance(parsed_content_dict, dict):
                                            status = parsed_content_dict.get('status')
                                            # Check for MCP Server's isError or standard error status
                                            if status == 'error' or parsed_content_dict.get('isError') == True:
                                                is_error_response = True
                                            
                                            pretty_content = json.dumps(parsed_content_dict, indent=2, ensure_ascii=False)
                                            display_color = Colors.CODE_ERROR if is_error_response else Colors.CODE_OUTPUT
                                            print(f"{display_color}{indent_multiline_text(pretty_content, '    ')}{Colors.ENDC}")

                                            # Specific pretty print for MCP Code Executor like structures
                                            if 'status' in parsed_content_dict and ('output' in parsed_content_dict or 'error' in parsed_content_dict or 'message' in parsed_content_dict or 'generated_filename' in parsed_content_dict or 'file_path' in parsed_content_dict):
                                                print(f"{Colors.TOOL_INFO}    Parsed Details:{Colors.ENDC}")
                                                if 'status' in parsed_content_dict: print(f"{Colors.BOLD}      Status:{Colors.ENDC} {parsed_content_dict['status']}")
                                                if 'file_path' in parsed_content_dict: print(f"{Colors.BOLD}      File Path:{Colors.ENDC} {parsed_content_dict['file_path']}")
                                                if 'generated_filename' in parsed_content_dict: print(f"{Colors.BOLD}      Generated Filename:{Colors.ENDC} {parsed_content_dict['generated_filename']}")
                                                out_val = parsed_content_dict.get('output')
                                                if out_val: print(f"{Colors.BOLD}      Output:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(out_val, '        ')}{Colors.ENDC}")
                                                err_val = parsed_content_dict.get('error')
                                                if err_val: print(f"{Colors.BOLD}      Error:{Colors.ENDC}\n{Colors.CODE_ERROR}{indent_multiline_text(err_val, '        ')}{Colors.ENDC}")
                                                msg_val = parsed_content_dict.get('message')
                                                if msg_val and not out_val and not err_val:
                                                    print(f"{Colors.BOLD}      Message:{Colors.ENDC}\n{Colors.CODE_OUTPUT}{indent_multiline_text(msg_val, '        ')}{Colors.ENDC}")
                                        else: # Not a dict after potential parsing, or was not a string/dict initially
                                            print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(str(item_content), '    ')}{Colors.ENDC}")
                                    except json.JSONDecodeError:
                                        # Not JSON, print as plain text
                                        print(f"{Colors.CODE_OUTPUT}{indent_multiline_text(str(item_content), '    ')}{Colors.ENDC}")
                                    except Exception as e:
                                        logger.error(f"Error displaying tool response content: {e}")
                                        print(f"{Colors.CODE_ERROR}{indent_multiline_text(str(item_content), '    ')} (Error parsing details: {e}){Colors.ENDC}")
                                
                                elif item_role == "user":
                                    print(f"{Colors.USER_PROMPT}  User Input (from history):{Colors.ENDC} {item_content}")
                                
                                elif item_role == "assistant" and item_content and not item_tool_calls_list: # Assistant's text response
                                    print(f"{Colors.AGENT_PROMPT}  Assistant Says (text response):{Colors.ENDC} {item_content}")
                                
                                elif item_role == "system":
                                    print(f"{Colors.SYSTEM_INFO}  System Message (from history):{Colors.ENDC} {item_content}")
                                
                                elif item_content: # Fallback for other roles or messages with content but not fitting above categories
                                    print(f"{Colors.SYSTEM_INFO}  Content:{Colors.ENDC} {item_content}")
                                
                                print(f"{Colors.HEADER}  ---{Colors.ENDC}") # End of step details

                        print(f"{Colors.HEADER}--- End of Agent's Detailed Actions ---{Colors.ENDC}")
                    
                    else: # Not verbose, print a summary of tools used if any
                        tool_names_used_in_turn = set()
                        if hasattr(result, 'raw_responses') and result.raw_responses:
                            for raw_item_summary in result.raw_responses:
                                current_tool_calls = None
                                if hasattr(raw_item_summary, 'choices') and raw_item_summary.choices and hasattr(raw_item_summary.choices[0], 'message'):
                                    msg_detail = raw_item_summary.choices[0].message
                                    if msg_detail.role == "assistant" and hasattr(msg_detail, 'tool_calls') and msg_detail.tool_calls:
                                        current_tool_calls = msg_detail.tool_calls
                                elif hasattr(raw_item_summary, 'role') and raw_item_summary.role == "assistant" and hasattr(raw_item_summary, 'tool_calls') and raw_item_summary.tool_calls:
                                    current_tool_calls = raw_item_summary.tool_calls

                                if current_tool_calls:
                                    for tc in current_tool_calls:
                                        if hasattr(tc, 'function'): # OpenAI SDK
                                            tool_names_used_in_turn.add(tc.function.name)
                                        elif hasattr(tc, 'name'): # agents.ToolCall
                                            tool_names_used_in_turn.add(tc.name)
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