"""
tools/network/connectivity.py — Network tools

Tools for: wifi info, IP address, ping host
Uses subprocess and PowerShell for network queries.
"""

import logging
import subprocess
from typing import Any

from ..base import BaseTool, ToolResult

log = logging.getLogger("network_tools")


class GetWifiTool(BaseTool):
    """Get Wi-Fi connection information."""
    
    name = "get_wifi"
    description = "Get current Wi-Fi network information including SSID, signal strength, and connection status."
    parameters = {}
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        try:
            script = r"""
            $profile = netsh wlan show interfaces | Select-String -Pattern "^\s+SSID\s*:" -Context 0,0
            if ($profile) {
                $ssid = ($profile -replace "^\s+SSID\s*:\s*", "").Trim()
                $signal = netsh wlan show interfaces | Select-String -Pattern "^\s+Signal\s*:" 
                $signalPercent = ($signal -replace "^\s+Signal\s*:\s*", "").Trim() -replace "%", ""
                "Connected to: $ssid (Signal: $signalPercent%)"
            } else {
                "Not connected to any Wi-Fi network"
            }
            """
            
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                return ToolResult.ok(output if output else "Wi-Fi status unknown")
            else:
                return ToolResult.fail(error=f"Failed to get Wi-Fi info: {result.stderr}")
                
        except Exception as e:
            log.error(f"Failed to get Wi-Fi info: {e}")
            return ToolResult.fail(error=f"Failed to get Wi-Fi info: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        return 2.0
    
    def risk_level(self) -> str:
        return "low"


class GetIpTool(BaseTool):
    """Get IP address information."""
    
    name = "get_ip"
    description = "Get the local IP address and optionally the public IP address."
    parameters = {
        "type": {
            "type": "string",
            "enum": ["local", "public", "both"],
            "description": "Type of IP to retrieve (default: local)",
        },
    }
    required_parameters = []
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        ip_type = kwargs.get("type", "local")
        if ip_type not in ["local", "public", "both"]:
            return False, "type must be 'local', 'public', or 'both'"
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        ip_type = kwargs.get("type", "local")
        results = []
        
        try:
            if ip_type in ["local", "both"]:
                # Get local IP
                script = """
                (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {$_.InterfaceAlias -notlike "*Loopback*" -and $_.IPAddress -notlike "169.254.*"} | Select-Object -First 1).IPAddress
                """
                result = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                local_ip = result.stdout.strip() if result.returncode == 0 else "unknown"
                results.append(f"Local IP: {local_ip}")
            
            if ip_type in ["public", "both"]:
                # Get public IP via API
                try:
                    import urllib.request
                    with urllib.request.urlopen("https://api.ipify.org", timeout=5) as response:
                        public_ip = response.read().decode().strip()
                    results.append(f"Public IP: {public_ip}")
                except Exception as e:
                    results.append(f"Public IP: unavailable ({e})")
            
            return ToolResult.ok("\n".join(results))
            
        except Exception as e:
            log.error(f"Failed to get IP info: {e}")
            return ToolResult.fail(error=f"Failed to get IP info: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        ip_type = kwargs.get("type", "local")
        return 3.0 if ip_type == "both" else 1.5
    
    def risk_level(self) -> str:
        return "low"


class PingTool(BaseTool):
    """Ping a host to check connectivity."""
    
    name = "ping"
    description = "Ping a host to check network connectivity and latency."
    parameters = {
        "host": {
            "type": "string",
            "description": "Hostname or IP address to ping",
        },
        "count": {
            "type": "integer",
            "description": "Number of pings to send (default: 4, max: 10)",
        },
    }
    required_parameters = ["host"]
    
    def validate(self, **kwargs) -> tuple[bool, str]:
        host = kwargs.get("host")
        if not host:
            return False, "host parameter is required"
        
        count = kwargs.get("count", 4)
        if not isinstance(count, int) or count < 1 or count > 10:
            return False, "count must be between 1 and 10"
        
        # Basic host validation
        if len(host) > 253:
            return False, "host name too long"
        
        return True, ""
    
    def execute(self, **kwargs) -> ToolResult:
        host = kwargs["host"]
        count = min(kwargs.get("count", 4), 10)
        
        try:
            result = subprocess.run(
                ["ping", "-n", str(count), host],
                capture_output=True,
                text=True,
                timeout=count * 3 + 5,  # Allow 3 seconds per ping plus buffer
            )
            
            output = result.stdout.strip()
            
            if result.returncode == 0:
                # Extract summary line
                lines = output.split("\n")
                for line in lines:
                    if "Average" in line or "Minimum" in line:
                        return ToolResult.ok(f"Ping to {host}: {line.strip()}")
                return ToolResult.ok(output[-500:])  # Last 500 chars if no summary
            else:
                return ToolResult.fail(error=f"Ping failed: {output[-200:]}")
                
        except subprocess.TimeoutExpired:
            return ToolResult.fail(error="Ping timed out")
        except Exception as e:
            log.error(f"Failed to ping {host}: {e}")
            return ToolResult.fail(error=f"Failed to ping {host}: {e}")
    
    def estimate_duration(self, **kwargs) -> float:
        count = kwargs.get("count", 4)
        return float(count) * 1.5
    
    def risk_level(self) -> str:
        return "low"


# Export all tool classes
NETWORK_TOOLS = [
    GetWifiTool,
    GetIpTool,
    PingTool,
]
