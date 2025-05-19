import logging
import os
from typing import List, Tuple, Any, Dict, Optional
import tiktoken
from openai import OpenAI # Needed to instantiate a new client for Ollama

from mcp_local_modules.mcp_agent_setup import setup_agent
from mcp_local_modules.mcp_utils import Colors
from . import cli_config # Import the whole module to allow modifying its attributes
from .cli_config import initialize_tokenizer

# Globals that will be managed by this module, similar to how they were in agentcli.py
# These are intended to be updated by _update_model_and_agent_config and accessed by the main CLI.
# This approach mirrors the original global usage but centralizes the update logic.
# Consider passing these as part of a state object in a more complex application.
current_model_name_global: str = "" # Will be set by the main script initially
tokenizer_global: Optional[tiktoken.Encoding] = None # Will be set by the main script initially

async def update_model_and_agent_config(
    new_model_name: str,
    logger_instance: logging.Logger,
    servers_list: List[Any],
    base_samples_dir: str,
    openrouter_client: Any,   # The pre-configured OpenRouter client instance
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
    
    current_model_name_global = new_model_name

    client_to_use = openrouter_client
    model_name_for_setup = current_model_name_global

    if new_model_name.startswith("ollama/"):
        logger_instance.info(f"Configuring for Ollama model: {new_model_name}")
        # Use Ollama specific configurations
        client_to_use = OpenAI(
            base_url=cli_config.OLLAMA_BASE_URL,
            api_key="ollama", # Use a dummy API key for Ollama, as it requires a non-None value
        )
        model_name_for_setup = new_model_name.split('/')[-1] # e.g., "llama3" from "ollama/llama3"
        
        # Set environment variables for the Agent class to use
        os.environ["OPENAI_API_KEY"] = "ollama"  # Dummy API key
        os.environ["OPENAI_BASE_URL"] = cli_config.OLLAMA_BASE_URL
        logger_instance.info(f"Set environment variables for Ollama: OPENAI_BASE_URL={cli_config.OLLAMA_BASE_URL}")
        
        # Update pricing in cli_config (this modifies the imported module's attributes)
        cli_config.PROMPT_PRICE_PER_1K = cli_config.OLLAMA_PROMPT_PRICE_PER_1K
        cli_config.COMPLETION_PRICE_PER_1K = cli_config.OLLAMA_COMPLETION_PRICE_PER_1K
        logger_instance.info(f"Set pricing for Ollama: Prompt=${cli_config.PROMPT_PRICE_PER_1K}/1k, Completion=${cli_config.COMPLETION_PRICE_PER_1K}/1k")

    else: # Assuming OpenRouter model
        logger_instance.info(f"Configuring for OpenRouter model: {new_model_name}")
        # Use OpenRouter specific configurations (or defaults if not overridden)
        # Pricing for OpenRouter models (using OpenAI as a stand-in for now)
        cli_config.PROMPT_PRICE_PER_1K = cli_config.OPENAI_PROMPT_PRICE_PER_1K
        cli_config.COMPLETION_PRICE_PER_1K = cli_config.OPENAI_COMPLETION_PRICE_PER_1K
        logger_instance.info(f"Set pricing for OpenRouter/OpenAI: Prompt=${cli_config.PROMPT_PRICE_PER_1K}/1k, Completion=${cli_config.COMPLETION_PRICE_PER_1K}/1k")
        # client_to_use is already openrouter_client, model_name_for_setup is new_model_name

    # Re-initialize agent with the new model and appropriate client
    new_agent_instance, new_instructions = setup_agent(
        logger_instance,
        servers_list,
        base_samples_dir,
        model_name=model_name_for_setup, # Use the potentially stripped model name for Ollama
        client=client_to_use,           # Use the client specific to the service
        extra_headers=extra_headers if not new_model_name.startswith("ollama/") else None # Ollama might not need/use these headers
    )
    
    # Re-initialize tokenizer for the new model (using the full name like "ollama/llama3" for mapping)
    tokenizer_global = initialize_tokenizer(current_model_name_global, tiktoken_map, logger_instance)
            
    print(f"{Colors.SYSTEM_INFO}Model changed from {old_model_for_message} to: {current_model_name_global}{Colors.ENDC}")
    print(f"{Colors.SYSTEM_INFO}Effective model for API: {model_name_for_setup}, Base URL: {client_to_use.base_url}{Colors.ENDC}")
    
    return new_agent_instance, new_instructions, current_model_name_global, tokenizer_global
