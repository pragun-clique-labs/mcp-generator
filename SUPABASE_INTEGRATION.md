# Supabase Integration for MCP Generator

## Overview

The MCP Generator now integrates with Supabase to automatically save generated MCP server information to your database. When an MCP server is successfully generated and deployed, it will be saved to the `mcp` table with all necessary connection parameters.

## Database Schema

The integration uses the existing `mcp` table with the following structure:

```sql
CREATE TABLE mcp (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  project_id UUID NOT NULL REFERENCES projects(id),
  parameters JSONB,
  description TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

## What Gets Saved

When an MCP server is successfully generated, the following information is saved:

- **name**: Auto-generated based on input type and timestamp
- **project_id**: The Supabase project ID you provide
- **parameters**: JSON object containing MCP connection info:
  ```json
  {
    "command": "node",
    "args": ["index.js"],
    "transport": "http",
    "url": "https://your-deployed-server.com"
  }
  ```
- **description**: Details about how the MCP was generated

## Environment Variables

### Required for MCP Generation
```bash
ANTHROPIC_API_KEY=your_anthropic_key
FREESTYLE_API_KEY=your_freestyle_key
MORPH_API_KEY=your_morph_key
```

### Required for Supabase Integration
```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your_anon_key
```

## Usage

### 1. Using the Interactive Script

```bash
cd mcp-generator
python run_mcp_generator.py
```

The script will:
1. Check for required environment variables
2. Prompt for your Supabase project ID
3. Ask how you want to generate the MCP (OpenAPI URL or description)
4. Generate, deploy, and save the MCP server automatically

### 2. Using the Graph Directly

```python
from src.agent.graph import graph, InputType

# Create initial state with project_id
state = {
    "input_type": InputType.OPENAPI,
    "input_data": "https://api.example.com/openapi.json",
    "project_id": "your-supabase-project-id",
    "validation_errors": [],
    "current_iteration": 0,
    "max_iterations": 3,
    "errors": []
}

# Run the graph
result = await graph.ainvoke(state)

# Check if saved to database
if result.get('mcp_id'):
    print(f"Saved to Supabase with ID: {result['mcp_id']}")
```

### 3. Using the Example Script

```bash
cd mcp-generator
python examples/generate_with_supabase.py
```

## Error Handling

The integration includes robust error handling:

- **Missing Environment Variables**: The system warns if Supabase variables are not set but continues with deployment
- **Database Save Failures**: If the MCP deploys successfully but database saving fails, the deployment is still considered successful
- **Project ID Validation**: The system validates that a project_id is provided when Supabase is configured

## Integration Flow

1. **Generate**: MCP server code is generated from OpenAPI spec or description
2. **Deploy**: Server is deployed to Freestyle dev environment
3. **Test & Refine**: ReAct agent tests and fixes any issues
4. **Deploy Production**: Server is deployed to production environment
5. **Save to Database**: MCP connection info is saved to Supabase ✨ **NEW**

## Viewing Generated MCPs

After generation, you can view your MCPs in the admin panel:
- Navigate to your admin panel
- Go to the MCPs section
- Find your newly generated MCP by name and timestamp
- Use the stored parameters to connect to your MCP server

## Troubleshooting

### Supabase Connection Issues
- Verify your `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- Ensure the project ID exists in your `projects` table
- Check that RLS policies allow inserts to the `mcp` table

### MCP Not Saved to Database
- Check the console output for database error messages
- Verify the project_id is valid
- Ensure the deployment was successful before database save attempt

### Generation Failures
- Verify all required API keys are set
- Check network connectivity for OpenAPI URL access
- Review error messages in the console output

## API Reference

### `save_mcp_to_database(project_id, name, mcp_url, description=None)`

Saves MCP server information to Supabase database.

**Parameters:**
- `project_id` (str): Supabase project ID
- `name` (str): Display name for the MCP
- `mcp_url` (str): URL where the MCP server is deployed
- `description` (str, optional): Description of the MCP

**Returns:**
- `str | None`: The database ID of the created MCP record, or None if failed

**Example:**
```python
mcp_id = await save_mcp_to_database(
    project_id="123e4567-e89b-12d3-a456-426614174000",
    name="Weather API MCP",
    mcp_url="https://my-mcp-server.com",
    description="Provides weather information for cities"
)
```
