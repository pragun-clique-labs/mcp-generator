"""Example usage of the MCP Generator agent."""

import asyncio
import os
from dotenv import load_dotenv

from agent import graph

# Load environment variables
load_dotenv()


async def generate_from_openapi_example():
    """Example: Generate MCP server from OpenAPI specification."""
    # Input state with OpenAPI URL
    input_state = {
        "openapi_url": "https://petstore.swagger.io/v2/swagger.json",
        "max_iterations": 3,
        "current_iteration": 0,
        "deployment_stage": "none",
        "errors": [],
        "test_results": [],
        "validation_errors": [],
        "refinement_history": [],
        "mcp_server_code": {},
    }
    
    # Configuration
    config = {
        "configurable": {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "morph_api_key": os.getenv("MORPH_API_KEY"),
            "freestyle_api_key": os.getenv("FREESTYLE_API_KEY"),
            "use_local_freestyle": True,  # Use local dev server
            "max_iterations": 3,
        }
    }
    
    print("Generating MCP server from OpenAPI spec...")
    
    # Run the agent
    result = await graph.ainvoke(input_state, config)
    
    # Print results
    print(f"\nFinal status: {result.get('current_phase')}")
    
    if result.get("freestyle_dev_server_url"):
        print(f"Dev server URL: {result['freestyle_dev_server_url']}")
    
    if result.get("freestyle_prod_url"):
        print(f"Production URL: {result['freestyle_prod_url']}")
    
    if result.get("errors"):
        print("\nErrors encountered:")
        for error in result["errors"]:
            print(f"  - {error}")
    
    return result


async def generate_from_description_example():
    """Example: Generate MCP server from natural language description."""
    # Input state with description
    input_state = {
        "user_description": """Create an MCP server that provides tools for:
        1. Searching GitHub repositories by topic or language
        2. Getting repository details including stars, forks, and description
        3. Listing recent commits for a repository
        4. Creating GitHub issues
        
        The server should handle authentication via GitHub personal access token.""",
        "max_iterations": 5,
        "current_iteration": 0,
        "deployment_stage": "none",
        "errors": [],
        "test_results": [],
        "validation_errors": [],
        "refinement_history": [],
        "mcp_server_code": {},
    }
    
    # Configuration
    config = {
        "configurable": {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "morph_api_key": os.getenv("MORPH_API_KEY"),
            "freestyle_api_key": os.getenv("FREESTYLE_API_KEY"),
            "use_local_freestyle": True,
            "max_iterations": 5,
        }
    }
    
    print("Generating MCP server from description...")
    
    # Run the agent
    result = await graph.ainvoke(input_state, config)
    
    # Print results
    print(f"\nFinal status: {result.get('current_phase')}")
    
    if result.get("current_iteration") > 0:
        print(f"Refinement iterations: {result['current_iteration']}")
    
    if result.get("freestyle_dev_server_url"):
        print(f"Dev server URL: {result['freestyle_dev_server_url']}")
    
    if result.get("validation_errors"):
        print("\nValidation errors fixed:")
        for error in result["validation_errors"]:
            print(f"  - {error}")
    
    return result


async def main():
    """Run examples."""
    print("MCP Generator Examples")
    print("=" * 50)
    
    # Choose which example to run
    choice = input("\nSelect example:\n1. Generate from OpenAPI spec\n2. Generate from description\nChoice (1 or 2): ")
    
    if choice == "1":
        await generate_from_openapi_example()
    elif choice == "2":
        await generate_from_description_example()
    else:
        print("Invalid choice")


if __name__ == "__main__":
    asyncio.run(main())
