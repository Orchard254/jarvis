"""
models/ollama_client.py — Ollama LLM client wrapper with cloud/local fallback

Handles all LLM communication with:
- Automatic cloud/local endpoint fallback
- Exponential backoff retry logic
- Streaming support for TTS
- Tool calling support
- Vision/multimodal support
"""

import json
import logging
import time
from typing import Callable, Generator, Optional, List, Dict, Any

import requests


def _load_settings():
    """Load settings with fallback to config system."""
    try:
        from settings import (
            OLLAMA_CLOUD_URL, OLLAMA_LOCAL_URL, OLLAMA_API_KEY,
            OLLAMA_MODEL, OLLAMA_TIMEOUT, OLLAMA_MAX_RETRIES,
        )
        return {
            'cloud_url': OLLAMA_CLOUD_URL,
            'local_url': OLLAMA_LOCAL_URL,
            'api_key': OLLAMA_API_KEY,
            'model': OLLAMA_MODEL,
            'timeout': OLLAMA_TIMEOUT,
            'max_retries': OLLAMA_MAX_RETRIES,
        }
    except ImportError:
        from jarvis.config.config import get_config
        cfg = get_config()
        return {
            'cloud_url': cfg.get('ollama_cloud_url', 'https://api.ollama.com/api/chat'),
            'local_url': cfg.get('ollama_local_url', 'http://localhost:11434/api/chat'),
            'api_key': cfg.get('ollama_api_key', ''),
            'model': cfg.get('ollama_model', 'nemotron-3-nano:30b-cloud'),
            'timeout': cfg.get('ollama_timeout', 60),
            'max_retries': cfg.get('ollama_max_retries', 3),
        }


log = logging.getLogger("ollama_client")


class OllamaUnavailableError(Exception):
    """Raised when all Ollama endpoints (cloud and local) are unreachable."""
    pass


class OllamaClient:
    """Ollama API client with automatic fallback and retry logic."""
    
    def __init__(
        self,
        cloud_url: Optional[str] = None,
        local_url: str = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        timeout: int = None,
        max_retries: int = None,
        base_backoff: float = 1.0,
    ):
        # Load settings with fallback
        _settings = _load_settings()
        
        # Use settings defaults, allow overrides
        self.cloud_url = cloud_url or _settings['cloud_url']
        self.local_url = local_url or _settings['local_url']
        self.api_key = api_key if api_key is not None else _settings['api_key']
        self.model = model or _settings['model']
        self.timeout = timeout or _settings['timeout']
        self.max_retries = max_retries if max_retries is not None else _settings['max_retries']
        self.base_backoff = base_backoff
        
        # Track which endpoint is working
        self._preferred_endpoint = "cloud" if self.api_key else "local"
    
    def _get_endpoints(self) -> List[tuple]:
        """Return list of (url, headers, name) tuples to try in order."""
        endpoints = []
        
        # Try preferred endpoint first
        if self._preferred_endpoint == "cloud":
            if self.cloud_url:
                endpoints.append((
                    self.cloud_url,
                    {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    "cloud"
                ))
            endpoints.append((self.local_url, {"Content-Type": "application/json"}, "local"))
        else:
            endpoints.append((self.local_url, {"Content-Type": "application/json"}, "local"))
            if self.cloud_url:
                endpoints.append((
                    self.cloud_url,
                    {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    "cloud"
                ))
        
        return endpoints
    
    def _request_with_retry(
        self,
        url: str,
        headers: dict,
        payload: dict,
        endpoint_name: str,
        stream: bool = False,
    ) -> Optional[requests.Response]:
        """Make request with exponential backoff retry."""
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                resp = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    stream=stream,
                    timeout=(5, self.timeout),  # connect fast (5s), read is patient
                )
                resp.raise_for_status()
                
                if attempt > 0:
                    log.info(f"[OLLAMA] Success on attempt {attempt + 1} ({endpoint_name})")
                
                # Update preferred endpoint on success
                self._preferred_endpoint = endpoint_name
                
                return resp
                
            except requests.exceptions.HTTPError as e:
                last_error = e
                log.warning(f"[OLLAMA] {endpoint_name} HTTP error (attempt {attempt + 1}): {e}")
                # Use e.response.status_code instead of resp.status_code for safety
                status = e.response.status_code if e.response else 0
                if status >= 500:  # Server error, retry
                    if attempt < self.max_retries - 1:
                        backoff = self.base_backoff * (2 ** attempt)
                        log.info(f"[OLLAMA] Retrying in {backoff:.1f}s...")
                        time.sleep(backoff)
                    continue
                elif status == 429:  # Rate limited - retry with backoff
                    if attempt < self.max_retries - 1:
                        backoff = self.base_backoff * (2 ** attempt) * 2  # Longer backoff for rate limits
                        log.info(f"[OLLAMA] Rate limited. Retrying in {backoff:.1f}s...")
                        time.sleep(backoff)
                    continue
                else:
                    break  # Other client error, don't retry
                    
            except requests.exceptions.ConnectionError as e:
                last_error = e
                log.warning(f"[OLLAMA] {endpoint_name} connection error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.info(f"[OLLAMA] Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)
                continue
                
            except Exception as e:
                last_error = e
                log.warning(f"[OLLAMA] {endpoint_name} error (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    backoff = self.base_backoff * (2 ** attempt)
                    log.info(f"[OLLAMA] Retrying in {backoff:.1f}s...")
                    time.sleep(backoff)
                continue
        
        log.error(f"[OLLAMA] All retries failed for {endpoint_name}: {last_error}")
        return None
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[dict]] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Send chat request to Ollama.
        
        Args:
            messages: List of message dicts with role/content
            tools: Optional list of tool definitions for function calling
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            stream: Whether to stream response
            
        Returns:
            Dict with keys: content, tool_calls, done, error
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        
        if tools:
            payload["tools"] = tools
        
        for url, headers, name in self._get_endpoints():
            log.info(f"[OLLAMA] Calling {name} endpoint: {url}")
            
            resp = self._request_with_retry(url, headers, payload, name, stream=False)
            
            if resp is None:
                continue
            
            try:
                # Handle both single JSON response and streaming responses
                response_text = resp.text.strip()
                
                # Check for empty response
                if not response_text:
                    log.warning(f"[OLLAMA] Empty response from {name} endpoint")
                    continue
                
                # Try to parse as single JSON first (standard response)
                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                    # Might be streaming response with multiple JSON lines or extra data
                    # Parse line by line and combine/find the complete response
                    lines = response_text.split('\n')
                    data = None
                    last_valid_data = None
                    accumulated_content = ""
                    chunk_count = 0
                    
                    for line in lines:
                        line = line.strip()
                        if line:
                            try:
                                candidate = json.loads(line)
                                chunk_count += 1
                                
                                # Keep track of last valid JSON as fallback
                                last_valid_data = candidate
                                
                                # Accumulate content from all chunks
                                msg_content = candidate.get("message", {}).get("content", "")
                                if msg_content:
                                    accumulated_content += msg_content
                                
                                # Prefer JSON objects that have done=true (final chunk)
                                if candidate.get("done") and "message" in candidate:
                                    data = candidate
                                    # Merge accumulated content if the final chunk has empty content
                                    if not data.get("message", {}).get("content"):
                                        data["message"]["content"] = accumulated_content
                                    break
                            except json.JSONDecodeError:
                                continue
                    
                    # If no done=true found, use last valid JSON with accumulated content
                    if data is None:
                        if last_valid_data:
                            data = last_valid_data
                            # Use accumulated content if available
                            if accumulated_content and not data.get("message", {}).get("content"):
                                data["message"]["content"] = accumulated_content
                        else:
                            log.error(f"[OLLAMA] Could not parse any JSON from {name} endpoint. Response: {response_text[:500]}")
                            continue
                    
                    # Log only first few chunks to reduce verbosity
                    if chunk_count <= 3:
                        log.debug(f"[OLLAMA] Parsed {chunk_count} chunks from {name}")
                
                msg = data.get("message", {})
                
                # Get raw content including thinking tags
                raw_content = msg.get("content") or ""
                is_done = data.get("done", True)
                
                # Check if this is a pure thinking chunk (empty content, not done)
                # But DON'T skip if the response is done - we need to process it
                if not raw_content.strip() and not is_done:
                    log.debug(f"[OLLAMA] Skipping thinking chunk from {name}")
                    continue
                
                # For reasoning models, the content might contain <think>...</think> tags
                # We should NOT treat this as empty - let the brain parse it
                # Only consider it truly empty if there's NO content at all when done
                if not raw_content.strip() and is_done:
                    # Check if there are tool_calls which would make this valid
                    tool_calls = msg.get("tool_calls") or []
                    if tool_calls:
                        # Valid response with tool calls but no text content
                        return {
                            "content": "",
                            "tool_calls": tool_calls,
                            "done": is_done,
                            "error": None,
                            "endpoint": name,
                        }
                    else:
                        # Truly empty response
                        log.warning(f"[OLLAMA] Empty response from {name} endpoint (done=True). Model may not be responding correctly.")
                        continue  # Try next endpoint
                
                # Return the full content (including any thinking tags for brain to parse)
                return {
                    "content": raw_content,
                    "tool_calls": msg.get("tool_calls") or [],
                    "done": is_done,
                    "error": None,
                    "endpoint": name,
                }
                
            except Exception as e:
                log.error(f"[OLLAMA] Response parsing error from {name}: {e}")
                log.error(f"[OLLAMA] Raw response: {resp.text[:500]}")
                continue
        
        # All endpoints failed - raise exception
        log.error("[OLLAMA] All endpoints (cloud and local) are unreachable")
        raise OllamaUnavailableError(
            "All Ollama endpoints failed. Cloud endpoint may be unreachable or rate-limited, "
            "and local Ollama server is not running. Please check your connection or start "
            "Ollama locally with 'ollama serve'."
        )
    
    def stream_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 512,
    ) -> Generator[str, None, None]:
        """
        Stream chat response sentence-by-sentence for TTS.
        
        Yields:
            Complete sentences as they are generated
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        
        buffer = ""
        yielded_text = ""
        
        # Common abbreviations that shouldn't split sentences
        abbreviations = {
            "dr", "mr", "mrs", "ms", "prof", "sr", "jr", "etc", "vs",
            "e.g", "i.e", "u.s", "u.k", "a.m", "p.m",
        }
        
        def is_sentence_end(buf: str, pos: int) -> bool:
            if buf[pos] not in ".!?":
                return False
            word_start = pos - 1
            while word_start >= 0 and buf[word_start].isalpha():
                word_start -= 1
            word = buf[word_start + 1 : pos].lower()
            if word in abbreviations:
                return False
            if pos + 1 < len(buf) and buf[pos + 1] == " ":
                return True
            return False
        
        for url, headers, name in self._get_endpoints():
            log.info(f"[OLLAMA] Streaming from {name} endpoint")
            
            resp = self._request_with_retry(url, headers, payload, name, stream=True)
            
            if resp is None:
                continue
            
            try:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    token = chunk.get("message", {}).get("content", "")
                    buffer += token
                    
                    while True:
                        found = False
                        for i, ch in enumerate(buffer):
                            if is_sentence_end(buffer, i) and i + 1 < len(buffer) and buffer[i + 1] == " ":
                                sentence = buffer[: i + 1].strip()
                                buffer = buffer[i + 2 :]
                                if sentence:
                                    yield sentence
                                    yielded_text += sentence + " "
                                found = True
                                break
                        if not found:
                            break
                    
                    if chunk.get("done"):
                        break
                
                break  # Success, don't try other endpoints
                
            except Exception as e:
                log.error(f"[OLLAMA] Streaming error from {name}: {e}")
                continue
        
        # Flush remaining buffer
        if buffer.strip():
            yield buffer.strip()
    
    def chat_with_vision(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        Send chat request with image support (multimodal).
        
        Args:
            messages: List of message dicts. Images should be base64 in content
                      or as separate image field
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            
        Returns:
            Dict with keys: content, tool_calls, done, error
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "images": [],  # Will be populated from messages
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        
        # Extract images from messages for Ollama cloud API compatibility
        for msg in messages:
            if isinstance(msg.get("content"), list):
                # Multi-modal format
                for item in msg["content"]:
                    if isinstance(item, dict) and item.get("type") == "image_url":
                        img_url = item.get("image_url", {})
                        if isinstance(img_url, dict):
                            url = img_url.get("url", "")
                            if url.startswith("data:image"):
                                base64_data = url.split(",", 1)[1] if "," in url else url
                                payload["images"].append(base64_data)
            elif msg.get("images"):
                # Direct images array
                payload["images"].extend(msg["images"])
        
        for url, headers, name in self._get_endpoints():
            log.info(f"[OLLAMA] Vision call to {name} endpoint")
            
            resp = self._request_with_retry(url, headers, payload, name, stream=False)
            
            if resp is None:
                continue
            
            try:
                # Handle both single JSON response and streaming responses
                response_text = resp.text.strip()
                
                # Try to parse as single JSON first (standard response)
                try:
                    data = json.loads(response_text)
                except json.JSONDecodeError:
                    # Might be streaming response with multiple JSON lines or extra data
                    # Parse line by line and combine/find the complete response
                    lines = response_text.split('\n')
                    data = None
                    last_valid_data = None
                    
                    for line in lines:
                        line = line.strip()
                        if line:
                            try:
                                candidate = json.loads(line)
                                # Prefer JSON objects that have the message key
                                if "message" in candidate:
                                    data = candidate
                                    break
                                # Keep track of last valid JSON as fallback
                                last_valid_data = candidate
                            except json.JSONDecodeError:
                                continue
                    
                    # If no message found, use last valid JSON or skip
                    if data is None:
                        if last_valid_data:
                            data = last_valid_data
                        else:
                            log.error(f"[OLLAMA] Could not parse any JSON from {name} endpoint. Response: {response_text[:500]}")
                            continue
                
                msg = data.get("message", {})
                
                return {
                    "content": (msg.get("content") or "").strip(),
                    "tool_calls": msg.get("tool_calls") or [],
                    "done": data.get("done", True),
                    "error": None,
                    "endpoint": name,
                }
                
            except Exception as e:
                log.error(f"[OLLAMA] Response parsing error from {name}: {e}")
                log.error(f"[OLLAMA] Raw response: {resp.text[:500]}")
                continue
        
        # All endpoints failed - raise exception
        log.error("[OLLAMA] All endpoints (cloud and local) are unreachable for vision call")
        raise OllamaUnavailableError(
            "All Ollama endpoints failed for vision call. Cloud endpoint may be unreachable or rate-limited, "
            "and local Ollama server is not running."
        )
    
    def chat_with_image(
        self,
        image_base64: str,
        prompt: str,
        model: str = None,
        response_format: str = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """
        Alias for chat_with_vision for backward compatibility.
        Send chat request with image support (multimodal).
        
        Args:
            image_base64: Base64-encoded image
            prompt: Text prompt/question about the image
            model: Optional model override
            response_format: Optional response format hint ('json', 'text')
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            
        Returns:
            Dict with keys: content, tool_calls, done, error
        """
        # Build messages array with image
        messages = [
            {
                "role": "user",
                "content": prompt,
                "images": [image_base64] if image_base64 else []
            }
        ]
        
        # Use provided model or default - temporarily set it on self
        original_model = self.model
        if model:
            self.model = model
        
        try:
            # Make the vision call
            return self.chat_with_vision(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        finally:
            # Restore original model
            self.model = original_model


    async def generate_async(self, prompt: str, temperature: float = 0.7) -> str:
        """
        Async wrapper around synchronous chat() for Tree of Thoughts compatibility.
        
        Runs the blocking chat() call in a thread pool executor so it does not
        block the event loop while the ToT engine awaits multiple branches.
        
        Args:
            prompt: The prompt string to send
            temperature: Sampling temperature (default 0.7)
            
        Returns:
            Response content as string
        """
        import asyncio
        messages = [{"role": "user", "content": prompt}]
        
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.chat(
                messages=messages,
                temperature=temperature,
                stream=False,
            )
        )
        
        # Extract string content from response
        if isinstance(result, dict):
            # Standard chat response format
            content = result.get('content', '')
            if not content:
                # Try nested message format
                content = result.get('message', {}).get('content', '')
            return content or ''
        
        return str(result) if result else ''

    def is_available(self) -> bool:
        """Check if any Ollama endpoint is available."""
        for url, headers, name in self._get_endpoints():
            try:
                # For cloud URL, check the base URL; for local, use /tags endpoint
                if 'api.ollama.com' in url:
                    # Cloud API - just check if we can reach the base URL
                    check_url = url.replace('/api/chat', '')
                    resp = requests.get(check_url, headers=headers, timeout=5)
                else:
                    # Local Ollama server - use /tags endpoint
                    resp = requests.get(url.replace("/chat", "/tags"), headers=headers, timeout=5)
                if resp.status_code == 200:
                    log.info(f"[OLLAMA] {name} endpoint is available")
                    return True
            except Exception as e:
                log.debug(f"[OLLAMA] Health check failed for {name}: {e}")
        return False
    
    async def generate_async(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> str:
        """
        Async wrapper for chat completion - generates text response.
        
        Args:
            prompt: User prompt
            temperature: Sampling temperature
            max_tokens: Max tokens to generate
            
        Returns:
            Generated text content
        """
        messages = [{"role": "user", "content": prompt}]
        result = await self._async_chat(messages, temperature=temperature, max_tokens=max_tokens)
        return result.get("content", "")
    
    async def _async_chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ) -> Dict[str, Any]:
        """Internal async chat method."""
        import asyncio
        
        # Run synchronous chat in executor to make it async-compatible
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self.chat(messages, temperature=temperature, max_tokens=max_tokens)
        )
        return result


# Global client instance (lazy initialization)
_client: Optional[OllamaClient] = None


def get_ollama_client(
    cloud_url: str = "https://api.ollama.com/api/chat",
    local_url: str = "http://localhost:11434/api/chat",
    api_key: str = "",
    model: str = "nemotron-3-nano:30b-cloud",
) -> OllamaClient:
    """Get or create global OllamaClient instance."""
    global _client
    if _client is None:
        _client = OllamaClient(
            cloud_url=cloud_url,
            local_url=local_url,
            api_key=api_key,
            model=model,
        )
    return _client


# Alias for backwards compatibility
get_client = get_ollama_client
