#Actively in Use
"""
Guards module for concurrency control and rate limiting.

Provides ConcurrencyGuard and RateLimiter classes for system protection.
"""

import asyncio
import time
import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class ConcurrencyGuard:
    """Guard to control concurrent workflow execution."""
    
    def __init__(self, max_concurrent: int = 1):
        """
        Initialize concurrency guard.
        
        Args:
            max_concurrent: Maximum number of concurrent workflows allowed
        """
        self.max_concurrent = max_concurrent
        self.current_count = 0
        self.lock = asyncio.Lock()
        self.waiting_queue = asyncio.Queue()
        
    async def acquire(self) -> bool:
        """
        Acquire a concurrency slot.
        
        Returns:
            True if slot acquired, False if at limit
        """
        async with self.lock:
            if self.current_count < self.max_concurrent:
                self.current_count += 1
                logger.debug(f"Concurrency slot acquired. Current: {self.current_count}/{self.max_concurrent}")
                return True
            return False
    
    async def release(self):
        """Release a concurrency slot."""
        async with self.lock:
            if self.current_count > 0:
                self.current_count -= 1
                logger.debug(f"Concurrency slot released. Current: {self.current_count}/{self.max_concurrent}")
    
    async def wait_for_slot(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for a concurrency slot to become available.
        
        Args:
            timeout: Maximum time to wait in seconds
            
        Returns:
            True if slot acquired, False if timeout
        """
        try:
            await asyncio.wait_for(self.waiting_queue.get(), timeout=timeout)
            return await self.acquire()
        except asyncio.TimeoutError:
            return False
    
    def get_stats(self) -> Dict[str, int]:
        """Get concurrency statistics."""
        return {
            "current_count": self.current_count,
            "max_concurrent": self.max_concurrent,
            "available_slots": self.max_concurrent - self.current_count,
            "queue_size": self.waiting_queue.qsize()
        }
    
    def allow(self) -> bool:
        """
        Simple synchronous check if concurrency allows new workflow.
        
        Returns:
            True if new workflow can be started
        """
        return self.current_count < self.max_concurrent

class TokenBucket:
    """Token bucket for rate limiting."""
    
    def __init__(self, capacity: int, refill_rate: float):
        """
        Initialize token bucket.
        
        Args:
            capacity: Maximum number of tokens
            refill_rate: Tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
    
    def _refill(self):
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Try to consume tokens.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens consumed, False if insufficient
        """
        self._refill()
        
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False
    
    def get_wait_time(self, tokens: int = 1) -> float:
        """
        Get time to wait for tokens to be available.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Wait time in seconds
        """
        self._refill()
        
        if self.tokens >= tokens:
            return 0.0
        
        needed_tokens = tokens - self.tokens
        return needed_tokens / self.refill_rate

class RateLimiter:
    """Advanced rate limiter with multiple strategies."""
    
    def __init__(self, config: Dict[str, Dict[str, int]]):
        """
        Initialize rate limiter.
        
        Args:
            config: Rate limiting configuration
                   {
                       "per_minute": {"requests": 60, "window": 60},
                       "per_hour": {"requests": 1000, "window": 3600},
                       "burst": {"requests": 10, "window": 1}
                   }
        """
        self.config = config
        self.client_buckets: Dict[str, Dict[str, TokenBucket]] = defaultdict(dict)
        self.client_windows: Dict[str, Dict[str, deque]] = defaultdict(lambda: defaultdict(deque))
    
    def _get_or_create_bucket(self, client_id: str, limit_name: str) -> TokenBucket:
        """Get or create token bucket for client and limit."""
        if limit_name not in self.client_buckets[client_id]:
            limit_config = self.config[limit_name]
            capacity = limit_config["requests"]
            refill_rate = capacity / limit_config["window"]
            
            self.client_buckets[client_id][limit_name] = TokenBucket(capacity, refill_rate)
        
        return self.client_buckets[client_id][limit_name]
    
    def _check_sliding_window(self, client_id: str, limit_name: str) -> bool:
        """Check sliding window rate limit."""
        now = time.time()
        limit_config = self.config[limit_name]
        window_size = limit_config["window"]
        max_requests = limit_config["requests"]
        
        # Get client's request history for this limit
        requests = self.client_windows[client_id][limit_name]
        
        # Remove old requests outside the window
        cutoff_time = now - window_size
        while requests and requests[0] < cutoff_time:
            requests.popleft()
        
        # Check if under limit
        if len(requests) < max_requests:
            requests.append(now)
            return True
        
        return False
    
    def check_rate_limit(self, client_id: str, tokens: int = 1) -> Tuple[bool, Optional[str], float]:
        """
        Check if request is allowed under rate limits.
        
        Args:
            client_id: Client identifier
            tokens: Number of tokens to consume
            
        Returns:
            Tuple of (allowed, reason, wait_time)
        """
        max_wait_time = 0.0
        
        for limit_name, limit_config in self.config.items():
            if limit_config.get("strategy") == "sliding_window":
                allowed = self._check_sliding_window(client_id, limit_name)
                if not allowed:
                    # Calculate wait time for sliding window
                    requests = self.client_windows[client_id][limit_name]
                    if requests:
                        oldest_request = requests[0]
                        wait_time = limit_config["window"] - (time.time() - oldest_request)
                        max_wait_time = max(max_wait_time, wait_time)
            else:
                # Token bucket strategy (default)
                bucket = self._get_or_create_bucket(client_id, limit_name)
                if not bucket.consume(tokens):
                    wait_time = bucket.get_wait_time(tokens)
                    max_wait_time = max(max_wait_time, wait_time)
                    return False, f"Rate limit exceeded: {limit_name}", wait_time
        
        if max_wait_time > 0:
            return False, "Rate limit exceeded", max_wait_time
        
        return True, None, 0.0
    
    def get_client_stats(self, client_id: str) -> Dict[str, Dict[str, float]]:
        """Get rate limiting statistics for a client."""
        stats = {}
        
        for limit_name in self.config:
            if limit_name in self.client_buckets.get(client_id, {}):
                bucket = self.client_buckets[client_id][limit_name]
                bucket._refill()  # Update token count
                
                stats[limit_name] = {
                    "tokens_available": bucket.tokens,
                    "capacity": bucket.capacity,
                    "refill_rate": bucket.refill_rate,
                    "utilization": (bucket.capacity - bucket.tokens) / bucket.capacity
                }
            
            # Add sliding window stats if applicable
            if self.config[limit_name].get("strategy") == "sliding_window":
                requests = self.client_windows[client_id][limit_name]
                window_size = self.config[limit_name]["window"]
                max_requests = self.config[limit_name]["requests"]
                
                # Clean old requests
                now = time.time()
                cutoff_time = now - window_size
                while requests and requests[0] < cutoff_time:
                    requests.popleft()
                
                if limit_name not in stats:
                    stats[limit_name] = {}
                
                stats[limit_name].update({
                    "requests_in_window": len(requests),
                    "max_requests": max_requests,
                    "window_utilization": len(requests) / max_requests
                })
        
        return stats
    
    def reset_client(self, client_id: str):
        """Reset rate limiting data for a client."""
        if client_id in self.client_buckets:
            del self.client_buckets[client_id]
        if client_id in self.client_windows:
            del self.client_windows[client_id]
        
        logger.info(f"Reset rate limiting data for client: {client_id}")
    
    def cleanup_expired_data(self):
        """Clean up expired rate limiting data."""
        now = time.time()
        clients_to_remove = []
        
        for client_id, windows in self.client_windows.items():
            for limit_name, requests in windows.items():
                window_size = self.config[limit_name]["window"]
                cutoff_time = now - window_size * 2  # Keep some buffer
                
                while requests and requests[0] < cutoff_time:
                    requests.popleft()
            
            # Remove clients with no recent activity
            if all(len(requests) == 0 for requests in windows.values()):
                clients_to_remove.append(client_id)
        
        for client_id in clients_to_remove:
            if client_id in self.client_buckets:
                del self.client_buckets[client_id]
            if client_id in self.client_windows:
                del self.client_windows[client_id]
        
        if clients_to_remove:
            logger.info(f"Cleaned up rate limiting data for {len(clients_to_remove)} inactive clients")

class TokenRateLimiter:
    """Simplified token-based rate limiter (compatibility with pseudocode)."""
    
    def __init__(self, rate_limits: Dict[str, int]):
        """
        Initialize token rate limiter.
        
        Args:
            rate_limits: Dictionary of limit_name -> requests_per_minute
        """
        config = {}
        for limit_name, rpm in rate_limits.items():
            config[limit_name] = {
                "requests": rpm,
                "window": 60  # 1 minute
            }
        
        self.rate_limiter = RateLimiter(config)
    
    def check(self, client_id: str) -> bool:
        """
        Check if client is within rate limits.
        
        Args:
            client_id: Client identifier
            
        Returns:
            True if allowed, False if rate limited
        """
        allowed, reason, wait_time = self.rate_limiter.check_rate_limit(client_id)
        
        if not allowed:
            logger.warning(f"Rate limit exceeded for client {client_id}: {reason}, wait {wait_time:.2f}s")
        
        return allowed 