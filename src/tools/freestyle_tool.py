"""Freestyle.sh tools for MCP server development and deployment."""

import os
from typing import Dict, Any, Optional
from langchain_core.tools import tool

import freestyle

async def freestyle_create_repo(
    name: str,
    project_files: Dict[str, str],
    freestyle_api_key: str,
    public: bool = True
) -> Dict[str, str]:
    """Create a new Git repository on Freestyle.sh with the MCP server code.
    
    Args:
        name: Name for the repository
        project_files: Dictionary of filename -> content for the MCP server
        freestyle_api_key: Freestyle API key
        public: Whether to make the repo public (for testing)
        
    Returns:
        Dictionary with repo_id and other repo details
    """
    client = freestyle.Freestyle(freestyle_api_key)
    
    # Create empty repository
    repo = client.create_repository(
        name=name,
        public=public
    )
    
    # Extract repo_id from response - handle different possible attribute names
    repo_id = getattr(repo, 'repo_id', None) or getattr(repo, 'id', None) or getattr(repo, 'repoId', None)
    
    if not repo_id:
        # Debug: print available attributes if we can't find repo_id
        available_attrs = [attr for attr in dir(repo) if not attr.startswith('_')]
        raise Exception(f"Could not find repo_id in response. Available attributes: {available_attrs}")
    
    # Store the project files to write later via the dev server
    return {
        "repo_id": repo_id,
        "name": name,
        "status": "created",
        "project_files": project_files  # Pass files to be written by dev server
    }


async def freestyle_request_dev_server(
    repo_id: str,
    freestyle_api_key: str,
    project_files: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Request a dev server for the MCP repository and optionally write initial files.
    
    Args:
        repo_id: ID of the repository to create dev server for
        freestyle_api_key: Freestyle API key
        project_files: Optional dictionary of files to write to the dev server
        
    Returns:
        Dictionary with dev server details and utilities
    """
    client = freestyle.Freestyle(freestyle_api_key)
    
    # Request dev server
    dev_server = client.request_dev_server(repo_id=repo_id)
    
    # Write project files if provided
    if project_files:
        for file_path, content in project_files.items():
            dev_server.fs.write_file(file_path, content)
        
        # Commit and push the initial files
        dev_server.commit_and_push("Initial MCP server files")
        
        # Start the MCP server with npm run dev
        print("DEBUG: Starting MCP server with npm run dev...")
        dev_server.process.exec("npm run dev")
    
    # Extract URLs with fallbacks for different attribute names
    ephemeral_url = getattr(dev_server, 'ephemeral_url', None) or getattr(dev_server, 'ephemeralUrl', None)
    mcp_ephemeral_url = getattr(dev_server, 'mcp_ephemeral_url', None) or getattr(dev_server, 'mcpEphemeralUrl', None)
    code_server_url = getattr(dev_server, 'code_server_url', None) or getattr(dev_server, 'codeServerUrl', None)
    is_new = getattr(dev_server, 'is_new', None) or getattr(dev_server, 'isNew', False)
    
    return {
        "ephemeral_url": ephemeral_url,
        "mcp_ephemeral_url": mcp_ephemeral_url,
        "code_server_url": code_server_url,
        "repo_id": repo_id,
        "is_new": is_new,
        "dev_command_running": getattr(dev_server, 'dev_command_running', False),
        "install_command_running": getattr(dev_server, 'install_command_running', False)
    }





@tool
async def freestyle_test_mcp_server(
    mcp_url: str,
    freestyle_api_key: str
) -> Dict[str, Any]:
    """Test the MCP server running on Freestyle dev server.
    
    Args:
        mcp_url: URL of the MCP server to test
        freestyle_api_key: Freestyle API key
        
    Returns:
        Test results
    """
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Test MCP initialization
            response = await client.post(
                f"{mcp_url}/mcp/v1/initialize",
                json={
                    "jsonrpc": "2.0",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "1.0.0",
                        "clientInfo": {
                            "name": "mcp-tester",
                            "version": "1.0.0"
                        }
                    },
                    "id": 1
                },
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                return {
                    "passed": True,
                    "status_code": response.status_code,
                    "response": response.json()
                }
            else:
                return {
                    "passed": False,
                    "status_code": response.status_code,
                    "error": f"MCP initialization failed: {response.status_code}"
                }
                
    except Exception as e:
        return {
            "passed": False,
            "error": str(e)
        }


@tool
async def freestyle_deploy_production(
    repo_id: str,
    freestyle_api_key: str
) -> Dict[str, str]:
    """Deploy the MCP server from repository to production on Freestyle.sh.
    
    Args:
        repo_id: Repository ID to deploy
        freestyle_api_key: Freestyle API key
        
    Returns:
        Production deployment details
    """
    # Mock implementation - in reality you'd use Freestyle deployment API
    # freestyle = FreestyleSandboxes(api_key=freestyle_api_key)
    # deployment = await freestyle.deployToProduction({"repoId": repo_id})
    
    return {
        "deployment_id": f"prod-{repo_id}-{hash(repo_id) % 1000}",
        "production_url": f"https://prod-{repo_id}.freestyle.sh",
        "status": "deployed",
        "repo_id": repo_id
    }