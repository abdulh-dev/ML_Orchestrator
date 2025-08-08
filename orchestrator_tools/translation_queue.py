#Actively in Use
"""
Translation Queue for Async NL→DSL Translation

Implements the async translation pipeline from the Hybrid API design:
- Redis-backed token queue for scalability
- Status tracking with detailed error states
- Timeout and failure handling
- Fallback to in-memory queue if Redis unavailable
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timedelta
from enum import Enum
from uuid import uuid4
import yaml

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .translator import LLMTranslator, NeedsHumanError

logger = logging.getLogger(__name__)

class TranslationStatus(Enum):
    """Translation status states."""
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"
    NEEDS_HUMAN = "needs_human"
    TIMEOUT = "timeout"

class TranslationQueue:
    """
    Async translation queue with Redis backing and in-memory fallback.
    
    Features:
    - Token-based tracking for client polling
    - Redis persistence with automatic fallback
    - Timeout handling and cleanup
    - Comprehensive error categorization
    """
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 queue_name: str = "translation:q",
                 token_prefix: str = "translation:",
                 timeout_seconds: int = 300):
        """
        Initialize translation queue.
        
        Args:
            redis_url: Redis connection URL
            queue_name: Name of the Redis list for queue
            token_prefix: Prefix for translation token keys
            timeout_seconds: Max time for translation before timeout
        """
        self.redis_url = redis_url
        self.queue_name = queue_name
        self.token_prefix = token_prefix
        self.timeout_seconds = timeout_seconds
        
        # Redis connection
        self.redis_client: Optional[redis.Redis] = None
        self.use_redis = False
        
        # In-memory fallback
        self.in_memory_queue = asyncio.Queue()
        self.in_memory_tokens: Dict[str, Dict[str, Any]] = {}
        
        # Statistics
        self.stats = {
            "translations_queued": 0,
            "translations_completed": 0,
            "translations_failed": 0,
            "translations_timed_out": 0,
            "translations_needs_human": 0
        }
        
        logger.info(f"Translation queue initialized with timeout={timeout_seconds}s")
    
    async def initialize(self) -> bool:
        """Initialize Redis connection with fallback."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using in-memory queue fallback")
            return False
        
        try:
            self.redis_client = redis.from_url(self.redis_url, decode_responses=True)
            # Test connection
            await self.redis_client.ping()
            self.use_redis = True
            logger.info("Redis translation queue initialized successfully")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory fallback: {e}")
            self.redis_client = None
            self.use_redis = False
            return False
    
    async def enqueue(self, text: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Enqueue natural language text for translation.
        
        Args:
            text: Natural language text to translate
            metadata: Optional metadata to include
            
        Returns:
            Translation token for polling status
        """
        token = uuid4().hex
        timestamp = datetime.utcnow()
        
        translation_data = {
            "status": TranslationStatus.QUEUED.value,
            "text": text,
            "metadata": metadata or {},
            "created_at": timestamp.isoformat(),
            "updated_at": timestamp.isoformat(),
            "retries": 0
        }
        
        try:
            if self.use_redis and self.redis_client:
                try:
                    # Use pipeline for atomic operations
                    pipeline = self.redis_client.pipeline()
                    
                    # Store token data
                    pipeline.hset(
                        f"{self.token_prefix}{token}",
                        mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                                for k, v in translation_data.items()}
                    )
                    
                    # Add to queue
                    pipeline.rpush(self.queue_name, token)
                    
                    # Set expiration for cleanup
                    pipeline.expire(
                        f"{self.token_prefix}{token}",
                        self.timeout_seconds + 3600  # Extra buffer for cleanup
                    )
                    
                    # Execute all operations atomically
                    await pipeline.execute()
                except AttributeError:
                    # Fallback for Redis clients that don't support pipeline
                    await self.redis_client.hset(
                        f"{self.token_prefix}{token}",
                        mapping={k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                                for k, v in translation_data.items()}
                    )
                    await self.redis_client.rpush(self.queue_name, token)
                    await self.redis_client.expire(
                        f"{self.token_prefix}{token}",
                        self.timeout_seconds + 3600
                    )
            else:
                # In-memory fallback
                self.in_memory_tokens[token] = translation_data.copy()
                await self.in_memory_queue.put(token)
            
            self.stats["translations_queued"] += 1
            logger.info(f"Translation queued with token: {token}")
            return token
            
        except Exception as e:
            logger.error(f"Failed to enqueue translation: {e}")
            raise
    
    async def get_status(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get translation status by token.
        
        Args:
            token: Translation token
            
        Returns:
            Translation status data or None if not found
        """
        try:
            if self.use_redis and self.redis_client:
                data = await self.redis_client.hgetall(f"{self.token_prefix}{token}")
                if not data:
                    return None
                
                # Parse JSON fields back
                for key in ["metadata", "dsl", "error_details"]:
                    if key in data and data[key]:
                        try:
                            data[key] = json.loads(data[key])
                        except (json.JSONDecodeError, TypeError):
                            pass
                
                return data
            else:
                # In-memory fallback
                return self.in_memory_tokens.get(token)
                
        except Exception as e:
            logger.error(f"Failed to get status for token {token}: {e}")
            return None
    
    async def update_status(self, 
                          token: str, 
                          status: TranslationStatus,
                          dsl: Optional[str] = None,
                          error_message: Optional[str] = None,
                          error_details: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update translation status.
        
        Args:
            token: Translation token
            status: New status
            dsl: Generated DSL (if successful)
            error_message: Error message (if failed)
            error_details: Detailed error information
            
        Returns:
            True if update successful
        """
        try:
            update_data = {
                "status": status.value,
                "updated_at": datetime.utcnow().isoformat()
            }
            
            if dsl:
                update_data["dsl"] = dsl
            if error_message:
                update_data["error_message"] = error_message
            if error_details:
                update_data["error_details"] = error_details
            
            if self.use_redis and self.redis_client:
                # Update Redis hash
                redis_data = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) 
                             for k, v in update_data.items()}
                await self.redis_client.hset(f"{self.token_prefix}{token}", mapping=redis_data)
            else:
                # Update in-memory
                if token in self.in_memory_tokens:
                    self.in_memory_tokens[token].update(update_data)
            
            # Update stats
            if status == TranslationStatus.DONE:
                self.stats["translations_completed"] += 1
            elif status == TranslationStatus.ERROR:
                self.stats["translations_failed"] += 1
            elif status == TranslationStatus.TIMEOUT:
                self.stats["translations_timed_out"] += 1
            elif status == TranslationStatus.NEEDS_HUMAN:
                self.stats["translations_needs_human"] += 1
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update status for token {token}: {e}")
            return False
    
    async def pop_next(self) -> Optional[str]:
        """
        Pop next translation token from queue.
        
        Returns:
            Next token to process or None if queue empty
        """
        try:
            if self.use_redis and self.redis_client:
                # Blocking pop with short timeout
                result = await self.redis_client.blpop(self.queue_name, timeout=5)
                return result[1] if result else None
            else:
                # In-memory fallback with timeout
                try:
                    return await asyncio.wait_for(self.in_memory_queue.get(), timeout=5.0)
                except asyncio.TimeoutError:
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to pop from queue: {e}")
            return None
    
    async def cleanup_expired(self) -> int:
        """
        Clean up expired translation tokens.
        
        Returns:
            Number of tokens cleaned up
        """
        cleanup_count = 0
        cutoff_time = datetime.utcnow() - timedelta(seconds=self.timeout_seconds)
        
        try:
            if self.use_redis and self.redis_client:
                # Scan for expired tokens
                async for key in self.redis_client.scan_iter(match=f"{self.token_prefix}*"):
                    data = await self.redis_client.hgetall(key)
                    if data and data.get("status") in [TranslationStatus.QUEUED.value, TranslationStatus.PROCESSING.value]:
                        created_at = datetime.fromisoformat(data.get("created_at", ""))
                        if created_at < cutoff_time:
                            await self.update_status(
                                key.replace(self.token_prefix, ""),
                                TranslationStatus.TIMEOUT,
                                error_message="Translation timed out"
                            )
                            cleanup_count += 1
            else:
                # In-memory cleanup
                expired_tokens = []
                for token, data in self.in_memory_tokens.items():
                    if data.get("status") in [TranslationStatus.QUEUED.value, TranslationStatus.PROCESSING.value]:
                        created_at = datetime.fromisoformat(data.get("created_at", ""))
                        if created_at < cutoff_time:
                            expired_tokens.append(token)
                
                for token in expired_tokens:
                    await self.update_status(
                        token,
                        TranslationStatus.TIMEOUT,
                        error_message="Translation timed out"
                    )
                    cleanup_count += 1
            
            if cleanup_count > 0:
                logger.info(f"Cleaned up {cleanup_count} expired translation tokens")
            
            return cleanup_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup expired tokens: {e}")
            return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        return {
            **self.stats,
            "use_redis": self.use_redis,
            "queue_size": len(self.in_memory_tokens) if not self.use_redis else "unknown"
        }


class TranslationWorker:
    """
    Background worker for processing translation queue.
    
    Handles the actual LLM translation with comprehensive error handling.
    """
    
    def __init__(self, 
                 translation_queue: TranslationQueue,
                 llm_translator: LLMTranslator,
                 max_retries: int = 3,
                 retry_delay: float = 5.0):
        """
        Initialize translation worker.
        
        Args:
            translation_queue: Queue to process
            llm_translator: LLM translator instance
            max_retries: Maximum retries per translation
            retry_delay: Delay between retries in seconds
        """
        self.queue = translation_queue
        self.llm_translator = llm_translator
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        
        logger.info("Translation worker initialized")
    
    async def start(self):
        """Start the background worker."""
        if self._running:
            logger.warning("Translation worker already running")
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Translation worker started")
    
    async def stop(self):
        """Stop the background worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Translation worker stopped")
    
    async def _worker_loop(self):
        """Main worker loop."""
        while self._running:
            try:
                # Get next translation
                token = await self.queue.pop_next()
                if not token:
                    continue
                
                # Process translation
                await self._process_translation(token)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(self.retry_delay)
    
    async def _process_translation(self, token: str):
        """Process a single translation."""
        try:
            # Get translation data
            data = await self.queue.get_status(token)
            if not data:
                logger.error(f"Translation data not found for token: {token}")
                return
            
            # Update status to processing
            await self.queue.update_status(token, TranslationStatus.PROCESSING)
            
            text = data.get("text", "")
            retries = int(data.get("retries", 0))
            
            logger.info(f"Processing translation {token}, attempt {retries + 1}")
            
            try:
                # Attempt translation
                dsl = await self.llm_translator.translate_strict(text)
                
                # Validate DSL
                await self._validate_dsl(dsl)
                
                # Success
                await self.queue.update_status(
                    token,
                    TranslationStatus.DONE,
                    dsl=dsl
                )
                
                logger.info(f"Translation completed successfully: {token}")
                
            except NeedsHumanError as e:
                # Human intervention required
                await self.queue.update_status(
                    token,
                    TranslationStatus.NEEDS_HUMAN,
                    error_message=str(e),
                    error_details={"context": e.context}
                )
                
                logger.warning(f"Translation needs human intervention: {token}")
                
            except Exception as e:
                # Translation failed
                if retries < self.max_retries:
                    # Retry
                    await self._schedule_retry(token, retries + 1, str(e))
                else:
                    # Max retries exceeded
                    await self.queue.update_status(
                        token,
                        TranslationStatus.ERROR,
                        error_message=f"Translation failed after {self.max_retries} attempts: {str(e)}",
                        error_details={"retries": retries, "last_error": str(e)}
                    )
                    
                    logger.error(f"Translation failed permanently: {token} - {e}")
                
        except Exception as e:
            logger.error(f"Failed to process translation {token}: {e}")
    
    async def _validate_dsl(self, dsl: str):
        """Validate generated DSL."""
        try:
            parsed = yaml.safe_load(dsl)
            if not isinstance(parsed, dict):
                raise ValueError("DSL must be a YAML object")
            if "tasks" not in parsed:
                raise ValueError("DSL must contain 'tasks' field")
            if not isinstance(parsed["tasks"], list):
                raise ValueError("'tasks' must be a list")
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML: {e}")
    
    async def _schedule_retry(self, token: str, retry_count: int, error_message: str):
        """Schedule a retry for failed translation."""
        try:
            # Update retry count
            if self.queue.use_redis and self.queue.redis_client:
                await self.queue.redis_client.hset(
                    f"{self.queue.token_prefix}{token}",
                    "retries",
                    str(retry_count)
                )
                # Re-add to queue for retry
                await self.queue.redis_client.rpush(self.queue.queue_name, token)
            else:
                # In-memory retry
                if token in self.queue.in_memory_tokens:
                    self.queue.in_memory_tokens[token]["retries"] = retry_count
                await self.queue.in_memory_queue.put(token)
            
            # Reset status to queued
            await self.queue.update_status(token, TranslationStatus.QUEUED)
            
            logger.info(f"Scheduled retry {retry_count} for translation {token}")
            
        except Exception as e:
            logger.error(f"Failed to schedule retry for {token}: {e}") 