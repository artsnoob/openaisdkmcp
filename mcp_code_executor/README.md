# MCP Code Executor
[![smithery badge](https://smithery.ai/badge/@bazinga012/mcp_code_executor)](https://smithery.ai/server/@bazinga012/mcp_code_executor)

The MCP Code Executor is an MCP server that allows LLMs to execute Python code within a specified Python environment. This enables LLMs to run code with access to libraries and dependencies defined in the environment.

<a href="https://glama.ai/mcp/servers/45ix8xode3"><img width="380" height="200" src="https://glama.ai/mcp/servers/45ix8xode3/badge" alt="Code Executor MCP server" /></a>

## Features

- Execute Python code from LLM prompts
- Run code within a specified environment (Conda, virtualenv, or UV virtualenv)
- Install dependencies when needed
- Check if packages are already installed
- Dynamically configure the environment at runtime
- Configurable code storage directory

## Prerequisites

- Node.js installed
- One of the following:
  - Conda installed with desired Conda environment created
  - Python virtualenv
  - UV virtualenv

## Setup

1. Clone this repository:

```bash
git clone https://github.com/bazinga012/mcp_code_executor.git
```

2. Navigate to the project directory:

```bash 
cd mcp_code_executor
```

3. Install the Node.js dependencies:

```bash
npm install
```

4. Build the project:

```bash
npm run build
```

## Configuration

To configure the MCP Code Executor server, add the following to your MCP servers configuration file:

### Using Node.js

```json
{
  "mcpServers": {
    "mcp-code-executor": {
      "command": "node",
      "args": [
        "/path/to/mcp_code_executor/build/index.js" 
      ],
      "env": {
        "CODE_STORAGE_DIR": "/path/to/code/storage",
        "ENV_TYPE": "conda",
        "CONDA_ENV_NAME": "your-conda-env"
      }
    }
  }
}
```

### Using Docker

```json
{
  "mcpServers": {
    "mcp-code-executor": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "mcp-code-executor"
      ]
    }
  }
}
```

> **Note:** The Dockerfile has been tested with the venv-uv environment type only. Other environment types may require additional configuration.

### Environment Variables

#### Required Variables
- `CODE_STORAGE_DIR`: Directory where the generated code will be stored

#### Environment Type (choose one setup)
- **For Conda:**
  - `ENV_TYPE`: Set to `conda`
  - `CONDA_ENV_NAME`: Name of the Conda environment to use

- **For Standard Virtualenv:**
  - `ENV_TYPE`: Set to `venv`
  - `VENV_PATH`: Path to the virtualenv directory

- **For UV Virtualenv:**
  - `ENV_TYPE`: Set to `venv-uv`
  - `UV_VENV_PATH`: Path to the UV virtualenv directory

## Available Tools

The MCP Code Executor provides the following tools to LLMs:

### 1. `execute_code`
Executes Python code in the configured environment.
```json
{
  "name": "execute_code",
  "arguments": {
    "code": "import numpy as np\nprint(np.random.rand(3,3))",
    "filename": "matrix_gen"
  }
}
```

### 2. `install_dependencies`
Installs Python packages in the environment.
```json
{
  "name": "install_dependencies",
  "arguments": {
    "packages": ["numpy", "pandas", "matplotlib"]
  }
}
```

### 3. `check_installed_packages`
Checks if packages are already installed in the environment.
```json
{
  "name": "check_installed_packages",
  "arguments": {
    "packages": ["numpy", "pandas", "non_existent_package"]
  }
}
```

### 4. `configure_environment`
Dynamically changes the environment configuration.
```json
{
  "name": "configure_environment",
  "arguments": {
    "type": "conda",
    "conda_name": "new_env_name"
  }
}
```

### 5. `get_environment_config`
Gets the current environment configuration.
```json
{
  "name": "get_environment_config",
  "arguments": {}
}
```

## Usage

Once configured, the MCP Code Executor will allow LLMs to execute Python code by generating a file in the specified `CODE_STORAGE_DIR` and running it within the configured environment.

LLMs can generate and execute code by referencing this MCP server in their prompts.

## Backward Compatibility

This package maintains backward compatibility with earlier versions. Users of previous versions who only specified a Conda environment will continue to work without any changes to their configuration.

## Contributing

Contributions are welcome! Please open an issue or submit a pull request.

## License

This project is licensed under the MIT License.
