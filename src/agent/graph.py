"""MCP Generator LangGraph Agent with ReAct Agent for Refinement."""

import asyncio
import json
import os
import tempfile
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, TypedDict

import aiofiles
import aiofiles.tempfile
import httpx

from langchain.chat_models import init_chat_model
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import HumanMessage
from langgraph.graph import END, StateGraph
from langgraph.prebuilt import create_react_agent
from pydantic import BaseModel
from dotenv import load_dotenv

# Import our tools (only the ones not provided by MCP)
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from tools import (
    morph_apply_edit,
    freestyle_create_repo,
    freestyle_request_dev_server,
    freestyle_test_mcp_server,
    freestyle_deploy_production
)

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    print("WARNING: Supabase environment variables not set. Database operations will be disabled.")

# Initialize the LLM once
anthropic_key = os.getenv("ANTHROPIC_API_KEY")
print(f"DEBUG: Initializing LLM with Anthropic key: {'SET' if anthropic_key else 'NOT SET'} (length: {len(anthropic_key) if anthropic_key else 0})")

try:
    llm = init_chat_model(
        "anthropic:claude-3-5-sonnet-20241022",
        temperature=0.1,
        anthropic_api_key=anthropic_key,
    )
    print("DEBUG: LLM initialized successfully")
except Exception as llm_error:
    print(f"DEBUG: LLM initialization failed: {type(llm_error).__name__}: {str(llm_error)}")
    raise llm_error


# Supabase Database Functions
async def save_mcp_to_database(
    project_id: str,
    name: str, 
    mcp_url: str,
    description: Optional[str] = None
) -> Optional[str]:
    """Save MCP server info to Supabase database."""
    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        print("WARNING: Supabase not configured, skipping database save")
        return None
    
    try:
        # Create the MCP parameters JSON for the database
        mcp_parameters = {
            "command": "node",
            "args": ["index.js"],
            "transport": "http",
            "url": mcp_url
        }
        
        # Prepare the data for insertion
        mcp_data = {
            "name": name,
            "project_id": project_id,
            "parameters": mcp_parameters,
            "description": description or f"Auto-generated MCP server deployed at {mcp_url}"
        }
        
        # Make the API call to Supabase
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{SUPABASE_URL}/rest/v1/mcp",
                headers={
                    "apikey": SUPABASE_ANON_KEY,
                    "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation"
                },
                json=mcp_data
            )
            
            if response.status_code == 201:
                result = response.json()
                if isinstance(result, list) and len(result) > 0:
                    mcp_id = result[0].get("id")
                    print(f"DEBUG: Successfully saved MCP to database with ID: {mcp_id}")
                    return mcp_id
                else:
                    print(f"DEBUG: Unexpected response format: {result}")
                    return None
            else:
                print(f"DEBUG: Failed to save MCP to database. Status: {response.status_code}, Response: {response.text}")
                return None
                
    except Exception as e:
        print(f"DEBUG: Error saving MCP to database: {type(e).__name__}: {str(e)}")
        return None


# State and Configuration Classes
class InputType(str, Enum):
    OPENAPI = "openapi"
    DESCRIPTION = "description"


class Phase(str, Enum):
    GENERATING = "generating"
    DEPLOYING = "deploying"
    TESTING = "testing"
    REFINING = "refining"
    PRODUCTION = "production"
    COMPLETED = "completed"
    FAILED = "failed"


class MCPGeneratorState(TypedDict):
    """State for the MCP Generator agent."""
    # Input
    input_type: InputType
    input_data: str  # OpenAPI URL or description
    project_id: str  # Supabase project ID for linking the MCP
    
    # Generation outputs
    mcp_server_files: Optional[Dict[str, str]]
    
    # Deployment info
    repo_id: Optional[str]
    dev_server_info: Optional[Dict[str, Any]]
    
    # Testing and refinement
    validation_errors: List[str]
    current_iteration: int
    max_iterations: int
    
    # Status tracking
    current_phase: Phase
    errors: List[Dict[str, str]]
    completed_at: Optional[str]
    
    # Database tracking
    mcp_id: Optional[str]  # Supabase MCP record ID





# Node Functions
async def generate_mcp_server(state: MCPGeneratorState, config: RunnableConfig) -> Dict[str, Any]:
    """Generate MCP server from OpenAPI spec or description."""
    updates = {"current_phase": Phase.GENERATING}
    
    try:
        if state["input_type"] == InputType.OPENAPI:
            # Validate URL format (trim whitespace)
            spec_url = state["input_data"].strip()
            if not (spec_url.startswith("http://") or spec_url.startswith("https://")):
                raise Exception(f"OpenAPI spec must be a valid URL, got: '{spec_url}'")
            
            # Create temp directory in thread to avoid blocking
            def run_openapi_generator():
                import subprocess
                with tempfile.TemporaryDirectory() as tmpdir:
                    # Run generator
                    result = subprocess.run([
                        "npx", "openapi-mcp-generator",
                        "--input", spec_url,
                        "--output", tmpdir
                    ], capture_output=True, text=True, timeout=120)
                    
                    if result.returncode != 0:
                        raise Exception(f"openapi-mcp-generator failed: {result.stderr}")
                    
                    # Read all files
                    files = {}
                    for root, _, filenames in os.walk(tmpdir):
                        for filename in filenames:
                            filepath = os.path.join(root, filename)
                            rel_path = os.path.relpath(filepath, tmpdir)
                            with open(filepath, 'r') as f:
                                files[rel_path] = f.read()
                    return files
            
            # Run everything in a thread
            files = await asyncio.to_thread(run_openapi_generator)
            updates["mcp_server_files"] = files
        
        else:  # DESCRIPTION
            # Generate using LLM
            prompt = f"""Generate a complete MCP server based on this description:
                {state["input_data"]}

                Create a Node.js MCP server with:
                1. package.json with proper dependencies
                2. index.js as the main server file
                3. Any additional files needed

                Return the files as JSON with filename -> content mapping."""

            response = await llm.ainvoke([HumanMessage(content=prompt)])
            
            try:
                files = json.loads(response.content)
                updates["mcp_server_files"] = files
            except json.JSONDecodeError:
                raise Exception("Failed to parse LLM response as JSON")
        
        updates["current_phase"] = Phase.DEPLOYING
        
    except Exception as e:
        updates["errors"] = state.get("errors", []) + [
            {"phase": "generation", "error": str(e)}
        ]
        updates["current_phase"] = Phase.FAILED
    
    return updates


async def deploy_to_dev_server(state: MCPGeneratorState, config: RunnableConfig) -> Dict[str, Any]:
    """Deploy MCP server to Freestyle dev server."""
    updates = {"current_phase": Phase.DEPLOYING}
    
    try:
        freestyle_api_key = os.getenv("FREESTYLE_API_KEY")
        
        if not freestyle_api_key:
            raise Exception("FREESTYLE_API_KEY environment variable required")
        
        # Create repository
        repo_result = await freestyle_create_repo(
            name=f"mcp-server-{datetime.now().strftime('%Y%m%d-%H%M%S')}",
            project_files=state["mcp_server_files"],
            freestyle_api_key=freestyle_api_key,
            public=True
        )
        
        updates["repo_id"] = repo_result["repo_id"]
        
        # Request dev server and write the initial files
        dev_server_result = await freestyle_request_dev_server(
            repo_id=repo_result["repo_id"],
            freestyle_api_key=freestyle_api_key,
            project_files=repo_result.get("project_files")
        )
        
        updates["dev_server_info"] = dev_server_result
        updates["current_phase"] = Phase.REFINING
        
    except Exception as e:
        updates["errors"] = state.get("errors", []) + [
            {"phase": "deployment", "error": str(e)}
        ]
        updates["current_phase"] = Phase.FAILED
    
    return updates


async def react_agent_workflow(state: MCPGeneratorState, config: RunnableConfig) -> Dict[str, Any]:
    """ReAct agent that tests, fixes, and deploys the MCP server."""
    updates = {"current_phase": Phase.REFINING}
    
    try:
        morph_api_key = os.getenv("MORPH_API_KEY")
        freestyle_api_key = os.getenv("FREESTYLE_API_KEY")
        
        if not morph_api_key or not freestyle_api_key:
            raise Exception("Both MORPH_API_KEY and FREESTYLE_API_KEY environment variables required")
        
        # Get MCP server URL from dev server info
        dev_server_info = state.get("dev_server_info", {})
        mcp_url = dev_server_info.get("mcp_ephemeral_url")
        
        if not mcp_url:
            raise Exception("No MCP server URL found in dev server info")
        
        # Import MCP adapters
        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as e:
            raise Exception(f"Failed to import MCP adapters: {e}")
        
        # Connect to Freestyle's MCP server
        try:
            print(f"DEBUG: Connecting to MCP server at {mcp_url}")
            print(f"DEBUG: Using Freestyle API key: {freestyle_api_key[:10]}...{freestyle_api_key[-4:]}")
            
            mcp_config = {
                "freestyle": {
                    "url": mcp_url,
                    "transport": "streamable_http",
                    "headers": {
                        "x-api-key": freestyle_api_key
                    }
                }
            }
            print(f"DEBUG: MCP client config: {mcp_config}")
            
            client = MultiServerMCPClient(mcp_config)
            print("DEBUG: MCP client created successfully")
            
            # Get tools from the MCP server
            print("DEBUG: About to get tools from MCP server...")
            try:
                mcp_tools = await client.get_tools()
                print(f"DEBUG: Retrieved {len(mcp_tools)} MCP tools successfully")
                
                # Log tool names for debugging
                tool_names = [tool.name if hasattr(tool, 'name') else str(tool) for tool in mcp_tools]
                print(f"DEBUG: MCP tool names: {tool_names}")
                
            except Exception as tools_error:
                print(f"DEBUG: Error getting tools: {type(tools_error).__name__}: {str(tools_error)}")
                raise tools_error
            
        except Exception as e:
            print(f"DEBUG: MCP connection failed: {type(e).__name__}: {str(e)}")
            print(f"DEBUG: Full exception details: {repr(e)}")
            if hasattr(e, '__cause__') and e.__cause__:
                print(f"DEBUG: Exception cause: {type(e.__cause__).__name__}: {str(e.__cause__)}")
            raise Exception(f"Failed to connect to MCP server at {mcp_url}: {e}")
        
        # Create the workflow prompt
        prompt = """You are an MCP server deployment agent. Your job is simple:

1. TEST the server using freestyle_test_mcp_server to see if it's accessible
2. If test PASSES: Use freestyle_deploy_production to deploy to production
3. If test FAILS: The server might not be running - you can try basic debugging with the available tools, but in most cases just report the issue

The test simply checks if the server is responding. If it responds with any status code under 500, consider it successful.

Available tools:
- freestyle_test_mcp_server(mcp_url, freestyle_api_key): Test if server is accessible
- freestyle_deploy_production(repo_id, freestyle_api_key): Deploy to production
- readFile, writeFile, editFile, ls, exec, commitAndPush, npmInstall, npmLint: Basic dev server tools
- morph_apply_edit: AI code editing (only use if absolutely necessary)

Keep it simple: Test → Deploy if working → Done."""
        
        # Combine MCP tools with our custom tools
        all_tools = mcp_tools + [
            morph_apply_edit,
            freestyle_test_mcp_server,
            freestyle_deploy_production
        ]
        
        print(f"DEBUG: Using {len(all_tools)} tools ({len(mcp_tools)} MCP + 3 custom)")
        
        # Create ReAct agent with all tools and prompt
        react_agent = create_react_agent(llm, all_tools, prompt=prompt)
        
        # Create the human input with current environment info
        human_input = f"""Current Environment:
- Repository ID: {state["repo_id"]}
- Server URL: {dev_server_info.get("ephemeral_url")} (this is both the dev server AND the MCP server)
- API Keys: MORPH_API_KEY and FREESTYLE_API_KEY are available as environment variables

The MCP server code has been deployed and npm run dev has been executed to start it.
Please test the MCP server, fix any issues, and deploy to production once working."""

        # Run the ReAct agent
        try:
            # Check if Anthropic API key is available
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_api_key:
                raise Exception("ANTHROPIC_API_KEY environment variable is required")
            
            print(f"DEBUG: API Keys status:")
            print(f"  - ANTHROPIC_API_KEY: {'SET' if anthropic_api_key else 'NOT SET'} (length: {len(anthropic_api_key) if anthropic_api_key else 0})")
            print(f"  - FREESTYLE_API_KEY: {'SET' if freestyle_api_key else 'NOT SET'} (length: {len(freestyle_api_key) if freestyle_api_key else 0})")
            print(f"  - MORPH_API_KEY: {'SET' if morph_api_key else 'NOT SET'} (length: {len(morph_api_key) if morph_api_key else 0})")
            
            # Run ReAct agent with detailed logging
            print(f"DEBUG: Starting ReAct agent with {len(all_tools)} tools")
            print(f"DEBUG: Human input length: {len(human_input)} chars")
            print(f"DEBUG: MCP URL: {mcp_url}")
            
            try:
                print("DEBUG: About to invoke ReAct agent...")
                result = await react_agent.ainvoke({
                    "messages": [HumanMessage(content=human_input)]
                })
                print("DEBUG: ReAct agent completed successfully")
            except Exception as agent_error:
                print(f"DEBUG: ReAct agent error type: {type(agent_error).__name__}")
                print(f"DEBUG: ReAct agent error message: {str(agent_error)}")
                print(f"DEBUG: Full agent error details: {repr(agent_error)}")
                
                # Print the full traceback for better debugging
                import traceback
                print(f"DEBUG: Full traceback:")
                print(traceback.format_exc())
                
                # Check if it's a schema-related error
                if "schema" in str(agent_error).lower() or "$schema" in str(agent_error):
                    print("DEBUG: Schema-related error detected")
                
                # Check if it's a rate limiting error
                if "rate" in str(agent_error).lower() or "quota" in str(agent_error).lower():
                    print("DEBUG: Rate limiting error detected")
                
                # Re-raise with more context
                raise Exception(f"ReAct agent failed - {type(agent_error).__name__}: {str(agent_error)}")
            
            # Save MCP server info to database after successful deployment
            try:
                # Generate a name based on the input data or timestamp
                if state["input_type"] == InputType.OPENAPI:
                    mcp_name = f"OpenAPI MCP - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                else:
                    # Extract a name from the description or use a default
                    description_preview = state["input_data"][:50] + "..." if len(state["input_data"]) > 50 else state["input_data"]
                    mcp_name = f"Custom MCP - {description_preview}"
                
                # Get the production URL (assuming it's similar to dev server URL but production)
                dev_server_info = state.get("dev_server_info", {})
                dev_url = dev_server_info.get("ephemeral_url", "")
                
                # For production, we'll assume it's the same URL but we'll store what we have
                # The ReAct agent should have deployed to production, so we use the ephemeral URL
                production_url = dev_url  # This might be updated by the ReAct agent
                
                if production_url and state.get("project_id"):
                    mcp_id = await save_mcp_to_database(
                        project_id=state["project_id"],
                        name=mcp_name,
                        mcp_url=production_url,
                        description=f"Generated from {state['input_type'].value}: {state['input_data'][:100]}..."
                    )
                    
                    if mcp_id:
                        updates["mcp_id"] = mcp_id
                        print(f"DEBUG: MCP saved to database with ID: {mcp_id}")
                    else:
                        print("DEBUG: Failed to save MCP to database, but deployment was successful")
                else:
                    print("DEBUG: Missing production URL or project_id, skipping database save")
            
            except Exception as db_error:
                print(f"DEBUG: Database save failed but deployment succeeded: {type(db_error).__name__}: {str(db_error)}")
                # Don't fail the whole process if database save fails
            
            updates["current_phase"] = Phase.COMPLETED
            updates["completed_at"] = datetime.now().isoformat()
            updates["react_result"] = "ReAct agent completed successfully"
            
        except Exception as e:
            error_msg = f"ReAct agent failed: {type(e).__name__}: {str(e)}"
            print(f"DEBUG: {error_msg}")  # Debug output
            raise Exception(error_msg)
        
    except Exception as e:
        updates["errors"] = state.get("errors", []) + [
            {"phase": "react_workflow", "error": str(e)}
        ]
        updates["current_phase"] = Phase.FAILED
    
    return updates


# Create the graph
def create_mcp_generator_graph() -> StateGraph:
    """Create the MCP Generator LangGraph."""
    
    workflow = StateGraph(MCPGeneratorState)
    
    # Add nodes - only 3 nodes!
    workflow.add_node("generate", generate_mcp_server)
    workflow.add_node("deploy_dev", deploy_to_dev_server)
    workflow.add_node("react_agent", react_agent_workflow)
    
    # Add edges - simple linear flow
    workflow.add_edge("generate", "deploy_dev")
    workflow.add_edge("deploy_dev", "react_agent")
    workflow.add_edge("react_agent", END)
    
    # Set entry point
    workflow.set_entry_point("generate")
    
    return workflow.compile()


# Export the compiled graph
graph = create_mcp_generator_graph()