"""Integration tests for MCP Generator agent."""

import pytest
import os
import tempfile

from agent import graph

pytestmark = pytest.mark.anyio


@pytest.mark.langsmith
async def test_mcp_generator_with_description() -> None:
    """Test generating MCP server from description."""
    # Create a simple description
    input_state = {
        "user_description": "Create a simple MCP server with a hello world tool that takes a name parameter and returns a greeting",
        "max_iterations": 2,
        "current_iteration": 0,
        "deployment_stage": "none",
        "errors": [],
        "test_results": [],
        "validation_errors": [],
        "refinement_history": [],
        "mcp_server_code": {},
    }
    
    config = {
        "configurable": {
            "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY"),
            "use_local_freestyle": True,
            "max_iterations": 2,
        }
    }
    
    # Skip if no API key
    if not config["configurable"]["anthropic_api_key"]:
        pytest.skip("ANTHROPIC_API_KEY not set")
    
    # Run the agent
    result = await graph.ainvoke(input_state, config)
    
    # Verify basic results
    assert result is not None
    assert "current_phase" in result
    assert "mcp_server_code" in result
    assert len(result["mcp_server_code"]) > 0
    

@pytest.mark.langsmith
async def test_input_classification() -> None:
    """Test input classification node."""
    from agent.graph import classify_input
    
    # Test OpenAPI classification
    state_openapi = {
        "openapi_url": "https://example.com/openapi.json",
    }
    result = await classify_input(state_openapi, {"configurable": {}})
    assert result["input_type"] == "openapi"
    
    # Test description classification
    state_desc = {
        "user_description": "Create an MCP server",
    }
    result = await classify_input(state_desc, {"configurable": {}})
    assert result["input_type"] == "description"
    
    # Test no input
    state_empty = {}
    result = await classify_input(state_empty, {"configurable": {}})
    assert "errors" in result
    assert result.get("current_phase") == "failed"


@pytest.mark.langsmith
async def test_error_analysis() -> None:
    """Test error analysis functionality."""
    from agent.refiner import analyze_errors
    from agent.graph import TestResult
    
    # Create test results with errors
    test_results = [
        TestResult(
            test_name="server_health",
            passed=False,
            error="Connection timeout",
        ),
        TestResult(
            test_name="list_tools",
            passed=False,
            error="404 Not Found",
        ),
    ]
    
    validation_errors = [
        "Tool schema validation failed",
        "Server returned 500 error",
    ]
    
    # Analyze errors
    analysis = analyze_errors(test_results, validation_errors)
    
    assert "failed_tests" in analysis
    assert len(analysis["failed_tests"]) == 2
    assert "error_patterns" in analysis
    assert "suggested_fixes" in analysis