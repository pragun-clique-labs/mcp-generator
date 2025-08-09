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

# Initialize the LLM once
llm = init_chat_model(
    "anthropic:claude-3-5-sonnet-20241022",
    temperature=0.1,
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
)


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
            client = MultiServerMCPClient({
                "freestyle": {
                    "url": mcp_url,
                    "transport": "streamable_http"
                }
            })
            
            # Get tools from the MCP server
            print("DEBUG: Getting tools from MCP server...")
            mcp_tools = await client.get_tools()
            print(f"DEBUG: Retrieved {len(mcp_tools)} MCP tools")
            
            # Log tool names for debugging
            tool_names = [tool.name if hasattr(tool, 'name') else str(tool) for tool in mcp_tools]
            print(f"DEBUG: MCP tool names: {tool_names}")
            
        except Exception as e:
            print(f"DEBUG: MCP connection failed: {type(e).__name__}: {str(e)}")
            raise Exception(f"Failed to connect to MCP server at {mcp_url}: {e}")
        
        # Create the workflow prompt
        prompt = """You are an MCP server development agent. Your job is to test and fix an MCP server running on a Freestyle dev server.

IMPORTANT: The MCP server you're testing IS the application running on the dev server. The dev server URL and MCP server URL are the SAME thing.

Step-by-step workflow:
1. TEST the MCP server using freestyle_test_mcp_server
2. If test FAILS:
   a. Use readFile to examine the code (package.json, index.js, etc.)
   b. Identify the problem from error messages
   c. Use morph_apply_edit to fix the code with specific instructions
   d. Use writeFile to save the fixed code
   e. Use commitAndPush to save changes
   f. Test again
3. If test PASSES: Use freestyle_deploy_production to deploy

Tools available:
- readFile(path): Read a file from the dev server
- writeFile(path, content): Write a file to the dev server  
- editFile(path, old_text, new_text): Search and replace in files
- ls(path): List files in a directory
- exec(command): Execute shell commands on the dev server
- commitAndPush(message): Commit and push changes to the repo
- npmInstall(package): Install an npm module
- npmLint(): Lint the code

- morph_apply_edit(file_content, edit_instructions, morph_api_key): Use AI to fix complex code issues
- freestyle_test_mcp_server(mcp_url, freestyle_api_key): Test if MCP server responds correctly
- freestyle_deploy_production(repo_id, freestyle_api_key): Deploy working server to production

DEBUGGING TIPS:
- If server doesn't respond: Check if it's running (npm run dev should have started it)
- If getting errors: Read the main server file (usually index.js) and package.json
- If port issues: MCP servers usually run on specific ports, check the code
- If JSON-RPC errors: The server must respond to MCP protocol initialization requests

Start by testing the server. Be methodical and fix one issue at a time."""
        
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
            
            # Run ReAct agent with detailed logging
            print(f"DEBUG: Starting ReAct agent with {len(all_tools)} tools")
            print(f"DEBUG: Human input length: {len(human_input)} chars")
            
            try:
                result = await react_agent.ainvoke({
                    "messages": [HumanMessage(content=human_input)]
                })
                print("DEBUG: ReAct agent completed successfully")
            except Exception as agent_error:
                print(f"DEBUG: ReAct agent error type: {type(agent_error).__name__}")
                print(f"DEBUG: ReAct agent error message: {str(agent_error)}")
                
                # Check if it's a schema-related error
                if "schema" in str(agent_error).lower() or "$schema" in str(agent_error):
                    print("DEBUG: Schema-related error detected")
                
                # Check if it's a rate limiting error
                if "rate" in str(agent_error).lower() or "quota" in str(agent_error).lower():
                    print("DEBUG: Rate limiting error detected")
                
                # Re-raise with more context
                raise Exception(f"ReAct agent failed - {type(agent_error).__name__}: {str(agent_error)}")
            
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