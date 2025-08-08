#Actively in Use
"""
LLM Client for DSL Repair Pipeline

Provides a thin wrapper around Ollama and OpenAI APIs for LLM calls
used in the DSL repair pipeline.
"""

import os
import json
import asyncio
import logging
from typing import Optional, Dict, Any
import httpx
from pydantic import BaseModel, Field

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

logger = logging.getLogger(__name__)

class LlmRequest(BaseModel):
    """Request model for LLM calls."""
    prompt: str = Field(..., description="The prompt to send to the LLM")
    model: str = Field("gemma3n:e4b", description="Model name to use")
    temperature: float = Field(0.0, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(800, gt=0, le=4000, description="Maximum tokens to generate")

class LlmResponse(BaseModel):
    """Response model for LLM calls."""
    text: str = Field(..., description="Generated text response")
    model: str = Field(..., description="Model used for generation")
    provider: str = Field(..., description="Provider used (ollama/openai)")

class LlmClient:
    """Thin wrapper for LLM API calls with fallback support."""
    
    def __init__(self, endpoint: str, fallback_provider: str = "openai"):
        self.endpoint = endpoint
        self.fallback_provider = fallback_provider
        self.timeout = 60.0
        
    async def call_llm(self, prompt: str, **kwargs) -> LlmResponse:
        """
        Call LLM with the given prompt.
        
        Args:
            prompt: The prompt to send
            **kwargs: Additional parameters (model, temperature, max_tokens)
            
        Returns:
            LlmResponse with generated text and metadata
            
        Raises:
            Exception: If both primary and fallback providers fail
        """
        request = LlmRequest(prompt=prompt, **kwargs)
        
        # Try primary provider (Ollama)
        try:
            return await self._call_ollama(request)
        except Exception as e:
            logger.warning(f"Primary LLM provider failed: {e}")
            
            # Try fallback provider (OpenAI)
            if self.fallback_provider == "openai" and OPENAI_AVAILABLE:
                try:
                    return await self._call_openai(request)
                except Exception as fallback_e:
                    logger.error(f"Fallback LLM provider also failed: {fallback_e}")
                    raise Exception(f"Both LLM providers failed. Primary: {e}, Fallback: {fallback_e}")
            else:
                raise Exception(f"Primary LLM provider failed and fallback unavailable: {e}")
    
    async def _call_ollama(self, request: LlmRequest) -> LlmResponse:
        """Call Ollama API."""
        body = {
            "model": request.model,
            "prompt": request.prompt,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(self.endpoint, json=body)
            response.raise_for_status()
            
            data = response.json()
            return LlmResponse(
                text=data.get("response", ""),
                model=request.model,
                provider="ollama"
            )
    
    async def _call_openai(self, request: LlmRequest) -> LlmResponse:
        """Call OpenAI API as fallback."""
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI library not available")
            
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        # Map Ollama model names to OpenAI equivalents
        model_mapping = {
            "llama2-13b": "gpt-4o-mini",
            "llama2-7b": "gpt-4o-mini",
            "llama2": "gpt-4o-mini"
        }
        
        openai_model = model_mapping.get(request.model, "gpt-4o-mini")
        
        # Use asyncio.to_thread for OpenAI sync calls
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model=openai_model,
            messages=[{"role": "user", "content": request.prompt}],
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        return LlmResponse(
            text=response.choices[0].message.content,
            model=openai_model,
            provider="openai"
        )

# Global client instance
_llm_client: Optional[LlmClient] = None

def get_llm_client() -> LlmClient:
    """Get or create the global LLM client instance."""
    global _llm_client
    if _llm_client is None:
        from config import get_config
        config = get_config()
        _llm_client = LlmClient(
            endpoint=config.master_orchestrator.llm.endpoint,
            fallback_provider=config.master_orchestrator.llm.fallback_provider
        )
    return _llm_client

async def call_llm(prompt: str, **kwargs) -> str:
    """
    Convenience function to call LLM and return just the text.
    
    Args:
        prompt: The prompt to send
        **kwargs: Additional parameters
        
    Returns:
        Generated text response
    """
    client = get_llm_client()
    response = await client.call_llm(prompt, **kwargs)
    return response.text 