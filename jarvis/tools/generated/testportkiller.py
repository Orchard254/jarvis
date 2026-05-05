from jarvis.tools.base import BaseTool, ToolResult

class TestPortKiller(BaseTool):
    name = "test_port_killer"
    description = "Test tool for port killing"
    
    def execute(self, port: int = 8080) -> ToolResult:
        return ToolResult.ok(f"Would kill process on port {port}")
    
    def validate(self, **kwargs):
        return True, ""
