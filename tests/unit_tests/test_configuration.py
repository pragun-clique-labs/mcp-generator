"""Unit tests for MCP Generator configuration and components."""

from langgraph.pregel import Pregel
import pytest

from agent.graph import graph, MCPGeneratorState, Phase, InputType, DeploymentStage
from agent.generators import create_basic_mcp_template
from agent.refiner import generate_fix_instructions


def test_graph_compilation() -> None:
    """Test that the graph compiles correctly."""
    assert isinstance(graph, Pregel)
    
    # Check that all expected nodes are present
    nodes = list(graph.nodes.keys())
    expected_nodes = [
        "classify", "generate", "deploy", "test", 
        "refine", "deploy_prod", "complete", "failed"
    ]
    for node in expected_nodes:
        assert node in nodes


def test_state_enums() -> None:
    """Test state enum values."""
    # Test InputType enum
    assert InputType.OPENAPI == "openapi"
    assert InputType.DESCRIPTION == "description"
    
    # Test DeploymentStage enum
    assert DeploymentStage.NONE == "none"
    assert DeploymentStage.DEV == "dev"
    assert DeploymentStage.PROD == "prod"
    
    # Test Phase enum
    assert Phase.GENERATING == "generating"
    assert Phase.DEPLOYING == "deploying"
    assert Phase.TESTING == "testing"
    assert Phase.REFINING == "refining"
    assert Phase.COMPLETE == "complete"
    assert Phase.FAILED == "failed"


def test_basic_mcp_template() -> None:
    """Test basic MCP template generation."""
    template = create_basic_mcp_template()
    
    # Check required files
    assert "src/index.ts" in template
    assert "package.json" in template
    assert "tsconfig.json" in template
    assert "README.md" in template
    
    # Check that files contain expected content
    assert "@modelcontextprotocol/sdk" in template["src/index.ts"]
    assert '"name": "generated-mcp-server"' in template["package.json"]
    assert '"target": "ES2022"' in template["tsconfig.json"]


def test_fix_instructions_generation() -> None:
    """Test generation of fix instructions."""
    error_analysis = {
        "error_patterns": ["Server connection issues", "Tool-related errors"],
        "failed_tests": [
            {
                "test": "mcp_connection",
                "error": "Connection failed",
            }
        ],
    }
    
    instructions = generate_fix_instructions("src/index.ts", error_analysis)
    
    assert "Fix the following issues" in instructions
    assert "server starts correctly" in instructions
    assert "tools have proper name" in instructions
    assert "MCP protocol initialization" in instructions


def test_minimal_args_creation() -> None:
    """Test creation of minimal arguments for tool testing."""
    from agent.tester import create_minimal_args
    
    # Test with various schemas
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "count": {"type": "integer"},
            "enabled": {"type": "boolean"},
        },
        "required": ["name", "count"],
    }
    
    args = create_minimal_args(schema)
    
    assert args == {"name": "test", "count": 0}
    assert "enabled" not in args  # Optional field not included
    
    # Test with empty schema
    assert create_minimal_args({}) == {}
    assert create_minimal_args(None) == {}