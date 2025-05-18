import logging
from typing import List, Tuple, Any, Dict, Optional # Any for agent, http_client, servers_list
import tiktoken

from mcp_agent_setup import setup_agent # For re-initializing the agent
from mcp_utils import Colors # For printing colored messages
from cli_config import initialize_tokenizer # For re-initializing the tokenizer

# Globals that will be managed by this module, similar to how they were in agentcli.py
# These are intended to be updated by _update_model_and_agent_config and accessed by the main CLI.
# This approach mirrors the original global usage but centralizes the update logic.
# Consider passing these as part of a state object in a more complex application.
current_model_name_global: str = "" # Will be set by the main script initially
tokenizer_global: Optional[tiktoken.Encoding] = None # Will be set by the main script initially

async def update_model_and_agent_config(
    new_model_name: str,
    logger_instance: logging.Logger,
    servers_list: List[Any],  # List of server instances
    base_samples_dir: str,
    http_client: Any,         # The OpenAI client instance
    extra_headers: Dict[str, str],
    tiktoken_map: Dict[str, Tuple[str, str]],
    supported_model_list: List[str]
) -> Tuple[Any, str, str, Optional[tiktoken.Encoding]]:
    """
    Updates the global current model, re-initializes the agent and tokenizer.
    Returns the new agent instance, new agent instructions, the new model name, and the new tokenizer.
    """
    global current_model_name_global, tokenizer_global # Allow modification of these module-level globals

    if new_model_name not in supported_model_list:
        logger_instance.error(f"Internal error: Attempted to switch to an unsupported model: {new_model_name}")
        # In case of error, return the current global state without changes
        # This requires current_model_name_global and tokenizer_global to be initialized before first call
        # And also requires the current agent and instructions to be passed in or fetched if we want to return them.
        # For simplicity, this path should ideally not be hit if called from main CLI logic correctly.
        # Raising an error might be more appropriate if this state is truly invalid.
        raise ValueError(f"Unsupported model: {new_model_name}")

    old_model_for_message = current_model_name_global
    logger_instance.info(f"Changing model from {old_model_for_message} to {new_model_name}")
    
    current_model_name_global = new_model_name # Update global model name

    # Re-initialize agent with the new model
    new_agent_instance, new_instructions = setup_agent(
        logger_instance,
        servers_list,
        base_samples_dir,
        model_name=current_model_name_global,
        client=http_client,
        extra_headers=extra_headers
    )
    
    # Re-initialize tokenizer for the new model
    tokenizer_global = initialize_tokenizer(current_model_name_global, tiktoken_map, logger_instance)
            
    print(f"{Colors.SYSTEM_INFO}Model changed from {old_model_for_message} to: {current_model_name_global}{Colors.ENDC}")
    # TODO: Implement dynamic pricing update if model changes (original TODO from agentcli.py)
    
    return new_agent_instance, new_instructions, current_model_name_global, tokenizer_global
