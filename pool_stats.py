#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import threading
import logging
from collections import deque

logger = logging.getLogger(__name__)

class PoolStats:
    """
    Track and manage statistics for the mining pool
    """
    
    def __init__(self, window_size=600):  # 10 minute window by default
        self.shares = {
            'valid': 0,
            'invalid': 0,
            'stale': 0
        }
        self.blocks_found = 0
        self.start_time = time.time()
        self.last_share_time = 0
        self.window_size = window_size
        self.share_times = deque(maxlen=1000)  # Store timestamps of last 1000 shares
        self.hashrate_history = deque(maxlen=100)  # Store last 100 hashrate calculations
        self.clients = {}
        self.lock = threading.RLock()
        
        # Start hashrate calculation thread
        self.update_thread = threading.Thread(target=self._update_hashrate, daemon=True)
        self.update_thread.start()
    
    def add_share(self, worker_name, valid=True, stale=False, difficulty=1):
        """Add a share to the statistics"""
        with self.lock:
            current_time = time.time()
            self.last_share_time = current_time
            self.share_times.append((current_time, difficulty))
            
            if valid and not stale:
                self.shares['valid'] += 1
                # Update per-worker stats
                if worker_name not in self.clients:
                    self.clients[worker_name] = {
                        'shares': {'valid': 0, 'invalid': 0, 'stale': 0},
                        'last_share_time': current_time,
                        'connection_time': current_time,
                        'difficulty': difficulty,
                        'active': True
                    }
                self.clients[worker_name]['shares']['valid'] += 1
                self.clients[worker_name]['last_share_time'] = current_time
                self.clients[worker_name]['difficulty'] = difficulty
            elif stale:
                self.shares['stale'] += 1
                if worker_name in self.clients:
                    self.clients[worker_name]['shares']['stale'] += 1
            else:
                self.shares['invalid'] += 1
                if worker_name in self.clients:
                    self.clients[worker_name]['shares']['invalid'] += 1
    
    def add_block(self, worker_name, height, hash):
        """Record a found block"""
        with self.lock:
            self.blocks_found += 1
            logger.info(f"BLOCK FOUND by {worker_name} at height {height}! Hash: {hash}")
            if worker_name in self.clients:
                if 'blocks' not in self.clients[worker_name]:
                    self.clients[worker_name]['blocks'] = []
                self.clients[worker_name]['blocks'].append({
                    'height': height,
                    'hash': hash,
                    'time': time.time()
                })
    
    def add_client(self, client_id, worker_name=None):
        """Add a new client to statistics"""
        with self.lock:
            key = worker_name or client_id
            if key not in self.clients:
                self.clients[key] = {
                    'shares': {'valid': 0, 'invalid': 0, 'stale': 0},
                    'last_share_time': 0,
                    'connection_time': time.time(),
                    'difficulty': 1,
                    'active': True,
                    'client_ids': [client_id]
                }
            else:
                # If client exists but was marked inactive, reactivate it
                self.clients[key]['active'] = True
                # Add client_id to the list if not already present
                if client_id not in self.clients[key].get('client_ids', []):
                    if 'client_ids' not in self.clients[key]:
                        self.clients[key]['client_ids'] = []
                    self.clients[key]['client_ids'].append(client_id)
    
    def remove_client(self, worker_name):
        """Remove a client from active statistics"""
        with self.lock:
            if worker_name in self.clients:
                # We don't actually delete the client to keep historical data
                self.clients[worker_name]['active'] = False
    
    def calculate_hashrate(self, window_seconds=300):
        """Calculate the current hashrate based on shares in the last window_seconds"""
        with self.lock:
            if not self.share_times:
                return 0
            
            current_time = time.time()
            # Filter shares within the window
            recent_shares = [(t, d) for t, d in self.share_times 
                             if current_time - t <= window_seconds]
            
            if not recent_shares:
                return 0
            
            # Calculate hashrate: shares * difficulty * 2^32 / window_seconds
            total_difficulty = sum(d for _, d in recent_shares)
            
            # Avoid division by zero
            if window_seconds == 0:
                return 0
                
            # Each share at difficulty 1 represents 2^32 hashes
            hashrate = (total_difficulty * 4294967296) / window_seconds
            return hashrate
    
    def get_worker_hashrate(self, worker_name, window_seconds=300):
        """Calculate hashrate for a specific worker"""
        with self.lock:
            if worker_name not in self.clients:
                return 0
            
            # Simple estimation based on shares and difficulty
            shares = self.clients[worker_name]['shares']['valid']
            difficulty = self.clients[worker_name]['difficulty']
            
            # Calculate time window
            current_time = time.time()
            connection_time = self.clients[worker_name]['connection_time']
            elapsed = min(current_time - connection_time, window_seconds)
            
            if elapsed == 0 or shares == 0:
                return 0
                
            # Each share at difficulty 1 represents 2^32 hashes
            hashrate = (shares * difficulty * 4294967296) / elapsed
            return hashrate
    
    def _update_hashrate(self):
        """Background thread to periodically update hashrate history"""
        while True:
            try:
                hashrate = self.calculate_hashrate()
                with self.lock:
                    self.hashrate_history.append((time.time(), hashrate))
                time.sleep(60)  # Update every minute
            except Exception as e:
                logger.error(f"Error updating hashrate: {str(e)}")
                time.sleep(60)
    
    def get_stats(self):
        """Get a dictionary of all statistics"""
        with self.lock:
            uptime = time.time() - self.start_time
            
            stats = {
                'uptime': uptime,
                'uptime_human': self._format_time(uptime),
                'shares': dict(self.shares),
                'blocks_found': self.blocks_found,
                'hashrate': self.calculate_hashrate(),
                'hashrate_human': self._format_hashrate(self.calculate_hashrate()),
                'clients': len([c for c in self.clients.values() if c.get('active', True)]),
                'total_clients': len(self.clients)
            }
            
            return stats
    
    def get_worker_stats(self):
        """Get statistics for all workers"""
        with self.lock:
            worker_stats = {}
            for worker_name, data in self.clients.items():
                if not data.get('active', True):
                    continue
                    
                hashrate = self.get_worker_hashrate(worker_name)
                worker_stats[worker_name] = {
                    'shares': dict(data['shares']),
                    'hashrate': hashrate,
                    'hashrate_human': self._format_hashrate(hashrate),
                    'last_share_time': data['last_share_time'],
                    'last_share_ago': self._format_time(time.time() - data['last_share_time']) if data['last_share_time'] > 0 else 'Never',
                    'difficulty': data['difficulty']
                }
            
            return worker_stats
    
    def get_pool_stats(self):
        """Get pool statistics for the web interface"""
        with self.lock:
            current_time = time.time()
            
            # Calculate total shares
            total_shares = self.shares['valid'] + self.shares['invalid'] + self.shares['stale']
            
            # Get current hashrate
            hashrate = self.calculate_hashrate()
            
            # Count active miners - only count workers, not connections
            active_miners = len([name for name, data in self.clients.items() 
                               if data.get('active', True) and not name.startswith('192.168.')])
            
            return {
                'hashrate': hashrate,
                'total_shares': total_shares,
                'valid_shares': self.shares['valid'],
                'invalid_shares': self.shares['invalid'],
                'blocks_found': self.blocks_found,
                'connected_miners': active_miners,
                'uptime': current_time - self.start_time
            }
    
    @staticmethod
    def _format_hashrate(hashrate):
        """Format hashrate to human-readable string"""
        if hashrate < 1000:
            return f"{hashrate:.2f} H/s"
        elif hashrate < 1000000:
            return f"{hashrate/1000:.2f} KH/s"
        elif hashrate < 1000000000:
            return f"{hashrate/1000000:.2f} MH/s"
        elif hashrate < 1000000000000:
            return f"{hashrate/1000000000:.2f} GH/s"
        else:
            return f"{hashrate/1000000000000:.2f} TH/s"
    
    @staticmethod
    def _format_time(seconds):
        """Format time duration to human-readable string"""
        if seconds < 60:
            return f"{int(seconds)} seconds"
        elif seconds < 3600:
            return f"{int(seconds/60)} minutes, {int(seconds%60)} seconds"
        elif seconds < 86400:
            return f"{int(seconds/3600)} hours, {int((seconds%3600)/60)} minutes"
        else:
            return f"{int(seconds/86400)} days, {int((seconds%86400)/3600)} hours"
