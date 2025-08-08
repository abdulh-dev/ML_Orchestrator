#Actively in Use
"""
Cache client for the Master Orchestrator.

Provides Redis-based caching with fallback to in-memory caching.
"""

import json
import hashlib
import logging
from typing import Any, Optional, Dict
from datetime import datetime, timedelta
import asyncio

try:
    import aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)

class CacheClient:
    """Cache client with Redis backend and in-memory fallback."""
    
    def __init__(self, 
                 redis_url: str = "redis://localhost:6379",
                 namespace: str = "deepline",
                 default_ttl: int = 3600,
                 max_memory_items: int = 1000):
        """
        Initialize cache client.
        
        Args:
            redis_url: Redis connection URL
            namespace: Cache namespace for key prefixing
            default_ttl: Default time-to-live in seconds
            max_memory_items: Maximum items in memory cache (fallback)
        """
        self.redis_url = redis_url
        self.namespace = namespace
        self.default_ttl = default_ttl
        self.max_memory_items = max_memory_items
        
        # Redis connection
        self.redis = None
        self.redis_available = False
        
        # In-memory fallback cache
        self.memory_cache: Dict[str, tuple] = {}  # key -> (value, expires_at)
        
        # Initialize Redis connection
        asyncio.create_task(self._init_redis())
    
    async def _init_redis(self):
        """Initialize Redis connection."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis not available, using in-memory cache only")
            return
        
        try:
            self.redis = await aioredis.from_url(self.redis_url)
            await self.redis.ping()
            self.redis_available = True
            logger.info("Redis cache initialized successfully")
        except Exception as e:
            logger.warning(f"Failed to connect to Redis: {e}. Using in-memory cache.")
            self.redis_available = False
    
    def _make_key(self, key: str) -> str:
        """Create namespaced cache key."""
        return f"{self.namespace}:{key}"
    
    def _hash_key(self, obj: Any) -> str:
        """Create hash key from object."""
        if isinstance(obj, (str, int, float, bool)):
            content = str(obj)
        else:
            content = json.dumps(obj, sort_keys=True, default=str)
        
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        cache_key = self._make_key(key)
        
        # Try Redis first
        if self.redis_available and self.redis:
            try:
                value = await self.redis.get(cache_key)
                if value:
                    return json.loads(value)
            except Exception as e:
                logger.warning(f"Redis get error: {e}")
        
        # Fallback to memory cache
        if cache_key in self.memory_cache:
            value, expires_at = self.memory_cache[cache_key]
            if datetime.now() < expires_at:
                return value
            else:
                # Remove expired item
                del self.memory_cache[cache_key]
        
        return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._make_key(key)
        ttl = ttl or self.default_ttl
        
        try:
            serialized_value = json.dumps(value, default=str)
        except (TypeError, ValueError) as e:
            logger.warning(f"Failed to serialize value for caching: {e}")
            return False
        
        # Try Redis first
        if self.redis_available and self.redis:
            try:
                await self.redis.setex(cache_key, ttl, serialized_value)
                return True
            except Exception as e:
                logger.warning(f"Redis set error: {e}")
        
        # Fallback to memory cache
        expires_at = datetime.now() + timedelta(seconds=ttl)
        
        # Remove oldest items if cache is full
        if len(self.memory_cache) >= self.max_memory_items:
            oldest_key = min(self.memory_cache.keys(), 
                           key=lambda k: self.memory_cache[k][1])
            del self.memory_cache[oldest_key]
        
        self.memory_cache[cache_key] = (value, expires_at)
        return True
    
    async def delete(self, key: str) -> bool:
        """
        Delete value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if successful, False otherwise
        """
        cache_key = self._make_key(key)
        
        success = False
        
        # Try Redis first
        if self.redis_available and self.redis:
            try:
                await self.redis.delete(cache_key)
                success = True
            except Exception as e:
                logger.warning(f"Redis delete error: {e}")
        
        # Remove from memory cache
        if cache_key in self.memory_cache:
            del self.memory_cache[cache_key]
            success = True
        
        return success
    
    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key exists and not expired
        """
        value = await self.get(key)
        return value is not None
    
    async def clear_namespace(self) -> int:
        """
        Clear all keys in the current namespace.
        
        Returns:
            Number of keys cleared
        """
        cleared = 0
        
        # Clear Redis namespace
        if self.redis_available and self.redis:
            try:
                pattern = f"{self.namespace}:*"
                async for key in self.redis.scan_iter(match=pattern):
                    await self.redis.delete(key)
                    cleared += 1
            except Exception as e:
                logger.warning(f"Redis clear error: {e}")
        
        # Clear memory cache namespace
        namespace_prefix = f"{self.namespace}:"
        memory_keys = [k for k in self.memory_cache.keys() 
                      if k.startswith(namespace_prefix)]
        
        for key in memory_keys:
            del self.memory_cache[key]
            cleared += 1
        
        return cleared
    
    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        stats = {
            "redis_available": self.redis_available,
            "memory_cache_size": len(self.memory_cache),
            "max_memory_items": self.max_memory_items,
            "namespace": self.namespace
        }
        
        if self.redis_available and self.redis:
            try:
                info = await self.redis.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "unknown")
            except Exception as e:
                logger.warning(f"Failed to get Redis stats: {e}")
        
        return stats
    
    async def health_check(self) -> bool:
        """
        Perform health check on cache.
        
        Returns:
            True if cache is healthy
        """
        test_key = "health_check"
        test_value = {"timestamp": datetime.now().isoformat()}
        
        try:
            # Test set/get cycle
            await self.set(test_key, test_value, ttl=60)
            retrieved = await self.get(test_key)
            
            if retrieved and retrieved.get("timestamp") == test_value["timestamp"]:
                await self.delete(test_key)
                return True
        except Exception as e:
            logger.warning(f"Cache health check failed: {e}")
        
        return False 