import datetime
import json
import os
import platform
import re
import sys

# Define ANSI escape codes for colors
class _AnsiColors:
    """Helper class for ANSI escape codes for console text styling."""
    RESET = "\033[0m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    BLUE = "\033[94m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    UNDERLINE = "\033[4m"

def auto_helper_dev_kit(task: str, **kwargs) -> str:
    """
    A lightweight, developer-friendly utility toolkit for various common tasks.

    This function provides a centralized way to perform operations like
    text formatting, color logging, regex searching, date/time manipulation,
    system information retrieval, and JSON parsing.

    Args:
        task (str): The specific utility task to perform.
                    Supported tasks:
                    - "format_text": Formats a given text string.
                        Requires: 'text' (str).
                        Optional: 'width' (int, default 80), 'align' (str: 'left', 'center', 'right', default 'left'),
                                  'fillchar' (str, default ' ').
                    - "log_message": Generates a colored log message string.
                        Requires: 'message' (str).
                        Optional: 'level' (str: 'info', 'warn', 'error', 'success', 'debug', default 'info').
                    - "regex_search": Performs a regex operation on a string.
                        Requires: 'text' (str), 'pattern' (str).
                        Optional: 'match_type' (str: 'search', 'findall', 'fullmatch', default 'search').
                    - "get_current_datetime": Returns the current date and time.
                        Optional: 'format' (str, standard strftime format, default '%Y-%m-%d %H:%M:%S').
                    - "get_system_info": Retrieves various system details.
                        No additional arguments needed.
                    - "parse_json": Parses a JSON string and returns its pretty-printed representation.
                        Requires: 'json_string' (str).
                    - "pretty_print_json": Pretty-prints a Python dictionary or list as a JSON string.
                        Requires: 'data' (dict or list).
        **kwargs: Additional arguments specific to the chosen task.

    Returns:
        str: A string containing the result of the operation, or an error message.
             Output messages include ANSI color codes for enhanced readability when printed to a terminal.
    """

    output_lines = []

    if task == "format_text":
        text = kwargs.get("text")
        width = kwargs.get("width", 80)
        align = kwargs.get("align", "left")
        fillchar = kwargs.get("fillchar", " ")

        if not isinstance(text, str):
            return f"{_AnsiColors.RED}Error: 'text' argument is required and must be a string for 'format_text'.{_AnsiColors.RESET}"
        if not isinstance(fillchar, str) or len(fillchar) != 1:
            return f"{_AnsiColors.RED}Error: 'fillchar' must be a single character string for 'format_text'.{_AnsiColors.RESET}"

        if align == "center":
            output_lines.append(text.center(width, fillchar))
        elif align == "right":
            output_lines.append(text.rjust(width, fillchar))
        else: # default to left
            output_lines.append(text.ljust(width, fillchar))

    elif task == "log_message":
        message = kwargs.get("message")
        level = kwargs.get("level", "info").lower()

        if not isinstance(message, str):
            return f"{_AnsiColors.RED}Error: 'message' argument is required and must be a string for 'log_message'.{_AnsiColors.RESET}"

        color_prefix = _AnsiColors.BLUE # Default info
        if level == "error":
            color_prefix = _AnsiColors.RED + _AnsiColors.BOLD
        elif level == "warn":
            color_prefix = _AnsiColors.YELLOW
        elif level == "success":
            color_prefix = _AnsiColors.GREEN
        elif level == "debug":
            color_prefix = _AnsiColors.CYAN
        elif level == "info":
            color_prefix = _AnsiColors.BLUE
        else:
            color_prefix = _AnsiColors.MAGENTA # Unknown level

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        output_lines.append(f"{color_prefix}{timestamp} [{level.upper()}] {message}{_AnsiColors.RESET}")

    elif task == "regex_search":
        text = kwargs.get("text")
        pattern = kwargs.get("pattern")
        match_type = kwargs.get("match_type", "search")

        if not isinstance(text, str) or not isinstance(pattern, str):
            return f"{_AnsiColors.RED}Error: 'text' and 'pattern' arguments are required and must be strings for 'regex_search'.{_AnsiColors.RESET}"

        try:
            if match_type == "findall":
                matches = re.findall(pattern, text)
                if matches:
                    output_lines.append(f"Found {_AnsiColors.GREEN}{len(matches)}{_AnsiColors.RESET} matches: {_AnsiColors.CYAN}{', '.join(matches)}{_AnsiColors.RESET}")
                else:
                    output_lines.append(f"{_AnsiColors.YELLOW}No matches found.{_AnsiColors.RESET}")
            elif match_type == "fullmatch":
                match = re.fullmatch(pattern, text)
                if match:
                    output_lines.append(f"Full match found: '{_AnsiColors.GREEN}{match.group(0)}{_AnsiColors.RESET}'")
                else:
                    output_lines.append(f"{_AnsiColors.YELLOW}No full match.{_AnsiColors.RESET}")
            else: # default to search
                match = re.search(pattern, text)
                if match:
                    output_lines.append(f"First match found: '{_AnsiColors.GREEN}{match.group(0)}{_AnsiColors.RESET}' at index {_AnsiColors.MAGENTA}{match.start()}{_AnsiColors.RESET} to {_AnsiColors.MAGENTA}{match.end()-1}{_AnsiColors.RESET}")
                else:
                    output_lines.append(f"{_AnsiColors.YELLOW}No match found.{_AnsiColors.RESET}")
        except re.error as e:
            output_lines.append(f"{_AnsiColors.RED}Regex Error: {e}{_AnsiColors.RESET}")

    elif task == "get_current_datetime":
        fmt = kwargs.get("format", "%Y-%m-%d %H:%M:%S")
        try:
            output_lines.append(datetime.datetime.now().strftime(fmt))
        except ValueError as e:
            output_lines.append(f"{_AnsiColors.RED}Error in date format: {e}. Defaulting to '%Y-%m-%d %H:%M:%S'.{_AnsiColors.RESET}")
            output_lines.append(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    elif task == "get_system_info":
        output_lines.append(f"{_AnsiColors.BOLD}--- System Information ---{_AnsiColors.RESET}")
        output_lines.append(f"  {_AnsiColors.BLUE}OS:{_AnsiColors.RESET} {platform.system()} {platform.release()} ({platform.version()})")
        output_lines.append(f"  {_AnsiColors.BLUE}Hostname:{_AnsiColors.RESET} {platform.node()}")
        output_lines.append(f"  {_AnsiColors.BLUE}Architecture:{_AnsiColors.RESET} {platform.machine()}")
        output_lines.append(f"  {_AnsiColors.BLUE}Processor:{_AnsiColors.RESET} {platform.processor()}")
        output_lines.append(f"  {_AnsiColors.BLUE}Python Version:{_AnsiColors.RESET} {sys.version.splitlines()[0]}")
        output_lines.append(f"  {_AnsiColors.BLUE}CPU Count:{_AnsiColors.RESET} {os.cpu_count()}")
        output_lines.append(f"  {_AnsiColors.BLUE}Current Working Directory:{_AnsiColors.RESET} {os.getcwd()}")
        user = os.getenv('USER') or os.getenv('USERNAME')
        if user:
            output_lines.append(f"  {_AnsiColors.BLUE}Current User:{_AnsiColors.RESET} {user}")
        output_lines.append(f"{_AnsiColors.BOLD}--------------------------{_AnsiColors.RESET}")

    elif task == "parse_json":
        json_string = kwargs.get("json_string")
        if not isinstance(json_string, str):
            return f"{_AnsiColors.RED}Error: 'json_string' argument is required and must be a string for 'parse_json'.{_AnsiColors.RESET}"
        try:
            parsed_data = json.loads(json_string)
            output_lines.append(json.dumps(parsed_data, indent=2))
        except json.JSONDecodeError as e:
            output_lines.append(f"{_AnsiColors.RED}JSON Parsing Error: {e}{_AnsiColors.RESET}")
            output_lines.append(f"{_AnsiColors.YELLOW}Invalid JSON string provided (first 100 chars): '{json_string[:100]}...'{_AnsiColors.RESET}")

    elif task == "pretty_print_json":
        data = kwargs.get("data")
        if not isinstance(data, (dict, list)):
            return f"{_AnsiColors.RED}Error: 'data' argument is required and must be a dict or list for 'pretty_print_json'.{_AnsiColors.RESET}"
        try:
            output_lines.append(json.dumps(data, indent=2))
        except TypeError as e:
            output_lines.append(f"{_AnsiColors.RED}JSON Serialization Error: {e}{_AnsiColors.RESET}")

    else:
        output_lines.append(f"{_AnsiColors.RED}Error: Unknown task '{task}'.{_AnsiColors.RESET}")
        output_lines.append(f"{_AnsiColors.YELLOW}Supported tasks are: 'format_text', 'log_message', 'regex_search', 'get_current_datetime', 'get_system_info', 'parse_json', 'pretty_print_json'.{_AnsiColors.RESET}")

    return "\n".join(output_lines)