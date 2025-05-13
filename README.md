# MCP Agent Interaction Project

## Overview

This project implements an interactive AI agent that leverages several Model Context Protocol (MCP) servers to perform a variety of tasks. Users can interact with the agent via a command-line interface, instructing it to fetch web content, perform web searches, execute Python code, and interact with the local filesystem.

The project is designed to be a testbed and demonstration of how an AI agent can be augmented with external tools through MCP servers.

## Features

*   **Interactive Chat Interface**: Allows users to communicate with the AI agent in a conversational manner.
*   **MCP Server Integration**: Connects to and utilizes multiple MCP servers for extended capabilities:
    *   **Code Execution**: Executes Python code in a sandboxed environment.
    *   **Filesystem Operations**: Reads and writes files to a designated local directory.
    *   **Web Content Fetching**: Retrieves content from URLs.
    *   **Web Search**: Performs web searches using the Brave Search API.
*   **Robust Agent Instructions**: The agent is configured with detailed guidelines for generating Python code, emphasizing error handling and safe data access.
*   **Environment Setup**: Automatically creates necessary directories and a Python virtual environment.
*   **Dependency Management**: Installs basic Python packages into the virtual environment if it's newly created.
*   **Clear Logging**: Provides colored console output for system messages, agent responses, tool usage, and code execution results.

## Prerequisites

Before running the project, ensure you have the following installed:

*   **Python 3.x**
*   **Node.js and npm**: Required for `npx`, which is used to run some MCP servers (Filesystem, Brave Search). Download from [https://nodejs.org/](https://nodejs.org/).
*   **uv**: Required for `uvx`, which is used to run the Fetch MCP server. Installation instructions can be found at [https://github.com/astral-sh/uv](https://github.com/astral-sh/uv).
*   **Brave Search API Key**: If you intend to use the web search functionality, you'll need an API key from Brave Search.

## Setup

1.  **Environment Variables**:
    Create a file named `.env` in the project's root directory and add your Brave Search API key:
    ```env
    BRAVE_API_KEY=your_brave_api_key_here
    ```

2.  **Python Dependencies**:
    Install the required Python packages using the `requirements.txt` file:
    ```bash
    pip3 install -r requirements.txt
    ```
    This will install `openai-agents` (the OpenAI Agents SDK) and `python-dotenv`.
    The `openai-agents` SDK is used for defining the agent, its interactions, and managing the communication with MCP servers.
    The script also attempts to install `feedparser`, `requests`, and `beautifulsoup4` into its local venv if needed for specific agent tasks.

## Core Libraries Used

*   **OpenAI Agents SDK (`openai-agents`)**: This SDK provides the core framework for creating and running the AI agent. It handles the agent's lifecycle, tool integration (MCP servers), and the processing of user interactions. Key components used from this SDK include `Agent` for defining the agent and `Runner` for executing the interactive session.
*   **Python-dotenv**: Used to load environment variables (like API keys) from a `.env` file.

## Running the Project

To start the interactive agent session, run the `agent.py` script:

```bash
python3 agent.py
```

This will:
1.  Set up necessary directories (e.g., `sample_mcp_files` and a `venv` within it).
2.  Configure and test connections to the MCP servers.
3.  Initialize the AI agent.
4.  Start an interactive command-line session where you can chat with the agent.

Type `quit` or `exit` to end the session.

## Project Structure

*   `agent.py`: The main executable script that initializes and runs the agent and interactive session.
*   `mcp_agent_setup.py`: Defines the AI agent's configuration, including its instructions and personality.
*   `mcp_server_config.py`: Configures the MCP servers (Code Executor, Filesystem, Fetch, Brave Search) and tests their connections.
*   `mcp_utils.py`: (Not read, but assumed to contain utility functions like colored logging and venv setup based on imports).
*   `.env`: Stores environment variables like API keys (you need to create this).
*   `mcp_code_executor/`: Contains the source code and build for the Node.js-based MCP Code Executor server.
*   `sample_mcp_files/`: Directory used by the Filesystem MCP server and for storing generated code and its virtual environment. This directory is created automatically if it doesn't exist.

## MCP Servers Used

The project utilizes the following MCP servers:

*   **MCP Code Executor**:
    *   **Implementation**: Node.js application (located in `mcp_code_executor/`).
    *   **Purpose**: Executes Python code snippets provided by the agent. Manages a Python virtual environment for code execution.
*   **Filesystem Server**:
    *   **Implementation**: Run via `npx @modelcontextprotocol/server-filesystem`.
    *   **Purpose**: Allows the agent to read from and write to files within the `sample_mcp_files/` directory.
*   **Fetch Server**:
    *   **Implementation**: Run via `uvx mcp-server-fetch`.
    *   **Purpose**: Enables the agent to fetch content from web URLs.
*   **Brave Search Server**:
    *   **Implementation**: Run via `npx @modelcontextprotocol/server-brave-search`.
    *   **Purpose**: Allows the agent to perform web searches using the Brave Search API.

## Agent Capabilities

The AI agent is designed to:

*   Understand and respond to user queries in a conversational manner.
*   Generate and execute Python code to solve problems or perform tasks.
*   Adhere to specific guidelines for writing robust Python code, including error handling and safe data access (especially for RSS feeds).
*   Interact with the local filesystem (read/write files in `sample_mcp_files/`).
*   Fetch information from websites.
*   Perform web searches to find current information or answer questions.
