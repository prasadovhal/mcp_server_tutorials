# mcp_server_tutorials
How to create API and MCP servers tutorials from basic to advance

## System Monitor MCP Server

This MCP server provides comprehensive system monitoring capabilities without external dependencies like psutil or gputil. It works on Linux, Windows, and macOS.

### Features
- **CPU Usage**: Usage percentage, core count, frequency, load averages
- **Memory Usage**: RAM and swap usage with detailed breakdown
- **Storage Info**: All mounted partitions with usage statistics
- **Network Info**: Interfaces, IP addresses, traffic statistics, hostname, public IP
- **Network Connections**: Active TCP connections with states
- **GPU Usage**: Utilization, memory, temperature, power (NVIDIA, AMD, Intel, Apple)
- **GPU Info**: Hardware details, driver versions, PCIe info
- **System Info**: OS details, Python version, boot time, uptime
- **CPU Temperature**: Hardware temperature sensors
- **Top Processes**: Memory-sorted process list
- **Battery Info**: Charge level and status (laptops)
- **Logged-in Users**: Current user sessions
- **Open Files**: System-wide file descriptor count
- **Kernel Info**: Kernel version, architecture, CPU flags
- **Disk I/O Stats**: Read/write operations and bytes transferred per device

## Set up Python & Poetry

1. cd mcp_server_tutorials
2. install poetry
`(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -`
3. run `C:\Users\user_name\AppData\Roaming\Python\Scripts`
4. check poetry version `poetry --version`
5. set `poetry config virtualenvs.in-project true`
6. run `poetry install`
7. set venv 
   - for windows `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned` or `.venv\Scripts\activate`
   - for linux/mac `source .venv/bin/activate`

## Running the MCP Server in VS Code

### Prerequisites
1. VS Code with GitHub Copilot Chat extension installed
2. The MCP server dependencies installed (see setup above)

### Configuration Steps

1. **Open VS Code Settings** (Ctrl/Cmd + ,)
2. **Search for "mcp"** in settings
3. **Add MCP Server Configuration**:
   - Look for "GitHub Copilot Chat: Mcp" settings
   - Add a new server configuration

### Example MCP Configuration (JSON)

Add this to your VS Code MCP settings:

```json
{
  "mcpServers": {
    "system-monitor": {
      "command": "poetry",
      "args": ["run", "python", "MCP_servers/server.py"],
      "cwd": "/path/to/your/mcp_server_tutorials",
      "env": {}
    }
  }
}
```

Replace `/path/to/your/mcp_server_tutorials` with the actual path to your project directory.

### Alternative: Using .vscode/settings.json

Create or edit `.vscode/settings.json` in your workspace:

```json
{
  "github.copilot.chat.mcp": {
    "system-monitor": {
      "command": "poetry",
      "args": ["run", "python", "MCP_servers/server.py"],
      "cwd": "${workspaceFolder}",
      "env": {}
    }
  }
}
```

### Testing the Server

1. After configuration, restart VS Code or reload the Copilot Chat extension
2. Open Copilot Chat (Ctrl/Cmd + Shift + I)
3. You should see the system monitor tools available
4. Try asking: "What's my CPU usage?" or "Show me memory stats"

### Manual Testing

You can also test the server manually:

```bash
cd /path/to/mcp_server_tutorials
poetry run python MCP_servers/server.py
```

The server will start and wait for MCP protocol messages via stdin/stdout.

## API vs MCP server

| Feature          | Traditional API                                | MCP Server                                        |
| ---------------- | ---------------------------------------------- | ------------------------------------------------- |
| Primary Audience | Human developers writing code                  | AI models / LLM agents                            |
| Integration      | Requires custom code for every single service  | "Build once| works with any MCP-compatible AI"    |
| Discovery        | Manual (reading docs)                          | Automatic (runtime capability negotiation)        |
| Structure        | "Endpoints (REST, GraphQL, SOAP)"              | "Tools| Resources| and Prompts"                   |
| Adaptability     | Rigid; breaks if the endpoint changes          | Flexible; AI adapts to available tools on the fly |