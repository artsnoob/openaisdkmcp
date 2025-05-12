# Setting Up the MCP Code Executor

This guide provides instructions for setting up the MCP Code Executor on a new device.

## Setting Up on a New Device

### 1. Clone the Repository

```powershell
git clone https://github.com/artsnoob/openaisdkmcp.git
cd openaisdkmcp/mcp_code_executor
```

### 2. Install Dependencies

```powershell
npm install
```

### 3. Build the Project

```powershell
npm run build
```

### 4. Set Up Environment Variables

The MCP Code Executor requires the following environment variables:

- `CODE_STORAGE_DIR`: Directory where the generated code will be stored
- One of the following environment setups:
  - For Conda:
    - `ENV_TYPE`: Set to `conda`
    - `CONDA_ENV_NAME`: Name of the Conda environment to use
  - For Standard Virtualenv:
    - `ENV_TYPE`: Set to `venv`
    - `VENV_PATH`: Path to the virtualenv directory
  - For UV Virtualenv:
    - `ENV_TYPE`: Set to `venv-uv`
    - `UV_VENV_PATH`: Path to the UV virtualenv directory

### 5. Configure in Cline MCP Settings

You need to add the MCP Code Executor to your Cline MCP settings file. The location of this file depends on your operating system:

- Windows: `%APPDATA%\Code\User\globalStorage\saoudrizwan.claude-dev\settings\cline_mcp_settings.json`
- macOS: `~/Library/Application Support/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`
- Linux: `~/.config/Code/User/globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json`

Add the following configuration to the `mcpServers` object in the settings file:

```json
"mcp-code-executor": {
  "command": "node",
  "args": [
    "C:\\path\\to\\mcp_code_executor\\build\\index.js"
  ],
  "env": {
    "CODE_STORAGE_DIR": "C:\\path\\to\\code\\storage",
    "ENV_TYPE": "venv",
    "VENV_PATH": "C:\\path\\to\\venv"
  },
  "disabled": false,
  "autoApprove": []
}
```

Replace the paths with the appropriate paths on your new device. Make sure to use double backslashes (`\\`) for Windows paths in the JSON file.

### 6. Set Up Python Environment

Depending on your chosen environment type:

#### For Conda:

```powershell
conda create -n your-conda-env python=3.10
conda activate your-conda-env
conda install numpy pandas matplotlib # Add any packages you need
```

#### For Standard Virtualenv:

```powershell
python -m venv C:\path\to\venv
C:\path\to\venv\Scripts\activate
pip install numpy pandas matplotlib # Add any packages you need
```

#### For UV Virtualenv:

First, install UV:

```powershell
curl -sSf https://astral.sh/uv/install.ps1 | powershell
```

Then create and activate the environment:

```powershell
uv venv C:\path\to\uv-venv
C:\path\to\uv-venv\Scripts\activate
uv pip install numpy pandas matplotlib # Add any packages you need
```

## Docker Alternative

If you prefer to use Docker, you can build and run the MCP Code Executor as a container:

```powershell
# Build the Docker image
docker build -t mcp-code-executor .

# Configure in Cline MCP settings
```

Then update your Cline MCP settings to use the Docker container:

```json
"mcp-code-executor": {
  "command": "docker",
  "args": [
    "run",
    "-i",
    "--rm",
    "mcp-code-executor"
  ],
  "disabled": false,
  "autoApprove": []
}
```

## Testing the Setup

You can test your setup using the included `mcp_test.py` file. Make sure to update the paths in the file to match your environment.
