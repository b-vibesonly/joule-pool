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
                 variance_percent=30, adjustment_factor=2,
                 no_share_timeout=30,  
                 inactive_adjustment_factor=3):  
        """
        Initialize the difficulty adjuster
        
        initial_difficulty: Starting difficulty for new clients
        target_share_time: Target seconds between shares (10-15 is typical)
        min_difficulty: Minimum allowed difficulty
        max_difficulty: Maximum allowed difficulty
        variance_percent: Allowed variance in share time before adjusting
        adjustment_factor: How aggressively to adjust difficulty
        no_share_timeout: Lower difficulty if no share in this many seconds
        inactive_adjustment_factor: How aggressively to adjust difficulty for inactive miners
        """
        self.initial_difficulty = initial_difficulty
        self.target_share_time = target_share_time
        self.min_difficulty = min_difficulty
        self.max_difficulty = max_difficulty
        self.variance_percent = variance_percent
        self.adjustment_factor = adjustment_factor
        self.no_share_timeout = no_share_timeout
        self.inactive_adjustment_factor = inactive_adjustment_factor
        
        # Track share times per client
        self.client_share_times = defaultdict(lambda: deque(maxlen=10))
        self.client_difficulties = {}
        self.inactive_count = defaultdict(int)  
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
                
                # Only consider increasing difficulty if share came in within 5 seconds
                if time_since_last <= 5:
                    # Check if we need to adjust difficulty
                    return self._check_adjust_difficulty(client_id, time_since_last)
                else:
                    # If share took longer than 5 seconds, don't adjust difficulty
                    return False, self.client_difficulties[client_id]
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
        
        # Only increase difficulty if shares are coming very fast AND time since last share is not too high
        if time_since_last < lower_bound and time_since_last <= 10:
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
    
    def check_inactive_clients(self):
        """
        Check for clients that haven't submitted shares in a while
        and lower their difficulty if needed
        """
        current_time = time.time()
        adjusted_clients = []
        
        with self.lock:
            for client_id, share_times in self.client_share_times.items():
                if not share_times:
                    continue
                    
                last_share_time = share_times[-1]
                time_since_last = current_time - last_share_time
                
                # If no share in the timeout period, halve the difficulty
                if time_since_last > self.no_share_timeout:
                    current_diff = self.client_difficulties[client_id]
                    
                    # Only lower if above minimum
                    if current_diff > self.min_difficulty:
                        # Directly halve the difficulty (more aggressive than before)
                        new_diff = max(
                            current_diff / 2,  # Halve the difficulty
                            self.min_difficulty
                        )
                        
                        logger.info(f"Client {client_id} inactive for {time_since_last:.1f}s. "
                                   f"Halving difficulty from {current_diff} to {new_diff}")
                        
                        self.client_difficulties[client_id] = new_diff
                        adjusted_clients.append((client_id, new_diff))
                else:
                    # Reset inactive count if client has submitted a share within timeout
                    if client_id in self.inactive_count and self.inactive_count[client_id] > 0:
                        logger.info(f"Client {client_id} is active again, resetting inactive count")
                        self.inactive_count[client_id] = 0
        
        return adjusted_clients
