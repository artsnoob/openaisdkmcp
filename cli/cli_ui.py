import sys
import tty
import termios
from typing import List, Optional, Any # Any for Colors module/class

# ─── HELPER FUNCTION FOR INTERACTIVE MODEL SELECTION ───────────────────────────
def select_model_interactive(
    prompt_title: str,
    options: List[str],
    active_model_value: str,
    colors_module: Any # Using Any to represent the Colors class/module passed in
) -> Optional[str]:
    """
    Provides an interactive command-line interface for selecting a model.
    Uses raw terminal mode for arrow key navigation.
    """
    old_settings = termios.tcgetattr(sys.stdin.fileno())
    try:
        tty.setraw(sys.stdin.fileno())

        if not options:
            sys.stdout.write(f"{colors_module.LOG_ERROR}No models available for selection.{colors_module.ENDC}\r\n")
            sys.stdout.flush()
            # Wait for a key press before returning, to allow user to see the message
            sys.stdin.read(1)
            return None

        try:
            current_selection_index = options.index(active_model_value)
        except ValueError:
            # If active_model_value is not in options (e.g., if it was removed or is invalid),
            # default to the first option.
            current_selection_index = 0

        while True:
            # Clear screen or redraw in place (using ANSI codes)
            # \033c is a common sequence for resetting the terminal, often clearing it.
            sys.stdout.write("\033c")

            sys.stdout.write(f"{prompt_title}\r\n")
            sys.stdout.write(f"{colors_module.SYSTEM_INFO}Use ARROW UP/DOWN to navigate, ENTER to select, ESC to cancel.{colors_module.ENDC}\r\n\r\n")

            for i, option in enumerate(options):
                prefix = "> " if i == current_selection_index else "  "

                display_option_text = option
                if option == active_model_value:
                    display_option_text += " (current)"

                if i == current_selection_index:
                    # Highlight the current selection
                    sys.stdout.write(f"{colors_module.USER_PROMPT}{prefix}{colors_module.BOLD}{display_option_text}{colors_module.ENDC}{colors_module.ENDC}\r\n")
                else:
                    sys.stdout.write(f"{colors_module.SYSTEM_INFO}{prefix}{display_option_text}{colors_module.ENDC}\r\n")
            sys.stdout.flush()

            # Read a single character for input
            char = sys.stdin.read(1)

            if char == '\x1b':  # Escape character (used for ESC key and arrow keys)
                # Try to read the rest of an escape sequence (non-blocking if possible, but read(1) is blocking)
                next_char1 = sys.stdin.read(1) # If it's just ESC, this might block or get next input
                if next_char1 == '[': # Start of a CSI sequence (e.g., arrow keys)
                    next_char2 = sys.stdin.read(1)
                    if next_char2 == 'A':  # Up arrow
                        current_selection_index = (current_selection_index - 1 + len(options)) % len(options)
                    elif next_char2 == 'B':  # Down arrow
                        current_selection_index = (current_selection_index + 1) % len(options)
                    # Other CSI sequences (like Home, End, other arrows) could be handled here if needed
                else: # Likely just the ESC key pressed (\x1b followed by something not '[' or nothing)
                    sys.stdout.write("\033c") # Clear screen
                    sys.stdout.flush()
                    return None # Cancelled
            elif char == '\r' or char == '\n':  # Enter key
                sys.stdout.write("\033c") # Clear screen
                sys.stdout.flush()
                return options[current_selection_index]
            elif char == '\x03': # Ctrl+C
                # Restore terminal settings before raising KeyboardInterrupt
                termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
                raise KeyboardInterrupt
            # Ignore other characters
    finally:
        # Always restore terminal settings
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old_settings)
# ─── END HELPER FUNCTION ───────────────────────────────────────────────────────
from mcp_local_modules.mcp_utils import Colors # For printing colored messages
