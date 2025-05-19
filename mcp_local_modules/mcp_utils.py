import logging
import os
import subprocess
import venv

# Define ANSI color codes
class Colors:
    HEADER = '\033[95m'
    USER_PROMPT = '\033[92m'  # Green for user prompt
    AGENT_PROMPT = '\033[94m' # Blue for agent prompt
    AGENT_MESSAGE = '\033[96m'# Cyan for agent messages
    TOOL_INFO = '\033[93m'    # Yellow for tool related info
    CODE_OUTPUT = '\033[92m'  # Green for successful code output
    CODE_ERROR = '\033[91m'   # Red for code errors
    SYSTEM_INFO = '\033[94m'  # Blue for system messages
    LOG_NAME = '\033[94m'
    LOG_INFO = '\033[92m'
    LOG_WARNING = '\033[93m'
    LOG_ERROR = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Custom Formatter for logging
class ColoredFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG: Colors.LOG_INFO,
        logging.INFO: Colors.LOG_INFO,
        logging.WARNING: Colors.LOG_WARNING,
        logging.ERROR: Colors.LOG_ERROR,
        logging.CRITICAL: Colors.LOG_ERROR + Colors.BOLD,
    }

    def format(self, record):
        color = self.LEVEL_COLORS.get(record.levelno, Colors.ENDC)
        record.levelname = f"{color}{record.levelname}{Colors.ENDC}"
        record.name = f"{Colors.LOG_NAME}{record.name}{Colors.ENDC}"
        return super().format(record)

def setup_colored_logger(name, level=logging.INFO):
    """Sets up a logger with colored output."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(level)
        formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    
    logger.propagate = False
    return logger

def install_basic_packages(logger, venv_path):
    """Install basic packages in the virtual environment."""
    if os.name == 'nt':
        pip_path = os.path.join(venv_path, "Scripts", "pip.exe")
    else:
        pip_path = os.path.join(venv_path, "bin", "pip")
    
    if not os.path.exists(pip_path):
        logger.error(f"Pip not found at {pip_path}")
        return False
    
    packages = ["feedparser", "requests", "beautifulsoup4", "pandas", "matplotlib"]
    
    try:
        cmd = [pip_path, "install"] + packages
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if stderr:
            # Log warnings/errors but don't fail install for them unless returncode is non-zero
            # Some packages print to stderr for non-critical things
            logger.warning(f"Pip install stderr: {stderr.strip()}")
        
        if process.returncode != 0:
            logger.error(f"Failed to install packages. Pip return code: {process.returncode}\nStdout:\n{stdout}\nStderr:\n{stderr}")
            return False
        
        # logger.info(f"Pip install stdout: {stdout.strip()}") # Can be noisy
        return True
    except Exception as e:
        logger.error(f"Error installing packages: {e}")
        return False

def ensure_venv_exists(logger, venv_path):
    """Create a virtual environment if it doesn't exist."""
    created_new = False
    
    if os.path.exists(venv_path) and os.path.isdir(venv_path):
        if os.path.exists(os.path.join(venv_path, "Scripts", "activate")) or \
           os.path.exists(os.path.join(venv_path, "bin", "activate")):
            return True, False
    
    try:
        venv.create(venv_path, with_pip=True)
        created_new = True
        return True, created_new
    except Exception as e:
        logger.error(f"Failed to create virtual environment: {e}")
        return False, False

def indent_multiline_text(text, prefix="    "):
    """Indents each line of a given string."""
    if text is None:
        return prefix + "None"
    return "\n".join([prefix + line for line in str(text).splitlines()])