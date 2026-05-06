#!/usr/bin/env python3
"""
Model Health Endpoint for JARVIS

Provides HTTP endpoint for monitoring model status and health.
Useful for production deployments and external monitoring systems.

Usage:
    python model_health_endpoint.py [--port 8080]
"""

import json
import logging
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, Any
import argparse
import sys
from pathlib import Path

# Add project root to path
current_file = Path(__file__).resolve()
project_root = current_file.parent
sys.path.insert(0, str(project_root))

from jarvis.models.model_adapter import (
    get_reasoning_model,
    get_vision_model,
    GPTOSSAdapter,
    Gemma3Adapter
)

logger = logging.getLogger(__name__)


class ModelHealthHandler(BaseHTTPRequestHandler):
    """HTTP handler for model health endpoints."""
    
    # Class-level cache for model status
    _model_status: Dict[str, Any] = {}
    _last_check: float = 0
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == '/health':
            self._handle_health()
        elif self.path == '/health/models':
            self._handle_models_health()
        elif self.path == '/health/ready':
            self._handle_readiness()
        elif self.path == '/':
            self._handle_index()
        else:
            self.send_error(404, "Not Found")
    
    def _handle_index(self):
        """Return API documentation."""
        response = {
            "service": "JARVIS Model Health Monitor",
            "version": "2.0",
            "endpoints": {
                "/": "This documentation",
                "/health": "Overall system health",
                "/health/models": "Detailed model status",
                "/health/ready": "Readiness probe (200=ready, 503=not ready)"
            }
        }
        self._send_json_response(response)
    
    def _handle_health(self):
        """Return overall system health."""
        status = self._check_all_models()
        healthy = all([
            status["reasoning_model"]["available"],
            status["vision_model"]["available"]
        ])
        
        response = {
            "status": "healthy" if healthy else "degraded",
            "timestamp": self._get_timestamp(),
            "models": {
                "reasoning": status["reasoning_model"]["available"],
                "vision": status["vision_model"]["available"]
            }
        }
        
        self._send_json_response(response, status_code=200 if healthy else 503)
    
    def _handle_models_health(self):
        """Return detailed model status."""
        status = self._check_all_models()
        response = {
            "timestamp": self._get_timestamp(),
            "models": status
        }
        self._send_json_response(response)
    
    def _handle_readiness(self):
        """Readiness probe for Kubernetes/load balancers."""
        status = self._check_all_models()
        is_ready = all([
            status["reasoning_model"]["available"],
            status["vision_model"]["available"]
        ])
        
        if is_ready:
            self._send_json_response({"status": "ready"}, status_code=200)
        else:
            self._send_json_response({
                "status": "not_ready",
                "missing": [
                    name for name, info in status.items() 
                    if not info["available"]
                ]
            }, status_code=503)
    
    def _check_all_models(self) -> Dict[str, Any]:
        """Check status of all models with caching."""
        import time
        current_time = time.time()
        
        # Cache for 5 seconds to avoid excessive checks
        if current_time - self._last_check < 5 and self._model_status:
            return self._model_status
        
        status = {}
        
        # Check reasoning model (GPT-OSS 120B)
        try:
            model = get_reasoning_model()
            # Quick ping test
            test_response = model.generate("Say 'ping'", max_tokens=10)
            status["reasoning_model"] = {
                "available": True,
                "model_name": model.model_name,
                "response_time_ms": test_response.metadata.get("response_time_ms", 0),
                "status": "operational"
            }
        except Exception as e:
            status["reasoning_model"] = {
                "available": False,
                "model_name": "gpt-oss:120b",
                "error": str(e),
                "status": "unavailable"
            }
        
        # Check vision model (Gemma 3 27B)
        try:
            model = get_vision_model()
            # Quick ping test
            test_response = model.generate("Say 'ping'", max_tokens=10)
            status["vision_model"] = {
                "available": True,
                "model_name": model.model_name,
                "response_time_ms": test_response.metadata.get("response_time_ms", 0),
                "status": "operational"
            }
        except Exception as e:
            status["vision_model"] = {
                "available": False,
                "model_name": "gemma3:27b",
                "error": str(e),
                "status": "unavailable"
            }
        
        self._model_status = status
        self._last_check = current_time
        
        return status
    
    def _send_json_response(self, data: Dict[str, Any], status_code: int = 200):
        """Send JSON response."""
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode('utf-8'))
    
    def _get_timestamp(self) -> str:
        """Get current ISO timestamp."""
        from datetime import datetime
        return datetime.utcnow().isoformat() + "Z"


def run_server(port: int = 8080):
    """Run the health check server."""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    server_address = ('', port)
    httpd = HTTPServer(server_address, ModelHealthHandler)
    
    logger.info(f"Starting Model Health Endpoint on port {port}")
    logger.info(f"Endpoints:")
    logger.info(f"  - http://localhost:{port}/health (overall health)")
    logger.info(f"  - http://localhost:{port}/health/models (detailed model status)")
    logger.info(f"  - http://localhost:{port}/health/ready (readiness probe)")
    logger.info(f"  - http://localhost:{port}/ (API docs)")
    logger.info(f"\nPress Ctrl+C to stop")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("\nShutting down server...")
        httpd.shutdown()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='JARVIS Model Health Endpoint')
    parser.add_argument('--port', '-p', type=int, default=8080,
                        help='Port to run the server on (default: 8080)')
    args = parser.parse_args()
    
    run_server(args.port)
