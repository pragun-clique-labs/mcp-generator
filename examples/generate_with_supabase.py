#!/usr/bin/env python3
"""
Example script showing how to use the MCP Generator with Supabase integration.

This script demonstrates how to generate an MCP server and save its endpoint
to your Supabase database automatically.
"""

import asyncio
import os
from src.agent.graph import graph, InputType

async def main():
    """Generate an MCP server and save it to Supabase."""
    
    # Required environment variables for Supabase
    required_env_vars = [
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "ANTHROPIC_API_KEY",
        "FREESTYLE_API_KEY",
        "MORPH_API_KEY"
    ]
    
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        print(f"❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set these environment variables:")
        for var in missing_vars:
            print(f"  export {var}=your_value_here")
        return
    
    # Example 1: Generate from OpenAPI spec
    print("🚀 Generating MCP server from OpenAPI spec...")
    
    initial_state = {
        "input_type": InputType.OPENAPI,
        "input_data": "https://api.example.com/openapi.json",  # Replace with your OpenAPI URL
        "project_id": "your-project-id-here",  # Replace with your Supabase project ID
        "validation_errors": [],
        "current_iteration": 0,
        "max_iterations": 3,
        "errors": []
    }
    
    try:
        result = await graph.ainvoke(initial_state)
        
        if result["current_phase"] == "completed":
            print("✅ MCP server generated and deployed successfully!")
            print(f"📊 Repository ID: {result.get('repo_id')}")
            print(f"🌐 Server URL: {result.get('dev_server_info', {}).get('ephemeral_url')}")
            
            if result.get('mcp_id'):
                print(f"💾 Saved to Supabase with MCP ID: {result['mcp_id']}")
            else:
                print("⚠️  MCP deployed but not saved to database")
                
        else:
            print(f"❌ Generation failed in phase: {result['current_phase']}")
            if result.get('errors'):
                for error in result['errors']:
                    print(f"  - {error['phase']}: {error['error']}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")

    # Example 2: Generate from description
    print("\n🚀 Generating MCP server from description...")
    
    description_state = {
        "input_type": InputType.DESCRIPTION,
        "input_data": "Create an MCP server that provides weather information for any city",
        "project_id": "your-project-id-here",  # Replace with your Supabase project ID
        "validation_errors": [],
        "current_iteration": 0,
        "max_iterations": 3,
        "errors": []
    }
    
    try:
        result = await graph.ainvoke(description_state)
        
        if result["current_phase"] == "completed":
            print("✅ MCP server generated and deployed successfully!")
            print(f"📊 Repository ID: {result.get('repo_id')}")
            print(f"🌐 Server URL: {result.get('dev_server_info', {}).get('ephemeral_url')}")
            
            if result.get('mcp_id'):
                print(f"💾 Saved to Supabase with MCP ID: {result['mcp_id']}")
            else:
                print("⚠️  MCP deployed but not saved to database")
                
        else:
            print(f"❌ Generation failed in phase: {result['current_phase']}")
            if result.get('errors'):
                for error in result['errors']:
                    print(f"  - {error['phase']}: {error['error']}")
                    
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
