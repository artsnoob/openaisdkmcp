#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema, } from "@modelcontextprotocol/sdk/types.js";
import { randomBytes } from 'crypto';
import { join } from 'path';
import { mkdir, writeFile } from 'fs/promises';
import { exec } from 'child_process';
import { promisify } from 'util';
import { platform } from 'os';
// Environment variables
const CODE_STORAGE_DIR = process.env.CODE_STORAGE_DIR || '';
// Default environment settings
let ENV_CONFIG = {
    // Default environment (conda, venv, or venv-uv)
    type: (process.env.ENV_TYPE || 'conda'),
    // Name of the conda environment
    conda_name: process.env.CONDA_ENV_NAME,
    // Path to virtualenv
    venv_path: process.env.VENV_PATH,
    // Path to uv virtualenv
    uv_venv_path: process.env.UV_VENV_PATH
};
if (!CODE_STORAGE_DIR) {
    throw new Error('Missing required environment variable: CODE_STORAGE_DIR');
}
// Validate environment settings based on the selected type
if (ENV_CONFIG.type === 'conda' && !ENV_CONFIG.conda_name) {
    throw new Error('Missing required environment variable: CONDA_ENV_NAME (required for conda environment)');
}
else if (ENV_CONFIG.type === 'venv' && !ENV_CONFIG.venv_path) {
    throw new Error('Missing required environment variable: VENV_PATH (required for virtualenv)');
}
else if (ENV_CONFIG.type === 'venv-uv' && !ENV_CONFIG.uv_venv_path) {
    throw new Error('Missing required environment variable: UV_VENV_PATH (required for uv virtualenv)');
}
// Ensure storage directory exists
await mkdir(CODE_STORAGE_DIR, { recursive: true });
const execAsync = promisify(exec);
/**
 * Get platform-specific command for environment activation and execution
 */
function getPlatformSpecificCommand(pythonCommand) {
    const isWindows = platform() === 'win32';
    let command = '';
    let options = {};
    switch (ENV_CONFIG.type) {
        case 'conda':
            if (!ENV_CONFIG.conda_name) {
                throw new Error("conda_name is required for conda environment");
            }
            if (isWindows) {
                command = `conda run -n ${ENV_CONFIG.conda_name} ${pythonCommand}`;
                options = { shell: 'cmd.exe' };
            }
            else {
                command = `source $(conda info --base)/etc/profile.d/conda.sh && conda activate ${ENV_CONFIG.conda_name} && ${pythonCommand}`;
                options = { shell: '/bin/bash' };
            }
            break;
        case 'venv':
            if (!ENV_CONFIG.venv_path) {
                throw new Error("venv_path is required for virtualenv");
            }
            if (isWindows) {
                command = `${join(ENV_CONFIG.venv_path, 'Scripts', 'activate')} && ${pythonCommand}`;
                options = { shell: 'cmd.exe' };
            }
            else {
                command = `source ${join(ENV_CONFIG.venv_path, 'bin', 'activate')} && ${pythonCommand}`;
                options = { shell: '/bin/bash' };
            }
            break;
        case 'venv-uv':
            if (!ENV_CONFIG.uv_venv_path) {
                throw new Error("uv_venv_path is required for uv virtualenv");
            }
            if (isWindows) {
                command = `${join(ENV_CONFIG.uv_venv_path, 'Scripts', 'activate')} && ${pythonCommand}`;
                options = { shell: 'cmd.exe' };
            }
            else {
                command = `source ${join(ENV_CONFIG.uv_venv_path, 'bin', 'activate')} && ${pythonCommand}`;
                options = { shell: '/bin/bash' };
            }
            break;
        default:
            throw new Error(`Unsupported environment type: ${ENV_CONFIG.type}`);
    }
    return { command, options };
}
/**
 * Execute Python code and return the result
 */
async function executeCode(code, filePath) {
    try {
        // Write code to file
        await writeFile(filePath, code, 'utf-8');
        // Get platform-specific command
        const pythonCmd = platform() === 'win32' ? `python "${filePath}"` : `python3 "${filePath}"`;
        const { command, options } = getPlatformSpecificCommand(pythonCmd);
        // Execute code
        const { stdout, stderr } = await execAsync(command, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env },
            ...options
        });
        const response = {
            status: stderr ? 'error' : 'success',
            output: stderr || stdout,
            file_path: filePath
        };
        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: !!stderr
        };
    }
    catch (error) {
        const response = {
            status: 'error',
            error: error instanceof Error ? error.message : String(error),
            file_path: filePath
        };
        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}
/**
 * Install dependencies using the appropriate package manager
 */
async function installDependencies(packages) {
    try {
        if (!packages || packages.length === 0) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: 'No packages specified'
                }),
                isError: true
            };
        }
        // Build the install command based on environment type
        let installCmd = '';
        const packageList = packages.join(' ');
        switch (ENV_CONFIG.type) {
            case 'conda':
                if (!ENV_CONFIG.conda_name) {
                    throw new Error("conda_name is required for conda environment");
                }
                installCmd = `conda install -y -n ${ENV_CONFIG.conda_name} ${packageList}`;
                break;
            case 'venv':
                installCmd = `pip install ${packageList}`;
                break;
            case 'venv-uv':
                installCmd = `uv pip install ${packageList}`;
                break;
            default:
                throw new Error(`Unsupported environment type: ${ENV_CONFIG.type}`);
        }
        // Get platform-specific command
        const { command, options } = getPlatformSpecificCommand(installCmd);
        // Execute installation
        const { stdout, stderr } = await execAsync(command, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env },
            ...options
        });
        const response = {
            status: 'success',
            env_type: ENV_CONFIG.type,
            installed_packages: packages,
            output: stdout,
            warnings: stderr || undefined
        };
        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: false
        };
    }
    catch (error) {
        const response = {
            status: 'error',
            env_type: ENV_CONFIG.type,
            error: error instanceof Error ? error.message : String(error)
        };
        return {
            type: 'text',
            text: JSON.stringify(response),
            isError: true
        };
    }
}
/**
 * Check if packages are installed in the current environment
 */
async function checkPackageInstallation(packages) {
    try {
        if (!packages || packages.length === 0) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: 'No packages specified'
                }),
                isError: true
            };
        }
        // Create a temporary Python script to check packages
        const tempId = randomBytes(4).toString('hex');
        // CODE_STORAGE_DIR is validated at the start of the program, so it's safe to use here
        const checkScriptPath = join(CODE_STORAGE_DIR, `check_packages_${tempId}.py`);
        // This script will attempt to import each package and return the results
        const checkScript = `
import importlib.util
import json
import sys

results = {}

for package in ${JSON.stringify(packages)}:
    try:
        # Try to find the spec
        spec = importlib.util.find_spec(package)
        if spec is None:
            # Package not found
            results[package] = {
                "installed": False,
                "error": "Package not found"
            }
            continue
            
        # Try to import the package
        module = importlib.import_module(package)
        
        # Get version if available
        version = getattr(module, "__version__", None)
        if version is None:
            version = getattr(module, "version", None)
            
        results[package] = {
            "installed": True,
            "version": version,
            "location": getattr(module, "__file__", None)
        }
    except ImportError as e:
        results[package] = {
            "installed": False,
            "error": str(e)
        }
    except Exception as e:
        results[package] = {
            "installed": False,
            "error": f"Unexpected error: {str(e)}"
        }

print(json.dumps(results))
`;
        await writeFile(checkScriptPath, checkScript, 'utf-8');
        // Execute the check script
        const pythonCmd = platform() === 'win32' ? `python "${checkScriptPath}"` : `python3 "${checkScriptPath}"`;
        const { command, options } = getPlatformSpecificCommand(pythonCmd);
        const { stdout, stderr } = await execAsync(command, {
            cwd: CODE_STORAGE_DIR,
            env: { ...process.env },
            ...options
        });
        if (stderr) {
            return {
                type: 'text',
                text: JSON.stringify({
                    status: 'error',
                    error: stderr
                }),
                isError: true
            };
        }
        // Parse the package information
        const packageInfo = JSON.parse(stdout.trim());
        // Add summary information to make it easier to use
        const allInstalled = Object.values(packageInfo).every((info) => info.installed);
        const notInstalled = Object.entries(packageInfo)
            .filter(([_, info]) => !info.installed)
            .map(([name, _]) => name);
        return {
            type: 'text',
            text: JSON.stringify({
                status: 'success',
                env_type: ENV_CONFIG.type,
                all_installed: allInstalled,
                not_installed: notInstalled,
                package_details: packageInfo
            }),
            isError: false
        };
    }
    catch (error) {
        return {
            type: 'text',
            text: JSON.stringify({
                status: 'error',
                env_type: ENV_CONFIG.type,
                error: error instanceof Error ? error.message : String(error)
            }),
            isError: true
        };
    }
}
/**
 * Create an MCP server to handle code execution and dependency management
 */
const server = new Server({
    name: "code-executor",
    version: "0.2.0",
}, {
    capabilities: {
        tools: {},
    },
});
/**
 * Handler for listing available tools.
 */
server.setRequestHandler(ListToolsRequestSchema, async () => {
    return {
        tools: [
            {
                name: "execute_code",
                description: `Execute Python code in the ${ENV_CONFIG.type} environment`,
                inputSchema: {
                    type: "object",
                    properties: {
                        code: {
                            type: "string",
                            description: "Python code to execute"
                        },
                        filename: {
                            type: "string",
                            description: "Optional: Name of the file to save the code (default: generated UUID)"
                        }
                    },
                    required: ["code"]
                }
            },
            {
                name: "install_dependencies",
                description: `Install Python dependencies in the ${ENV_CONFIG.type} environment`,
                inputSchema: {
                    type: "object",
                    properties: {
                        packages: {
                            type: "array",
                            items: {
                                type: "string"
                            },
                            description: "List of packages to install"
                        }
                    },
                    required: ["packages"]
                }
            },
            {
                name: "check_installed_packages",
                description: `Check if packages are installed in the ${ENV_CONFIG.type} environment`,
                inputSchema: {
                    type: "object",
                    properties: {
                        packages: {
                            type: "array",
                            items: {
                                type: "string"
                            },
                            description: "List of packages to check"
                        }
                    },
                    required: ["packages"]
                }
            },
            {
                name: "configure_environment",
                description: "Change the environment configuration settings",
                inputSchema: {
                    type: "object",
                    properties: {
                        type: {
                            type: "string",
                            enum: ["conda", "venv", "venv-uv"],
                            description: "Type of Python environment"
                        },
                        conda_name: {
                            type: "string",
                            description: "Name of the conda environment (required if type is 'conda')"
                        },
                        venv_path: {
                            type: "string",
                            description: "Path to the virtualenv (required if type is 'venv')"
                        },
                        uv_venv_path: {
                            type: "string",
                            description: "Path to the UV virtualenv (required if type is 'venv-uv')"
                        }
                    },
                    required: ["type"]
                }
            },
            {
                name: "get_environment_config",
                description: "Get the current environment configuration",
                inputSchema: {
                    type: "object",
                    properties: {}
                }
            }
        ]
    };
});
/**
 * Validate the environment configuration
 */
function validateEnvironmentConfig(config) {
    if (config.type === 'conda' && !config.conda_name) {
        return "conda_name is required when type is 'conda'";
    }
    else if (config.type === 'venv' && !config.venv_path) {
        return "venv_path is required when type is 'venv'";
    }
    else if (config.type === 'venv-uv' && !config.uv_venv_path) {
        return "uv_venv_path is required when type is 'venv-uv'";
    }
    return null;
}
/**
 * Handler for tool execution.
 */
server.setRequestHandler(CallToolRequestSchema, async (request) => {
    switch (request.params.name) {
        case "execute_code": {
            const args = request.params.arguments;
            if (!args?.code) {
                throw new Error("Code is required");
            }
            // Generate a filename with both user-provided name and a random component for uniqueness
            let filename;
            if (args.filename && typeof args.filename === 'string') {
                // Extract base name without extension
                const baseName = args.filename.replace(/\.py$/, '');
                // Add a random suffix to ensure uniqueness
                filename = `${baseName}_${randomBytes(4).toString('hex')}.py`;
            }
            else {
                // Default filename if none provided
                filename = `code_${randomBytes(4).toString('hex')}.py`;
            }
            const filePath = join(CODE_STORAGE_DIR, filename);
            // Execute the code and include the generated filename in the response
            const result = await executeCode(args.code, filePath);
            // Parse the result to add the filename info if it's a success response
            try {
                const resultData = JSON.parse(result.text);
                resultData.generated_filename = filename;
                result.text = JSON.stringify(resultData);
            }
            catch (e) {
                // In case of parsing error, continue with original result
                console.error("Error adding filename to result:", e);
            }
            return {
                content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
            };
        }
        case "install_dependencies": {
            const args = request.params.arguments;
            if (!args?.packages || !Array.isArray(args.packages)) {
                throw new Error("Valid packages array is required");
            }
            const result = await installDependencies(args.packages);
            return {
                content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
            };
        }
        case "check_installed_packages": {
            const args = request.params.arguments;
            if (!args?.packages || !Array.isArray(args.packages)) {
                throw new Error("Valid packages array is required");
            }
            const result = await checkPackageInstallation(args.packages);
            return {
                content: [{
                        type: "text",
                        text: result.text,
                        isError: result.isError
                    }]
            };
        }
        case "configure_environment": {
            // Safely access and validate arguments
            const rawArgs = request.params.arguments || {};
            // Check if type exists and is one of the allowed values
            if (!rawArgs || typeof rawArgs !== 'object' || !('type' in rawArgs) ||
                !['conda', 'venv', 'venv-uv'].includes(String(rawArgs.type))) {
                return {
                    content: [{
                            type: "text",
                            text: JSON.stringify({
                                status: 'error',
                                error: "Invalid arguments: 'type' is required and must be one of 'conda', 'venv', or 'venv-uv'"
                            }),
                            isError: true
                        }]
                };
            }
            // Now we can safely create a properly typed object
            const args = {
                type: String(rawArgs.type),
                conda_name: 'conda_name' in rawArgs ? String(rawArgs.conda_name) : undefined,
                venv_path: 'venv_path' in rawArgs ? String(rawArgs.venv_path) : undefined,
                uv_venv_path: 'uv_venv_path' in rawArgs ? String(rawArgs.uv_venv_path) : undefined,
            };
            // Validate configuration
            const validationError = validateEnvironmentConfig(args);
            if (validationError) {
                return {
                    content: [{
                            type: "text",
                            text: JSON.stringify({
                                status: 'error',
                                error: validationError
                            }),
                            isError: true
                        }]
                };
            }
            // Update configuration
            const previousConfig = { ...ENV_CONFIG };
            ENV_CONFIG = {
                ...ENV_CONFIG,
                type: args.type,
                ...(args.conda_name && { conda_name: args.conda_name }),
                ...(args.venv_path && { venv_path: args.venv_path }),
                ...(args.uv_venv_path && { uv_venv_path: args.uv_venv_path })
            };
            return {
                content: [{
                        type: "text",
                        text: JSON.stringify({
                            status: 'success',
                            message: 'Environment configuration updated',
                            previous: previousConfig,
                            current: ENV_CONFIG
                        }),
                        isError: false
                    }]
            };
        }
        case "get_environment_config": {
            return {
                content: [{
                        type: "text",
                        text: JSON.stringify({
                            status: 'success',
                            config: ENV_CONFIG
                        }),
                        isError: false
                    }]
            };
        }
        default:
            throw new Error("Unknown tool");
    }
});
/**
 * Start the server using stdio transport.
 */
async function main() {
    console.error(` Info: Starting MCP Server with ${ENV_CONFIG.type} environment`);
    console.error(`Info: Code storage directory: ${CODE_STORAGE_DIR}`);
    const transport = new StdioServerTransport();
    await server.connect(transport);
}
main().catch((error) => {
    console.error("Server error:", error);
    process.exit(1);
});
