#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import time
import logging
from twisted.web import server, resource
from twisted.internet import reactor
from datetime import datetime
from pool_stats import PoolStats
from simple_web_interface import PoolStatsPage, setup_web_interface

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MockFactory:
    """Mock factory for testing the dashboard"""
    
    def __init__(self):
        # Initialize statistics tracker
        self.stats = PoolStats()
        
        # Mock jobs
        self.jobs = {
            '1': {
                'height': 800123,
                'bits': 0x1d00ffff,
                'transactions': ['tx1', 'tx2', 'tx3']
            }
        }
        
        # Set the pool address (this would normally come from config.ini)
        self.pool_address = "1EXAMPLE000000000000000000000000XXX"
        
        # Add some mock data
        self._add_mock_data()
    
    def _add_mock_data(self):
        """Add mock data for testing"""
        # Clear any existing data
        self.stats.clients = {}
        
        # Add a mock client (only one)
        self.stats.add_client('192.168.1.100', 'miner1_abcd')
        
        # Add some shares
        self.stats.add_share('miner1_abcd', valid=True, difficulty=1)
        self.stats.add_share('miner1_abcd', valid=True, difficulty=1)
        self.stats.add_share('miner1_abcd', valid=True, difficulty=1)
        
        # Record mock stratum methods
        self.stats.record_pool_to_miner_method('mining.notify')
        self.stats.record_miner_to_pool_method('mining.submit')

def main():
    """Main function to run the test dashboard"""
    try:
        # Create mock factory
        factory = MockFactory()
        
        # Set up web interface
        web_url = setup_web_interface(factory, port=8080)
        
        logger.info(f"Web interface started at {web_url}")
        logger.info(f"Using pool address: {factory.pool_address}")
        logger.info("Press Ctrl+C to exit")
        
        # Run the reactor
        reactor.run()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        reactor.stop()
    except Exception as e:
        logger.error(f"Error: {str(e)}")

if __name__ == "__main__":
    main()
