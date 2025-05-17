import logging
import os
import subprocess
import venv

# Define ANSI color codes
class Colors:
    HEADER = '\033[95m'
    USER_PROMPT = '\033[92m'
    AGENT_PROMPT = '\033[94m'
    AGENT_MESSAGE = '\033[96m'
    TOOL_INFO = '\033[93m'
    CODE_OUTPUT = '\033[92m'
    CODE_ERROR = '\033[91m'
    SYSTEM_INFO = '\033[94m'
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
    
    # Prevent adding multiple handlers if logger already configured
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(level) # Set handler level, could be different from logger level
        formatter = ColoredFormatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    
    logger.propagate = False # Prevent duplicate logs if root logger is also configured
    return logger

def install_basic_packages(logger, venv_path):
    """Install basic packages in the virtual environment."""
    # logger.info("Installing basic packages in the virtual environment...") # Reduced verbosity
    
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
        # logger.info(f"Running command: {' '.join(cmd)}") # Reduced verbosity
        
        process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate()
        
        if stdout:
            # logger.info(f"Pip install output: {stdout}") # Reduced verbosity - can be very noisy
            pass # Still capture stdout if needed for debugging, but don't log by default
        if stderr:
            logger.warning(f"Pip install warnings/errors: {stderr}")
        
        if process.returncode != 0:
            logger.error(f"Failed to install packages. Return code: {process.returncode}")
            return False
        
        # logger.info("Basic packages installed successfully") # Reduced verbosity
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
            # logger.info(f"Virtual environment already exists at {venv_path}") # Reduced verbosity
            return True, False
    
    # logger.info(f"Creating virtual environment at {venv_path}...") # Reduced verbosity
    try:
        venv.create(venv_path, with_pip=True)
        # logger.info(f"Virtual environment created successfully at {venv_path}") # Reduced verbosity
        created_new = True
        return True, created_new
    except Exception as e:
        logger.error(f"Failed to create virtual environment: {e}")
        return False, False

