# MCP Agent Server

## Description

This project appears to be a server and client implementation for the Model Context Protocol (MCP), designed to facilitate interactions with AI agents. It includes components for a command-line interface (CLI), a web-based interface, and a dedicated module for code execution.

## Features

*   **Command-Line Interface (CLI):** Allows interaction with MCP agents via `agentcli.py`.
*   **Web Interface:** Provides a web-based UI for interacting with MCP agents, served by `agentweb.py` and located in the `frontend/` directory.
*   **MCP Code Executor:** A Node.js module (`mcp_code_executor/`) likely responsible for executing code snippets or commands as directed by agents.
*   **Local MCP Modules:** Python modules (`mcp_local_modules/`) for handling MCP setup, configuration, and utility functions.
*   **Documentation:** Contains project-related documentation in the `docs/` directory.
*   **Sample MCP Files:** Includes example files related to MCP in `sample_mcp_files/`.

## Project Structure

A brief overview of the key directories and files:

*   `agentcli.py`: Main script for the command-line interface.
*   `agentweb.py`: Main script for the web server.
*   `frontend/`: Contains the HTML, CSS, and JavaScript for the web interface.
*   `mcp_code_executor/`: A Node.js module for code execution.
    *   `src/index.ts`: TypeScript source for the code executor.
    *   `build/index.js`: Compiled JavaScript for the code executor.
*   `mcp_local_modules/`: Python modules for MCP core functionalities.
    *   `mcp_agent_setup.py`: Handles agent setup.
    *   `mcp_server_config.py`: Manages server configuration.
*   `cli/`: Python modules supporting the command-line interface.
*   `docs/`: Project documentation files.
*   `requirements.txt`: Python project dependencies.
*   `.gitignore`: Specifies intentionally untracked files that Git should ignore.
*   `file_organization_log.md`: Log related to file organization.
*   `minimal_ollama_test.py`: Test script for Ollama.
*   `ollama_chat.py`: Script for Ollama chat functionality.

## Getting Started

To get started with this project, you would typically need to:

1.  **Install Dependencies:**
    *   For Python components: `pip install -r requirements.txt`
    *   For the MCP Code Executor: Navigate to `mcp_code_executor/` and run `npm install`
2.  **Configure the Environment:** (Details would depend on specific MCP server configurations needed)
3.  **Run the Application:**
    *   CLI: `python agentcli.py` (or similar, depending on arguments)
    *   Web Interface: `python agentweb.py` (and then access the specified port in a browser)

*(Please update with more specific instructions as the project develops.)*

## Contributing

Contributions are welcome! Please refer to contribution guidelines if available, or open an issue/pull request.

## License

(Please specify the license under which this project is distributed.)
