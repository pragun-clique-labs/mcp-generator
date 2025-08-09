#!/usr/bin/env python
"""Quick script to run the MCP Generator agent."""

import asyncio
import os
import sys
from dotenv import load_dotenv

from src.agent.graph import graph, InputType

# Load environment variables
load_dotenv()


async def main():
    """Main entry point."""
    print("MCP Generator Agent with Supabase Integration")
    print("=" * 60)
    
    # Check for required environment variables
    required_vars = [
        "ANTHROPIC_API_KEY",
        "FREESTYLE_API_KEY", 
        "MORPH_API_KEY"
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"\n❌ Missing required environment variables: {', '.join(missing_vars)}")
        print("\nPlease set these in your .env file:")
        for var in missing_vars:
            print(f"  {var}=your_value_here")
        return
    
    # Check for Supabase variables (optional but recommended)
    supabase_url = os.getenv("NEXT_PUBLIC_SUPABASE_URL")
    supabase_key = os.getenv("NEXT_PUBLIC_SUPABASE_ANON_KEY")
    
    if not supabase_url or not supabase_key:
        print("\n⚠️  Supabase environment variables not set.")
        print("   Generated MCP servers will not be saved to database.")
        print("   To enable database saving, set:")
        print("   - NEXT_PUBLIC_SUPABASE_URL")
        print("   - NEXT_PUBLIC_SUPABASE_ANON_KEY")
        print()
    
    # Get project ID for Supabase
    project_id = None
    if supabase_url and supabase_key:
        project_id = input("Enter your Supabase project ID (or press Enter to skip database saving): ").strip()
        if not project_id:
            print("⚠️  Skipping database saving (no project ID provided)")
    
    # Get input type
    print("\nHow would you like to generate an MCP server?")
    print("1. From OpenAPI specification URL")
    print("2. From natural language description")
    
    choice = input("\nEnter your choice (1 or 2): ").strip()
    
    if choice == "1":
        # OpenAPI input
        openapi_url = input("\nEnter OpenAPI spec URL: ").strip()
        
        if not (openapi_url.startswith("http://") or openapi_url.startswith("https://")):
            print("❌ Please provide a valid HTTP/HTTPS URL")
            return
            
        input_state = {
            "input_type": InputType.OPENAPI,
            "input_data": openapi_url,
            "project_id": project_id or "",
            "validation_errors": [],
            "current_iteration": 0,
            "max_iterations": 3,
            "errors": []
        }
    
    elif choice == "2":
        # Description input
        print("\nDescribe the MCP server you want to create.")
        print("Example: Create an MCP server with tools for searching GitHub repos and creating issues")
        
        description = input("\nYour description: ").strip()
        
        if not description:
            print("❌ Description cannot be empty")
            return
            
        input_state = {
            "input_type": InputType.DESCRIPTION,
            "input_data": description,
            "project_id": project_id or "",
            "validation_errors": [],
            "current_iteration": 0,
            "max_iterations": 3,
            "errors": []
        }
    
    else:
        print("❌ Invalid choice!")
        return
    
    # Run the graph
    print("\nStarting MCP generation...")
    print("🔄 This may take a few minutes...")
    
    try:
        result = await graph.ainvoke(input_state)
        
        print(f"\n{'='*60}")
        print("🎉 GENERATION RESULTS")
        print(f"{'='*60}")
        
        if result["current_phase"] == "completed":
            print("✅ MCP server generated and deployed successfully!")
            
            # Show deployment info
            if result.get('repo_id'):
                print(f"📊 Repository ID: {result['repo_id']}")
            
            dev_server_info = result.get('dev_server_info', {})
            if dev_server_info.get('ephemeral_url'):
                print(f"🌐 Server URL: {dev_server_info['ephemeral_url']}")
            
            # Show database save info
            if result.get('mcp_id'):
                print(f"💾 Saved to Supabase with MCP ID: {result['mcp_id']}")
                print("   You can now view this MCP in your admin panel!")
            elif project_id:
                print("⚠️  MCP deployed but not saved to database")
            
            if result.get('completed_at'):
                print(f"⏱️  Completed at: {result['completed_at']}")
                
        else:
            print(f"❌ Generation failed in phase: {result['current_phase']}")
            
            if result.get('errors'):
                print("\n🔍 Error details:")
                for error in result['errors']:
                    print(f"  - {error['phase']}: {error['error']}")
        
        print(f"\n{'='*60}")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  Generation cancelled by user")
    except Exception as e:
        print(f"\n❌ Error during generation: {e}")
        print("\nTip: Check your environment variables and network connection")


if __name__ == "__main__":
    asyncio.run(main())
