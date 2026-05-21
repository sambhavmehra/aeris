"""
AERIS — MCP Installer Tool
═══════════════════════════════════════════════════════════════════════
Allows AERIS to dynamically install, connect, and verify MCP servers via chat.
Provides a list of known servers and supports arbitrary npx packages too.
═══════════════════════════════════════════════════════════════════════
"""
import json
import logging
import time
from typing import Dict, List, Optional

logger = logging.getLogger("AerisMCPInstaller")

from tools.mcp_bridge import get_mcp_registry, MCPServerConfig
from tools.tool_registry import global_tool_registry as reg, RiskLevel

# 1. KNOWN_SERVERS Registry
KNOWN_SERVERS = {
    "github": {
        "package": "@modelcontextprotocol/server-github",
        "transport": "stdio",
        "required_env": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
        "env_descriptions": {
            "GITHUB_PERSONAL_ACCESS_TOKEN": "GitHub Personal Access Token"
        },
        "default_args": [],
        "description": "Interact with GitHub repositories, issues, and pull requests."
    },
    "filesystem": {
        "package": "@modelcontextprotocol/server-filesystem",
        "transport": "stdio",
        "required_env": [],
        "env_descriptions": {},
        "default_args": ["/tmp"],
        "description": "Interact with local files and directories."
    },
    "slack": {
        "package": "@anthropic-ai/mcp-server-slack",
        "transport": "stdio",
        "required_env": ["SLACK_BOT_TOKEN", "SLACK_TEAM_ID"],
        "env_descriptions": {
            "SLACK_BOT_TOKEN": "Slack Bot User OAuth Token (xoxb-...)",
            "SLACK_TEAM_ID": "Slack Team/Workspace ID"
        },
        "default_args": [],
        "description": "Interact with Slack workspaces and channels."
    },
    "google-drive": {
        "package": "@anthropic-ai/mcp-server-google-drive",
        "transport": "stdio",
        "required_env": ["GOOGLE_DRIVE_CREDENTIALS"],
        "env_descriptions": {
            "GOOGLE_DRIVE_CREDENTIALS": "JSON-encoded Google Drive credentials"
        },
        "default_args": [],
        "description": "Interact with Google Drive files and folders."
    },
    "postgres": {
        "package": "@modelcontextprotocol/server-postgres",
        "transport": "stdio",
        "required_env": ["POSTGRES_CONNECTION_STRING"],
        "env_descriptions": {
            "POSTGRES_CONNECTION_STRING": "PostgreSQL database URL (postgresql://...)"
        },
        "default_args": [],
        "description": "Query and interact with a PostgreSQL database."
    },
    "sqlite": {
        "package": "@modelcontextprotocol/server-sqlite",
        "transport": "stdio",
        "required_env": [],
        "env_descriptions": {},
        "default_args": [],
        "description": "Query and interact with an SQLite database (db path required as argument)."
    },
    "brave-search": {
        "package": "@modelcontextprotocol/server-brave-search",
        "transport": "stdio",
        "required_env": ["BRAVE_API_KEY"],
        "env_descriptions": {
            "BRAVE_API_KEY": "Brave Search API Key"
        },
        "default_args": [],
        "description": "Search the web using Brave Search."
    },
    "memory": {
        "package": "@modelcontextprotocol/server-memory",
        "transport": "stdio",
        "required_env": [],
        "env_descriptions": {},
        "default_args": [],
        "description": "Graph database-based memory for AERIS."
    },
    "puppeteer": {
        "package": "@modelcontextprotocol/server-puppeteer",
        "transport": "stdio",
        "required_env": [],
        "env_descriptions": {},
        "default_args": [],
        "description": "Automate browser navigation and screenshotting."
    },
    "brevo": {
        "package": "@houtini/brevo-mcp",
        "transport": "stdio",
        "required_env": ["BREVO_API_KEY"],
        "env_descriptions": {
            "BREVO_API_KEY": "Brevo API Key (xkeysib-...)"
        },
        "default_args": [],
        "description": "Interact with Brevo CRM, send emails, and manage contacts."
    }
}


def search_known_servers(query: str) -> dict:
    """Fuzzy matches user query against KNOWN_SERVERS and returns matched info."""
    logger.info(f"Searching known MCP servers for query: '{query}'")
    query = query.lower()
    matches = {}
    for name, info in KNOWN_SERVERS.items():
        if query in name or query in info["package"].lower() or query in info["description"].lower():
            matches[name] = info
    return {"query": query, "matches": matches}


def _verify_server_credentials(conn, server_name: str) -> Optional[str]:
    """
    Attempts to verify that the credentials for an MCP server are valid by executing a read-only tool.
    Returns None if verified successfully (or if no verification tool is available).
    Returns the error message string if verification fails.
    """
    tools = conn.get_tools()
    if not tools:
        return "No tools were discovered on this MCP server."
    
    # 1. Check known verification tools
    verification_configs = {
        "brevo": ("get_account_info", {}),
        "github": ("get_user", {}),
        "slack": ("list_channels", {}),
        "google-drive": ("list_files", {}),
        "postgres": ("list_tables", {}),
        "sqlite": ("list_tables", {}),
        "brave-search": ("brave_web_search", {"query": "test"}),
    }
    
    verify_tool = None
    verify_args = {}
    
    if server_name in verification_configs:
        t_name, t_args = verification_configs[server_name]
        # Check if the tool actually exists
        if any(t.name == t_name for t in tools):
            verify_tool = t_name
            verify_args = t_args
            
    # 2. If not found in known configs, find any read-only tool with no required arguments
    if not verify_tool:
        for t in tools:
            name_lower = t.name.lower()
            if any(prefix in name_lower for prefix in ["get_", "list_", "search_", "show_", "read_", "view_"]):
                schema = t.input_schema or {}
                required = schema.get("required", [])
                if not required:
                    verify_tool = t.name
                    verify_args = {}
                    break
                    
    # 3. If still no tool, try first tool with no required arguments
    if not verify_tool:
        for t in tools:
            schema = t.input_schema or {}
            required = schema.get("required", [])
            if not required:
                verify_tool = t.name
                verify_args = {}
                break

    # 4. If a verification tool is found, execute it
    if verify_tool:
        logger.info(f"Verifying MCP server '{server_name}' using tool '{verify_tool}' with args {verify_args}")
        try:
            res = conn.call_tool(verify_tool, verify_args)
            if not res.success:
                logger.warning(f"Verification call to '{verify_tool}' failed: {res.error}")
                return res.error or "Verification tool call failed."
            logger.info(f"Verification call to '{verify_tool}' succeeded.")
        except Exception as e:
            logger.warning(f"Verification call to '{verify_tool}' encountered exception: {e}")
            return str(e)
            
    return None


def install_mcp_server(server_name: str, env_vars: dict = None, extra_args: list = None) -> str:
    """
    Installs, connects, and verifies an MCP server.
    If the server is known and requires env vars but none are provided, returns a form request UI action.
    """
    logger.info(f"Requested installation of MCP server: '{server_name}'")
    server_info = KNOWN_SERVERS.get(server_name)
    
    if server_info:
        display_name = server_name.capitalize()
        # Check if environment variables are required but missing
        if server_info["required_env"] and (env_vars is None or not any(k in env_vars for k in server_info["required_env"])):
            logger.info(f"Required env vars missing for '{server_name}'. Returning form request.")
            return json.dumps({
                "__ui_action__": "request_form",
                "title": f"Connect {display_name}",
                "description": f"Enter the required credentials to connect {display_name} to AERIS.",
                "server_name": server_name,
                "fields": [
                    {
                        "name": env_var_name,
                        "label": env_description,
                        "type": "password",
                        "placeholder": f"Enter your {env_var_name}",
                        "required": True
                    }
                    for env_var_name, env_description in server_info["env_descriptions"].items()
                ],
                "submit_endpoint": "/api/mcp/connect"
            })
        
        # Build config from known template
        package = server_info["package"]
        transport = server_info["transport"]
        default_args = server_info["default_args"]
        env = env_vars or {}
    else:
        # Unknown server: treat server_name as npx package name
        logger.info(f"Server '{server_name}' is not in KNOWN_SERVERS. Treating as raw package name.")
        package = server_name
        transport = "stdio"
        default_args = []
        env = env_vars or {}

    # Create config object
    cmd = ["npx", "-y", package] + default_args + (extra_args or [])
    config = MCPServerConfig(
        name=server_name,
        transport=transport,
        command=cmd,
        env=env,
        enabled=True,
        auto_connect=True
    )

    registry = get_mcp_registry()
    
    # Pre-emptively remove any existing configuration to reset state cleanly
    registry.remove_server(server_name)
    
    # Attempt connection
    logger.info(f"Adding and connecting to MCP server '{server_name}' with command: {cmd}")
    success = registry.add_server(config)
    
    if success:
        conn = registry._servers.get(server_name)
        # Give a small buffer if needed, although connect() is synchronous
        if conn and conn.connected:
            # Perform actual tool-level verification if env vars were provided
            if env_vars:
                verify_error = _verify_server_credentials(conn, server_name)
                if verify_error:
                    registry.remove_server(server_name)
                    logger.warning(f"Verification of credentials failed for '{server_name}': {verify_error}")
                    return json.dumps({
                        "success": False,
                        "error": f"Credential verification failed: {verify_error}"
                    })
            
            tools = conn.get_tools()
            registry.save_config()
            logger.info(f"Successfully connected to MCP server '{server_name}'. Found {len(tools)} tools.")
            return json.dumps({
                "success": True,
                "message": f"Successfully connected to MCP server '{server_name}'.",
                "discovered_tools": [t.to_dict() for t in tools]
            })
        else:
            registry.remove_server(server_name)
            logger.warning(f"Connection verification failed for MCP server '{server_name}'.")
            return json.dumps({
                "success": False,
                "error": f"MCP server '{server_name}' failed to connect or handshake failed. Please check credentials or network connection."
            })
    else:
        registry.remove_server(server_name)
        logger.warning(f"Failed to add/connect MCP server '{server_name}' in bridge.")
        return json.dumps({
            "success": False,
            "error": f"Failed to add or connect MCP server '{server_name}'."
        })


def list_connected_servers() -> str:
    """Returns the list of all configured and connected MCP servers."""
    logger.info("Listing connected MCP servers")
    registry = get_mcp_registry()
    servers = registry.list_servers()
    return json.dumps({"servers": servers})


def disconnect_mcp_server(server_name: str) -> str:
    """Disconnects and removes an MCP server from the registry."""
    logger.info(f"Disconnecting MCP server: '{server_name}'")
    registry = get_mcp_registry()
    success = registry.remove_server(server_name)
    registry.save_config()
    
    if success:
        return json.dumps({
            "success": True,
            "message": f"Successfully disconnected and removed MCP server '{server_name}'."
        })
    else:
        return json.dumps({
            "success": False,
            "error": f"Failed to disconnect or server '{server_name}' was not registered."
        })


# Register tools to global_tool_registry
reg.register(
    "install_mcp_server",
    "Installs and connects an external MCP server (e.g. github, slack, sqlite). Prompts for credentials if needed.",
    install_mcp_server,
    ["server_name"],
    RiskLevel.HIGH,
    "mcp"
)

reg.register(
    "list_mcp_servers",
    "List all currently configured and connected MCP servers.",
    list_connected_servers,
    [],
    RiskLevel.SAFE,
    "mcp"
)

reg.register(
    "disconnect_mcp_server",
    "Disconnects and removes an MCP server by name.",
    disconnect_mcp_server,
    ["server_name"],
    RiskLevel.MEDIUM,
    "mcp"
)

logger.info("Successfully registered MCP Installer tools in tool registry.")
