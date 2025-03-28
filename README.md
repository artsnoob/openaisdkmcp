# OpenAI Agents SDK with MCP Filesystem, Fetch, and Brave Search Example

This project demonstrates how to use the OpenAI Agents SDK with multiple Model Context Protocol (MCP) servers. Specifically, it uses:
1.  The official [filesystem MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem) run locally via `npx` to allow an agent to interact with local files.
2.  The [fetch MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/fetch) run locally via `uvx` to allow an agent to fetch content from web URLs.
3.  The official [Brave Search MCP server](https://github.com/modelcontextprotocol/servers/tree/main/src/brave-search) run locally via `npx` to allow an agent to perform web searches using the Brave Search API.

The agent can leverage tools from all three servers to answer questions based on local files, web resources, or current information from the web.

## Prerequisites

Before you begin, ensure you have the following installed:

1.  **Python:** Version 3.9 or later.
2.  **Node.js and npm:** Required for using `npx` to run the MCP filesystem server. Download from [nodejs.org](https://nodejs.org/).
3.  **uv:** Required for using `uvx` to run the MCP fetch server. Install from [astral.sh/uv](https://astral.sh/uv).
4.  **OpenAI API Key:** The Agents SDK requires an OpenAI API key. Get one from [platform.openai.com](https://platform.openai.com/).
5.  **Brave Search API Key:** Required for the Brave Search MCP server. Get one from [api.search.brave.com](https://api.search.brave.com/).

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
    echo "Another test file." > sample_mcp_files/test.txt
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

6.  **Set Brave Search API Key:**
    Export your Brave Search API key as an environment variable.
    *   On macOS/Linux:
        ```bash
        export BRAVE_API_KEY='YourBraveApiKeyHere'
        ```
    *   On Windows (Command Prompt):
        ```bash
        set BRAVE_API_KEY=YourBraveApiKeyHere
        ```
    *   On Windows (PowerShell):
        ```bash
        $env:BRAVE_API_KEY = 'YourBraveApiKeyHere'
        ```
    Replace `YourBraveApiKeyHere` with your actual Brave Search API key.

## Running the Example

Make sure your virtual environment is activated and both the `OPENAI_API_KEY` and `BRAVE_API_KEY` environment variables are set.

Execute the Python script:

```bash
python mcp_test.py
```

The script will start the filesystem, fetch, and Brave Search MCP servers as subprocesses. You'll see output indicating the servers are connected, and then you can interact with the agent in your terminal. The script will also print the names of the MCP tools used by the agent before displaying the final answer.

## Example Interactions

**Using the Filesystem Server:**

```
MCP Servers (Filesystem, Fetch, Brave Search) connected. Starting interactive chat...
Type 'quit' or 'exit' to end the session.

You: What is in the file hello.txt?

[Tools Used: read_file]

Agent:
The file hello.txt contains the text "Hello from the MCP file!".
```

**Using the Fetch Server:**

```
You: Fetch the content of https://example.com

[Tools Used: fetch]

Agent:
Fetching content from https://example.com...
<!doctype html>
<html>
<head>
    <title>Example Domain</title>
    ... (rest of the HTML content) ...
</html>
```

**Using the Brave Search Server:**

```
You: What is the capital of France?

[Tools Used: brave_web_search]

Agent:
The capital of France is Paris.
```

Type `quit` or `exit` to stop the script and the MCP server subprocesses.
