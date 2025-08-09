#!/usr/bin/env python
"""Quick script to run the MCP Generator agent."""

import asyncio
import os
import sys
from dotenv import load_dotenv

from agent import graph

# Load environment variables
load_dotenv()


async def main():
    """Main entry point."""
    print("MCP Generator Agent")
    print("=" * 50)
    
    # Get input type
    print("\nHow would you like to generate an MCP server?")
    print("1. From OpenAPI specification (URL or file)")
    print("2. From natural language description")
    
    choice = input("\nEnter your choice (1 or 2): ").strip()
    
    if choice == "1":
        # OpenAPI input
        openapi_input = input("\nEnter OpenAPI spec URL or file path: ").strip()
        
        if os.path.exists(openapi_input):
            # Load from file
            import json
            import yaml
            
            with open(openapi_input, 'r') as f:
                if openapi_input.endswith('.yaml') or openapi_input.endswith('.yml'):
                    spec = yaml.safe_load(f)
                else:
                    spec = json.load(f)
            
            input_state = {"openapi_spec": spec}
        else:
            # Assume it's a URL
            input_state = {"openapi_url": openapi_input}
    
    elif choice == "2":
        # Description input
        print("\nDescribe the MCP server you want to create.")
        print("Example: Create an MCP server with tools for searching GitHub repos and creating issues")
        
        description = input("\nYour description: ").strip()
        input_state = {"user_description": description}
    
    else:
        print("Invalid choice!")
        return
    
    # Add required state fields (minimal for LangGraph Studio compatibility)
    input_state.update({
        "deployment_stage": "none",
        "test_results": [],
        "validation_errors": [],
        "mcp_server_code": {},
    })
    
    # Configuration from environment
    config = {
        "configurable": {
            "max_iterations": int(os.getenv("MAX_ITERATIONS", 5)),
            "morph_api_key": os.getenv("MORPH_API_KEY"),
            "freestyle_api_key": os.getenv("FREESTYLE_API_KEY"),
            "use_local_freestyle": os.getenv("USE_LOCAL_FREESTYLE", "false").lower() == "true",
        }
    }
    
    # Check for required Google API key
    if not os.getenv("GOOGLE_API_KEY"):
        print("\nError: GOOGLE_API_KEY environment variable is required.")
        print("Please set it in your .env file or environment.")
        return
    
    # Run the graph
    print("\nStarting MCP generation...")
    try:
        result = await graph.ainvoke(input_state, config)
        print(f"\nGeneration completed!")
        print(f"Final phase: {result.get('current_phase')}")
        if result.get('errors'):
            print(f"Errors encountered: {result['errors']}")
        if result.get('freestyle_prod_url'):
            print(f"Production URL: {result['freestyle_prod_url']}")
    except Exception as e:
        print(f"Error during generation: {e}")


if __name__ == "__main__":
    asyncio.run(main())
