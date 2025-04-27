#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import logging
import argparse
import configparser
import signal

from twisted.internet import reactor
from twisted.internet.endpoints import TCP4ServerEndpoint

from bitcoin_rpc import BitcoinRPC
from stratum import StratumFactory
from simple_web_interface import setup_web_interface

def parse_args():
    parser = argparse.ArgumentParser(description='Bitcoin Solo Mining Pool')
    parser.add_argument('--address', dest='address', type=str, help='Bitcoin address for block rewards')
    parser.add_argument('--port', dest='port', type=int, default=3333, help='Port for Stratum server (default: 3333)')
    parser.add_argument('--host', dest='host', type=str, default='0.0.0.0', help='Interface to listen on (default: 0.0.0.0)')
    parser.add_argument('--difficulty', dest='difficulty', type=float, default=0.01, help='Initial mining difficulty (default: 0.01)')
    parser.add_argument('--coinbase-msg', dest='coinbase_msg', type=str, default='vibe coded pool', help='Coinbase message')
    parser.add_argument('--config', dest='config', type=str, default='config.ini', help='Path to config file (default: config.ini)')
    parser.add_argument('--verbose', dest='verbose', action='store_true', help='Enable verbose logging')
    parser.add_argument('--web', dest='web_stats', action='store_true', help='Enable web statistics on port 8080')
    parser.add_argument('--web-port', dest='web_port', type=int, default=8080, help='Port for web statistics (default: 8080)')
    return parser.parse_args()

def load_config(config_path):
    config = configparser.ConfigParser()
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    try:
        config.read(config_path)
        return config
    except configparser.Error as e:
        raise ValueError(f"Error parsing config file: {str(e)}")

def validate_address(bitcoin_rpc, address):
    """Validate the Bitcoin address"""
    if not address:
        return False
    
    try:
        result = bitcoin_rpc.validate_address(address)
        return result.get('isvalid', False)
    except Exception as e:
        logging.error(f"Error validating address: {str(e)}")
        return False

def main():
    args = parse_args()
    
    # Set up logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=log_level
    )
    
    # Load config
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        logging.error(str(e))
        return 1
    
    # Connect to Bitcoin Core
    try:
        logging.info("Connecting to Bitcoin node...")
        bitcoin_rpc = BitcoinRPC(args.config)
        
        # Test connection
        info = bitcoin_rpc.get_blockchain_info()
        logging.info(f"Connected to Bitcoin node, chain: {info.get('chain', 'unknown')}")
        
        # Get current block height
        height = info.get('blocks', 0)
        logging.info(f"Current block height: {height}")
    except Exception as e:
        logging.error(f"Failed to connect to Bitcoin node: {str(e)}")
        return 1
    
    # Get mining address from args or config
    pool_address = args.address
    if not pool_address and config.has_option('pool', 'address'):
        pool_address = config.get('pool', 'address')
    
    # Validate address
    if not validate_address(bitcoin_rpc, pool_address):
        logging.error(f"Invalid Bitcoin address: {pool_address}")
        return 1
    
    # Set up Stratum server
    try:
        # Get coinbase message
        coinbase_msg = args.coinbase_msg
        if not coinbase_msg and config.has_option('pool', 'coinbase_message'):
            coinbase_msg = config.get('pool', 'coinbase_message')
        
        # Get initial difficulty
        difficulty = args.difficulty
        if difficulty <= 0 and config.has_option('pool', 'difficulty'):
            difficulty = config.getfloat('pool', 'difficulty', fallback=0.01)
        
        # Create factory with the specified difficulty
        factory = StratumFactory(bitcoin_rpc, pool_address, initial_difficulty=difficulty)
        factory.coinbase_message = coinbase_msg.encode()
        
        # Set up the Stratum server
        port = args.port
        host = args.host
        endpoint = TCP4ServerEndpoint(reactor, port, interface=host)
        endpoint.listen(factory)
        
        logging.info(f"Solo mining pool started on {host}:{port}")
        logging.info(f"Mining rewards will be sent to: {pool_address}")
        logging.info(f"Coinbase message: {coinbase_msg}")
        logging.info(f"Initial difficulty: {difficulty}")
        logging.info("Press Ctrl+C to stop the pool")
        
        # Set up web statistics if enabled
        if args.web_stats:
            web_url = setup_web_interface(factory, port=args.web_port)
            logging.info(f"Web statistics available at {web_url}")
        
        # Set up signal handling for graceful shutdown
        def signal_handler(sig, frame):
            logging.info("Shutting down mining pool...")
            reactor.stop()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Start the event loop
        reactor.run()
        
        return 0
    except Exception as e:
        logging.error(f"Error starting mining pool: {str(e)}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
