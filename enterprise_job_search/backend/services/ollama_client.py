import json
import logging
import requests
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Hardcoded for dev; use settings in production
OLLAMA_BASE_URL = "http://localhost:11434/api"
MODEL_NAME = "llama3"

class OllamaClient:
    """Client for interacting with local Ollama instance running Llama 3"""
    
    @staticmethod
    def generate(prompt: str, system: Optional[str] = None, format: Optional[str] = None) -> str:
        """Generate a raw text response from Ollama"""
        payload = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1
            }
        }
        if system:
            payload["system"] = system
        if format == "json":
            payload["format"] = "json"
            
        try:
            response = requests.post(f"{OLLAMA_BASE_URL}/generate", json=payload, timeout=60)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Ollama generation failed: {e}")
            raise

    @staticmethod
    def generate_json(prompt: str, system: Optional[str] = None) -> Dict[str, Any]:
        """Generate a response constrained to JSON format"""
        raw_response = OllamaClient.generate(prompt, system=system, format="json")
        try:
            return json.loads(raw_response)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode Ollama JSON response: {e}")
            return {}
