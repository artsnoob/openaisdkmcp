# OpenAI Agents SDK with MCP Filesystem Example

This project demonstrates how to use the OpenAI Agents SDK with a Model Context Protocol (MCP) server. Specifically, it uses the official [filesystem MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) run locally via `npx` to allow an agent to interact with local files within a specified directory.

## Prerequisites

Before you begin, ensure you have the following installed:

1.  **Python:** Version 3.9 or later.
2.  **Node.js and npm:** Required for using `npx` to easily run the MCP filesystem server. You can download it from [nodejs.org](https://nodejs.org/).
3.  **OpenAI API Key:** The Agents SDK requires an OpenAI API key for initialization and potentially for default functionalities like tracing. Get one from [platform.openai.com](https://platform.openai.com/).

## Setup Instructions

1.  **Clone or Create Project:**
    If you have cloned a repository containing this `README.md` and `mcp_test.py`, navigate into that directory. Otherwise, create a new project directory:
    ```bash
    mkdir agent_mcp_test
    cd agent_mcp_test
    # Make sure mcp_test.py is in this directory
    ```

2.  **Create and Activate Virtual Environment:**
    *   On macOS/Linux:
        ```bash
        python3 -m venv .venv
        source .venv/bin/activate
        ```
    *   On Windows (Command Prompt):
        ```bash
        python -m venv .venv
        .\.venv\Scripts\activate
        ```
    *   On Windows (PowerShell):
        ```bash
        python -m venv .venv
        .\.venv\Scripts\Activate.ps1
        ```
    Your command prompt should now be prefixed with `(.venv)`.

3.  **Install Dependencies:**
    Install the OpenAI Agents SDK using pip:
    ```bash
    pip install openai-agents
    ```

4.  **Create Sample Directory and File:**
    The MCP filesystem server needs a directory to operate on.
    ```bash
    mkdir sample_mcp_files
    echo "Hello from the MCP file!" > sample_mcp_files/hello.txt
    ```
    *(The Python script assumes this directory is named `sample_mcp_files` and is located in the same directory as the script)*

5.  **Set OpenAI API Key:**
    Export your OpenAI API key as an environment variable.
    *   On macOS/Linux:
        ```bash
        export OPENAI_API_KEY='sk-YourSecretKeyHere'
        ```
    *   On Windows (Command Prompt):
        ```bash
        set OPENAI_API_KEY=sk-YourSecretKeyHere
        ```
    *   On Windows (PowerShell):
        ```bash
        $env:OPENAI_API_KEY = 'sk-YourSecretKeyHere'
        ```
    Replace `sk-YourSecretKeyHere` with your actual API key.

## Running the Example

Make sure your virtual environment is activated and the `OPENAI_API_KEY` environment variable is set.

Execute the Python script:

```bash
python mcp_test.py
