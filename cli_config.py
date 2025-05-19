import os
import tiktoken
import logging

# ─── API AND REFERRER CONFIGURATION ───────────────────────────────────────────
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    # This will be caught by the main script's logger if it's an issue at startup.
    # For now, allow it to be None if not set, main script handles error.
    pass

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
YOUR_SITE_URL = os.getenv("OPENROUTER_REFERRER_URL", "http://localhost")
YOUR_SITE_NAME = os.getenv("OPENROUTER_SITE_NAME", "MCP Agent")

EXTRA_HEADERS = {
    "HTTP-Referer": YOUR_SITE_URL,
    "X-Title": YOUR_SITE_NAME,
}

# ─── MODEL DEFINITIONS AND MAPPINGS ───────────────────────────────────────────
SUPPORTED_MODELS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1-nano",
    "openai/o4-mini",
]
DEFAULT_MODEL = "openai/gpt-4o-mini"

# Mapping for supported models to tiktoken base model names or direct encoding names
TIKTOKEN_MAPPING = {
    "openai/gpt-4o-mini": ("model", "gpt-4o"),
    "openai/gpt-4.1-mini": ("model", "gpt-4o"), # Assuming gpt-4o compatibility
    "openai/gpt-4.1-nano": ("model", "gpt-4o"), # Assuming gpt-4o compatibility
    "openai/o4-mini": ("model", "gpt-4o"),      # Assuming gpt-4o compatibility
}

# ─── PRICING CONFIGURATION (Placeholder for gpt-4o-mini) ────────────────────
# TODO: Implement dynamic pricing based on current_model_name
PROMPT_PRICE_PER_1K = 0.00015  # gpt-4o-mini input price
COMPLETION_PRICE_PER_1K = 0.0006   # gpt-4o-mini output price

# ─── TOKENIZER INITIALIZATION FUNCTION ────────────────────────────────────────
def initialize_tokenizer(model_name: str, tiktoken_map: dict, logger_instance: logging.Logger) -> tiktoken.Encoding:
    """
    Initializes and returns a tiktoken encoding for the given model.
    """
    _map_type, _map_value = tiktoken_map.get(model_name, (None, None))

    enc = None
    if "claude" in model_name: # Specific handling for Claude models
        enc = tiktoken.encoding_for_model("gpt-4") # Use gpt-4 tokenizer for Claude
        logger_instance.info(f"Using 'gpt-4' base model for tiktoken with Claude model: {model_name}")
    elif _map_type == "encoding":
        enc = tiktoken.get_encoding(_map_value)
        logger_instance.info(f"Using '{_map_value}' encoding for {model_name}.")
    elif _map_type == "model":
        enc = tiktoken.encoding_for_model(_map_value)
        logger_instance.info(f"Using '{_map_value}' base model for tiktoken with {model_name}.")
    else: # Fallback for models not in TIKTOKEN_MAPPING and not Claude
        logger_instance.warning(f"No specific tiktoken mapping for {model_name}. Attempting 'cl100k_base' encoding.")
        try:
            enc = tiktoken.get_encoding("cl100k_base")
        except Exception as e_enc:
            logger_instance.error(f"Failed to get 'cl100k_base' as fallback for {model_name}: {e_enc}. Using 'gpt2' encoding.")
            enc = tiktoken.get_encoding("gpt2") # A very basic fallback
    return enc
