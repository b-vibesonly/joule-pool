#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import logging
import threading
from collections import defaultdict, deque

logger = logging.getLogger(__name__)

class DifficultyAdjuster:
    """
    Dynamically adjust mining difficulty for each client
    to optimize share submission rates
    """
    
    def __init__(self, initial_difficulty=1, target_share_time=10, 
                 min_difficulty=0.01, max_difficulty=1000000,
                 variance_percent=30, adjustment_factor=2):
        """
        Initialize the difficulty adjuster
        
        initial_difficulty: Starting difficulty for new clients
        target_share_time: Target seconds between shares (10-15 is typical)
        min_difficulty: Minimum allowed difficulty
        max_difficulty: Maximum allowed difficulty
        variance_percent: Allowed variance in share time before adjusting
        adjustment_factor: How aggressively to adjust difficulty
        """
        self.initial_difficulty = initial_difficulty
        self.target_share_time = target_share_time
        self.min_difficulty = min_difficulty
        self.max_difficulty = max_difficulty
        self.variance_percent = variance_percent
        self.adjustment_factor = adjustment_factor
        
        # Track share times per client
        self.client_share_times = defaultdict(lambda: deque(maxlen=10))
        self.client_difficulties = {}
        self.lock = threading.RLock()
    
    def get_difficulty(self, client_id):
        """Get the current difficulty for a client"""
        with self.lock:
            return self.client_difficulties.get(client_id, self.initial_difficulty)
    
    def record_share(self, client_id, timestamp=None):
        """Record a share submission time for a client"""
        if timestamp is None:
            timestamp = time.time()
            
        with self.lock:
            # Initialize client if not seen before
            if client_id not in self.client_difficulties:
                self.client_difficulties[client_id] = self.initial_difficulty
                
            # Record share time
            share_times = self.client_share_times[client_id]
            if share_times:
                # Calculate time since last share
                time_since_last = timestamp - share_times[-1]
                share_times.append(timestamp)
                
                # Check if we need to adjust difficulty
                return self._check_adjust_difficulty(client_id, time_since_last)
            else:
                # First share, just record the time
                share_times.append(timestamp)
                return False, self.client_difficulties[client_id]
    
    def _check_adjust_difficulty(self, client_id, time_since_last):
        """Check if difficulty needs adjustment and adjust if necessary"""
        current_diff = self.client_difficulties[client_id]
        
        # Calculate variance thresholds
        variance = self.target_share_time * (self.variance_percent / 100)
        lower_bound = self.target_share_time - variance
        upper_bound = self.target_share_time + variance
        
        # Only adjust if outside variance bounds
        if time_since_last < lower_bound:
            # Shares coming too fast, increase difficulty
            new_diff = min(
                current_diff * self.adjustment_factor,
                self.max_difficulty
            )
            if new_diff != current_diff:
                logger.debug(f"Increasing difficulty for {client_id} from {current_diff} to {new_diff}")
                self.client_difficulties[client_id] = new_diff
                return True, new_diff
                
        elif time_since_last > upper_bound:
            # Shares coming too slow, decrease difficulty
            new_diff = max(
                current_diff / self.adjustment_factor,
                self.min_difficulty
            )
            if new_diff != current_diff:
                logger.debug(f"Decreasing difficulty for {client_id} from {current_diff} to {new_diff}")
                self.client_difficulties[client_id] = new_diff
                return True, new_diff
        
        # No adjustment needed
        return False, current_diff
    
    def suggest_difficulty(self, client_id, suggested_diff):
        """Handle a difficulty suggestion from a client"""
        with self.lock:
            # Cap the suggestion within our bounds
            capped_diff = max(min(suggested_diff, self.max_difficulty), self.min_difficulty)
            
            # Always use the suggestion, even for existing clients
            old_diff = self.client_difficulties.get(client_id, self.initial_difficulty)
            self.client_difficulties[client_id] = capped_diff
            logger.info(f"Using suggested difficulty {capped_diff} for client {client_id}")
            
            # Return whether the difficulty changed and the new difficulty
            return old_diff != capped_diff, capped_diff
