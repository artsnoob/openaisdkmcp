graph TD
    UserQuestion[User Question via CLI] --> CLI_Input["agentcli.py: Receives Input in Main Loop"];
    CLI_Input --> CLI_History["agentcli.py: Adds to Conversation History &lpar;msgs&rpar;"];
    CLI_History --> CLI_CallRunner["agentcli.py: Calls Runner.run&lpar;agent, msgs&rpar;"];

    subgraph RunnerExecution ["Runner.run Orchestration Logic (Conceptual)"]
        direction TB
        Runner_Entry["Input: agent &lpar;LLM + tools config&rpar;, msgs"] --> LLM_InitialProcessing{"LLM (Agent) Processes 'msgs'"};
        
        LLM_InitialProcessing -- "Option 1: Direct Textual Response" --> LLM_GeneratesText[LLM Generates Textual Response];
        LLM_GeneratesText --> Runner_PackageResult[Runner Packages LLM Text into 'result' object];
        
        LLM_InitialProcessing -- "Option 2: Tool Call Requested" --> LLM_RequestsTool["LLM Responds with Tool Call Request&lpar;s&rpar;"];
        LLM_RequestsTool --> Runner_IdentifiesTool["Runner Parses Tool Call Request&lpar;s&rpar;"];
        
        Runner_IdentifiesTool -- "For each MCP Tool Call" --> Runner_CallsMCPServer[Runner Invokes Specific MCP Server Tool];
        Runner_CallsMCPServer --> MCPServer_Executes[MCP Server Executes Tool Logic];
        MCPServer_Executes -- "Raw Tool Output" --> Runner_ReceivesMCPOutput[Runner Receives MCP Server Output];
        Runner_ReceivesMCPOutput --> Runner_FormatsMCPOutput[Runner Formats MCP Output as Tool Result Message];
        Runner_FormatsMCPOutput --> LLM_ProcessesToolOutput{"LLM (Agent) Processes Formatted Tool Result&lpar;s&rpar;"};
        
        %% Placeholder for non-MCP tools, if any were defined for the agent
        Runner_IdentifiesTool -- "For each Non-MCP Tool Call (if any)" --> Runner_HandlesOtherTool[Runner Handles Other Internal Tool];
        Runner_HandlesOtherTool -- "Raw Tool Output" --> Runner_FormatsOtherOutput[Runner Formats Other Tool Output];
        Runner_FormatsOtherOutput --> LLM_ProcessesToolOutput;
        
        LLM_ProcessesToolOutput --> LLM_GeneratesResponseAfterTool["LLM Generates Final Response Based on Tool Output&lpar;s&rpar;"];
        LLM_GeneratesResponseAfterTool --> Runner_PackageResult;
        
        Runner_PackageResult --> Runner_Exit["Output: 'result' object &lpar;contains final_output, history, usage, etc.&rpar;"];
    end

    CLI_CallRunner --> CLI_ReceivesResult["agentcli.py: Receives 'result' from Runner.run"];
    CLI_ReceivesResult --> CLI_ExtractsOutput["agentcli.py: Extracts 'result.final_output'"];
    CLI_ExtractsOutput --> CLI_Display[CLI: Displays Final Output to User];

    %% Styling for better readability
    classDef userNode fill:#D6EAF8,stroke:#3498DB,stroke-width:2px,color:#000;
    classDef cliNode fill:#E8DAEF,stroke:#8E44AD,stroke-width:2px,color:#000;
    classDef runnerNode fill:#D5F5E3,stroke:#2ECC71,stroke-width:2px,color:#000;
    classDef llmNode fill:#FCF3CF,stroke:#F1C40F,stroke-width:2px,color:#000;
    classDef mcpNode fill:#FDEDEC,stroke:#E74C3C,stroke-width:2px,color:#000;

    class UserQuestion,CLI_Display userNode;
    class CLI_Input,CLI_History,CLI_CallRunner,CLI_ReceivesResult,CLI_ExtractsOutput cliNode;
    class Runner_Entry,Runner_IdentifiesTool,Runner_CallsMCPServer,Runner_ReceivesMCPOutput,Runner_FormatsMCPOutput,Runner_HandlesOtherTool,Runner_FormatsOtherOutput,Runner_PackageResult,Runner_Exit runnerNode;
    class LLM_InitialProcessing,LLM_GeneratesText,LLM_RequestsTool,LLM_ProcessesToolOutput,LLM_GeneratesResponseAfterTool llmNode;
    class MCPServer_Executes mcpNode;
```

**Explanation of the Flow:**

1.  **User Input**: The user types a question into the command-line interface (CLI).
2.  **`agentcli.py` Processing**:
    *   The main loop in `agentcli.py` receives this input.
    *   The input is added to the ongoing conversation history (`msgs`).
    *   `agentcli.py` then calls `Runner.run()`, passing the `agent` (which includes the LLM client and tool configurations) and the `msgs`.
3.  **`Runner.run` Orchestration** (This is a conceptual representation as the `Runner` class code is not provided but its role is standard in agent frameworks):
    *   The `Runner` sends the `msgs` to the configured **LLM (Agent)**.
    *   The LLM processes the input and decides on an action:
        *   **Option 1: Direct Response**: If the LLM can answer directly, it generates a textual response. This response is packaged by the `Runner`.
        *   **Option 2: Tool Call**: If the LLM decides to use a tool (e.g., to fetch data, execute code, etc.), it generates a "tool call request".
            *   The `Runner` parses this request.
            *   If it's an **MCP Tool**: The `Runner` identifies the specific MCP server and tool, then invokes it. The **MCP Server** executes its logic and returns an output. The `Runner` receives this output and formats it as a "tool result message".
            *   (If other non-MCP tools were defined, the `Runner` would handle them similarly).
            *   The formatted tool result(s) are then sent back to the **LLM (Agent)**.
            *   The LLM processes the tool output(s) and generates a final response. This response is then packaged by the `Runner`.
    *   The `Runner.run()` function returns a `result` object, which typically contains the LLM's final output, the updated conversation history, token usage, and any raw responses from the LLM or tools.
4.  **`agentcli.py` Output Handling**:
    *   `agentcli.py` receives the `result` object back from `Runner.run()`.
    *   It extracts the `final_output` from the `result`.
    *   This `final_output` is then displayed to the user in the CLI.
