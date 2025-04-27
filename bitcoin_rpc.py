#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import configparser
import logging
import time
import socket
from bitcoinrpc.authproxy import AuthServiceProxy, JSONRPCException

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class BitcoinRPC:
    """
    Bitcoin RPC client to interact with a local Bitcoin node
    """
    
    def __init__(self, config_file='config.ini', max_retries=3, retry_delay=2):
        """Initialize the Bitcoin RPC client with configuration"""
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        
        self.host = self.config.get('bitcoind', 'rpchost')
        self.port = self.config.getint('bitcoind', 'rpcport')
        self.user = self.config.get('bitcoind', 'rpcuser')
        self.password = self.config.get('bitcoind', 'rpcpassword')
        
        self.rpc_url = f'http://{self.user}:{self.password}@{self.host}:{self.port}'
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.rpc_connection = None
        
        # Create RPC connection
        self._connect()
    
    def _connect(self):
        """Establish connection to the Bitcoin node"""
        retries = 0
        last_error = None
        
        while retries < self.max_retries:
            try:
                self.rpc_connection = AuthServiceProxy(self.rpc_url, timeout=30)
                # Test connection
                self.get_blockchain_info()
                logger.info(f"Successfully connected to Bitcoin node at {self.host}:{self.port}")
                return
            except Exception as e:
                last_error = e
                retries += 1
                logger.warning(f"Connection attempt {retries} failed: {str(e)}")
                if retries < self.max_retries:
                    time.sleep(self.retry_delay)
        
        logger.error(f"Failed to connect to Bitcoin node after {self.max_retries} attempts: {str(last_error)}")
        raise last_error
    
    def _call_with_retry(self, method, *args):
        """Make an RPC call with retry logic"""
        retries = 0
        last_error = None
        
        while retries < self.max_retries:
            try:
                if self.rpc_connection is None:
                    self._connect()
                return method(*args)
            except (JSONRPCException, socket.error, ConnectionRefusedError, BrokenPipeError) as e:
                last_error = e
                retries += 1
                logger.warning(f"RPC call attempt {retries} failed: {str(e)}")
                
                # For connection errors, try to reconnect
                if isinstance(e, (socket.error, ConnectionRefusedError, BrokenPipeError)):
                    self.rpc_connection = None
                    self._connect()
                
                if retries < self.max_retries:
                    time.sleep(self.retry_delay)
        
        logger.error(f"RPC call failed after {self.max_retries} attempts: {str(last_error)}")
        raise last_error
    
    def get_blockchain_info(self):
        """Get information about the blockchain"""
        try:
            return self.rpc_connection.getblockchaininfo()
        except Exception as e:
            logger.error(f"RPC Error: {str(e)}")
            raise
    
    def get_mining_info(self):
        """Get mining-related information"""
        return self._call_with_retry(self.rpc_connection.getmininginfo)
    
    def get_network_hashps(self):
        """Get the estimated network hashes per second"""
        return self._call_with_retry(self.rpc_connection.getnetworkhashps)
    
    def get_block_template(self, capabilities=None):
        """
        Get block template for mining
        
        capabilities: List of strings
        """
        params = {'rules': ['segwit']}
        if capabilities:
            params['capabilities'] = capabilities
        
        def call_method():
            return self.rpc_connection.getblocktemplate(params)
        
        return self._call_with_retry(call_method)
    
    def submit_block(self, hex_data):
        """
        Submit a new block to the network
        
        hex_data: Block data in hex
        """
        def call_method():
            return self.rpc_connection.submitblock(hex_data)
        
        return self._call_with_retry(call_method)
    
    def validate_address(self, address):
        """Validate a bitcoin address"""
        def call_method():
            return self.rpc_connection.validateaddress(address)
        
        return self._call_with_retry(call_method)


if __name__ == "__main__":
    # Simple test
    try:
        rpc = BitcoinRPC()
        info = rpc.get_blockchain_info()
        import json
        print(json.dumps(info, indent=4))
    except Exception as e:
        print(f"Error: {str(e)}")
