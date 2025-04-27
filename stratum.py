#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import hashlib
import binascii
import struct
import logging
import random
import traceback
import uuid
from twisted.internet import reactor, defer
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.endpoints import TCP4ServerEndpoint

from pool_stats import PoolStats
from difficulty_adjuster import DifficultyAdjuster

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class StratumProtocol(Protocol):
    """Stratum protocol implementation"""
    
    def __init__(self):
        """Initialize the protocol"""
        self.buffer = b''
        self.factory = None
        self.client_id = None
        self.authorized = False
        self.worker_name = None
        self.difficulty = 1
        self.subscription_id = None
        self.extranonce1 = None
        self.supported_versions = ["1.0", "2.0"]
        self.supported_extensions = {}
        
    def connectionMade(self):
        """Called when a connection is made"""
        peer = self.transport.getPeer()
        self.client_id = f"{peer.host}:{peer.port}"
        logger.info(f"New connection from {self.client_id}")
        self.extranonce1 = self.factory.get_new_extranonce1()
        
    def connectionLost(self, reason):
        """Called when the connection is lost"""
        logger.info(f"Connection lost from {self.client_id}: {reason.getErrorMessage()}")
        
        # Remove client from factory
        self.factory.remove_client(self)
        
        # Remove from statistics
        if self.worker_name:
            self.factory.stats.remove_client(self.worker_name)
        
    def dataReceived(self, data):
        """Process data received from the client"""
        self.buffer += data
        
        while b'\n' in self.buffer:
            line, self.buffer = self.buffer.split(b'\n', 1)
            try:
                line = line.strip()
                if line:
                    message = json.loads(line.decode('utf-8'))
                    self.handle_message(message)
            except json.JSONDecodeError:
                logger.error(f"Invalid JSON from {self.client_id}: {line}")
            except Exception as e:
                logger.error(f"Error processing message from {self.client_id}: {str(e)}")
                logger.debug(traceback.format_exc())
    
    def handle_message(self, message):
        """Handle a JSON-RPC message from the client"""
        if 'method' not in message:
            self.send_error(message.get('id', 0), -32600, "No method specified")
            return
            
        method = message['method']
        params = message.get('params', [])
        message_id = message.get('id', None)
        
        logger.debug(f"Received method: {method}, params: {params}, id: {message_id}")
        
        # Record the method name from miner to pool
        self.factory.stats.record_miner_to_pool_method(method, params)
        
        try:
            if method == 'mining.subscribe':
                self.handle_subscribe(message_id, params)
            elif method == 'mining.authorize':
                self.handle_authorize(message_id, params)
            elif method == 'mining.submit':
                self.handle_submit(message_id, params)
            elif method == 'mining.get_transactions':
                self.handle_get_transactions(message_id)
            elif method == 'mining.configure':
                self.handle_configure(message_id, params)
            elif method == 'mining.suggest_difficulty':
                self.handle_suggest_difficulty(message_id, params)
            elif method == 'mining.suggest_target':
                self.handle_suggest_target(message_id, params)
            elif method == 'mining.extranonce.subscribe':
                self.handle_extranonce_subscribe(message_id)
            elif method == 'mining.multi_version':
                self.handle_multi_version(message_id, params)
            else:
                logger.warning(f"Unknown method from {self.client_id}: {method}")
                if message_id is not None:
                    self.send_error(message_id, -32601, f"Method '{method}' not found")
        except Exception as e:
            logger.error(f"Error handling method {method} from {self.client_id}: {str(e)}")
            logger.debug(traceback.format_exc())
            if message_id is not None:
                self.send_error(message_id, -32603, f"Internal error: {str(e)}")
    
    def handle_subscribe(self, message_id, params):
        """Handle mining.subscribe method"""
        try:
            # Generate a unique subscription ID
            self.subscription_id = str(uuid.uuid4())
            
            # Generate a unique extranonce1
            self.extranonce1 = self.factory.get_new_extranonce1()
            
            # Fixed extranonce2_size for simplicity
            extranonce2_size = 4
            
            # Prepare response
            response = [
                [
                    ["mining.set_difficulty", self.subscription_id],
                    ["mining.notify", self.subscription_id]
                ],
                self.extranonce1,
                extranonce2_size
            ]
            
            # Send response
            self.send_result(message_id, response)
            
            # Add client to the factory's client list
            self.factory.add_client(self)
            
            # Send initial difficulty
            self.send_difficulty(self.difficulty)
            
            # Send initial job
            self.factory.send_job_to_client(self)
            
            logger.info(f"Client {self.client_id} subscribed with extranonce1: {self.extranonce1}")
        except Exception as e:
            logger.error(f"Error in subscribe from {self.client_id}: {str(e)}")
            logger.debug(traceback.format_exc())
            self.send_error(message_id, -32603, f"Internal error: {str(e)}")
    
    def handle_authorize(self, message_id, params):
        """Handle mining.authorize method"""
        if len(params) < 2:
            self.send_error(message_id, -32602, "Invalid params")
            return
            
        username = params[0]
        password = params[1]
        
        # In a solo mining pool, we accept any credentials
        self.authorized = True
        self.worker_name = username
        
        logger.info(f"Authorized worker: {username} from {self.client_id}")
        self.send_result(message_id, True)
    
    def handle_submit(self, message_id, params):
        """Handle mining.submit method"""
        if not self.authorized:
            self.send_error(message_id, -32500, "Not authorized")
            return
            
        if len(params) < 5:
            self.send_error(message_id, -32602, "Invalid params")
            return
            
        worker_name = params[0]
        job_id = params[1]
        extranonce2 = params[2]
        time_hex = params[3]
        nonce_hex = params[4]
        
        logger.debug(f"Share submission from {worker_name}: job_id={job_id}, extranonce2={extranonce2}, time={time_hex}, nonce={nonce_hex}")
        
        # Record share time for difficulty adjustment
        changed, new_diff = self.factory.difficulty_adjuster.record_share(self.client_id)
        if changed:
            # If difficulty changed, update and notify the client
            self.send_difficulty(new_diff)
            self.difficulty = new_diff
        
        # Always accept shares for testing
        logger.info(f"Valid share (difficulty {self.difficulty}) submitted by {worker_name} from {self.client_id}")
        
        # Record the share in statistics
        self.factory.stats.add_share(worker_name, valid=True, difficulty=self.difficulty)
        
        # Send success response to client
        self.send_result(message_id, True)
    
    def handle_get_transactions(self, message_id):
        """Handle mining.get_transactions method"""
        # For simplicity, we don't implement this
        self.send_result(message_id, [])
    
    def handle_configure(self, message_id, params):
        """Handle mining.configure method"""
        # This method allows miners to configure various options
        # For simplicity, we'll just accept any configuration and return success
        logger.info(f"Client {self.client_id} requested configuration: {params}")
        
        # Default response - accept all configurations
        response = {}
        
        # If params is a dict with extensions
        if len(params) > 0 and isinstance(params[0], dict):
            extensions = params[0]
            for ext_name, ext_params in extensions.items():
                # For each extension, indicate we support it
                response[ext_name] = True
                self.supported_extensions[ext_name] = ext_params
        
        self.send_result(message_id, response)
    
    def handle_suggest_difficulty(self, message_id, params):
        """Handle mining.suggest_difficulty method"""
        # This method allows miners to suggest a difficulty
        if len(params) > 0:
            try:
                # Original suggested difficulty from miner
                original_suggested_diff = float(params[0])
                logger.info(f"Client {self.client_id} originally suggested difficulty: {original_suggested_diff}")
                
                # Override with a much lower difficulty for testing
                suggested_diff = 0.01
                logger.info(f"Overriding to lower difficulty: {suggested_diff} for client {self.client_id}")
                
                # Use the difficulty adjuster to handle the suggestion
                changed, new_diff = self.factory.difficulty_adjuster.suggest_difficulty(
                    self.client_id, suggested_diff
                )
                
                # If difficulty changed, update and notify the client
                if changed:
                    self.send_difficulty(new_diff)
                    self.difficulty = new_diff
            except (ValueError, TypeError):
                logger.warning(f"Invalid difficulty suggestion from {self.client_id}: {params[0]}")
        
        # Always return true to indicate we received the suggestion
        self.send_result(message_id, True)
    
    def handle_suggest_target(self, message_id, params):
        """Handle mining.suggest_target method"""
        # Similar to suggest_difficulty but with a target instead
        if len(params) > 0:
            try:
                logger.info(f"Client {self.client_id} suggested target: {params[0]}")
                # We acknowledge but don't use it
                self.send_difficulty(self.difficulty)
            except Exception as e:
                logger.warning(f"Invalid target suggestion from {self.client_id}: {str(e)}")
        
        self.send_result(message_id, True)
    
    def handle_extranonce_subscribe(self, message_id):
        """Handle mining.extranonce.subscribe method"""
        # This indicates the client wants to be notified of extranonce changes
        logger.info(f"Client {self.client_id} subscribed to extranonce changes")
        self.send_result(message_id, True)
    
    def handle_multi_version(self, message_id, params):
        """Handle mining.multi_version method"""
        # This indicates the client supports multiple versions
        if len(params) > 0:
            try:
                version = str(params[0])
                logger.info(f"Client {self.client_id} supports version: {version}")
                if version in self.supported_versions:
                    self.send_result(message_id, True)
                else:
                    self.send_result(message_id, False)
            except Exception as e:
                logger.warning(f"Invalid version from {self.client_id}: {str(e)}")
                self.send_result(message_id, False)
        else:
            self.send_result(message_id, False)
    
    def send_result(self, message_id, result):
        """Send a JSON-RPC result to the client"""
        if message_id is None:
            return
            
        response = {
            "id": message_id,
            "result": result,
            "error": None
        }
        
        self.send_json(response)
    
    def send_error(self, message_id, code, message):
        """Send a JSON-RPC error to the client"""
        if message_id is None:
            return
            
        response = {
            "id": message_id,
            "result": None,
            "error": [code, message, None]
        }
        
        self.send_json(response)
    
    def send_notification(self, method, params):
        """Send a JSON-RPC notification to the client"""
        notification = {
            "id": None,
            "method": method,
            "params": params
        }
        
        # Record the method name from pool to miner
        self.factory.stats.record_pool_to_miner_method(method, params)
        
        self.send_json(notification)
    
    def send_json(self, obj):
        """Send a JSON object to the client"""
        try:
            message = json.dumps(obj) + '\n'
            self.transport.write(message.encode())
        except Exception as e:
            logger.error(f"Error sending JSON to {self.client_id}: {str(e)}")
    
    def send_difficulty(self, difficulty):
        """Send mining.set_difficulty notification"""
        self.difficulty = difficulty
        self.send_notification("mining.set_difficulty", [difficulty])
    
    def send_job(self, job_id, prev_hash, coinbase1, coinbase2, merkle_branches, version, bits, time, clean_jobs):
        """Send mining.notify notification"""
        # Convert merkle branches to hex strings
        merkle_branches_hex = [branch for branch in merkle_branches]
        
        # Prepare notification parameters
        params = [
            job_id,
            prev_hash,
            coinbase1,
            coinbase2,
            merkle_branches_hex,
            version,
            bits,
            time,
            clean_jobs
        ]
        
        # Send notification
        self.send_notification("mining.notify", params)
        logger.debug(f"Sent job {job_id} to client {self.client_id}")


class StratumFactory(Factory):
    """
    Factory for the Stratum protocol
    """
    
    protocol = StratumProtocol
    
    def __init__(self, bitcoin_rpc, pool_address, initial_difficulty=1):
        self.bitcoin_rpc = bitcoin_rpc
        self.pool_address = pool_address
        self.clients = {}
        self.jobs = {}
        self.current_jobs = {}  # Maps job_id to job details
        self.extranonce1_counter = 0
        self.job_counter = 0
        self.coinbase_message = b"Python Solo Mining Pool"
        
        # Initialize statistics tracker
        self.stats = PoolStats()
        
        # Initialize difficulty adjuster
        self.difficulty_adjuster = DifficultyAdjuster(
            initial_difficulty=initial_difficulty,
            target_share_time=10,  # Target 10 seconds between shares
            min_difficulty=0.01,
            max_difficulty=1000000
        )
        
        # Initialize with a block template
        self.update_block_template()
        
        # Schedule periodic updates
        reactor.callLater(30, self.periodic_update)
        
        # Schedule periodic stats logging
        reactor.callLater(60, self.log_stats)
    
    def log_stats(self):
        """Log pool statistics periodically"""
        try:
            stats = self.stats.get_stats()
            logger.info(f"Pool stats: {stats['hashrate_human']}, {stats['shares']['valid']} shares, {stats['blocks_found']} blocks, {stats['clients']} miners")
            
            # Log individual worker stats if we have any
            worker_stats = self.stats.get_worker_stats()
            for worker, wstats in worker_stats.items():
                logger.debug(f"Worker {worker}: {wstats['hashrate_human']}, {wstats['shares']['valid']} shares, diff={wstats['difficulty']}")
        except Exception as e:
            logger.error(f"Error logging stats: {str(e)}")
        finally:
            # Schedule next stats logging
            reactor.callLater(60, self.log_stats)
    
    def periodic_update(self):
        """Periodically update the block template"""
        try:
            self.update_block_template()
        except Exception as e:
            logger.error(f"Error in periodic update: {str(e)}")
            logger.debug(traceback.format_exc())
        finally:
            # Schedule the next update
            reactor.callLater(30, self.periodic_update)
    
    def update_block_template(self):
        """Update the current block template"""
        try:
            # Get a new block template from Bitcoin Core
            block_template = self.bitcoin_rpc.get_block_template(['coinbasetxn', 'workid'])
            
            # Create mining job
            job = self.create_mining_job(block_template)
            
            # Generate job ID
            job_id = f"{int(time.time())}_{self.job_counter}"
            self.job_counter += 1
            
            # Store job for validation
            self.jobs[job_id] = job
            self.current_jobs[job_id] = job
            
            # Keep only the last 10 jobs
            if len(self.jobs) > 10:
                oldest_job = min(self.jobs.keys())
                del self.jobs[oldest_job]
            
            # Log new block template
            logger.info(f"New block template received at height {job['height']}")
            
            # Send to all connected clients
            self.send_job_to_all_clients(job_id, job, clean_jobs=True)
            
            return job_id, job
        except Exception as e:
            logger.error(f"Error updating block template: {str(e)}")
            logger.debug(traceback.format_exc())
            return None, None
    
    def create_mining_job(self, block_template):
        """Create a mining job from a block template"""
        try:
            # Extract data from block template
            version = block_template['version']
            prev_block_hash = block_template['previousblockhash']
            height = block_template['height']
            bits = int(block_template['bits'], 16)
            transactions = block_template.get('transactions', [])
            
            # Create coinbase transaction
            coinbase_tx, coinbase_tx_hash = self.create_coinbase_tx(height, block_template['coinbasevalue'])
            
            # Calculate merkle root
            merkle_branches = []
            merkle_root = coinbase_tx_hash
            
            # Add transaction hashes to merkle tree
            tx_hashes = []
            for tx in transactions:
                tx_hash = binascii.unhexlify(tx['txid'])[::-1]  # Reverse byte order
                tx_hashes.append(tx_hash)
            
            # Calculate merkle branches
            if tx_hashes:
                merkle_branches, merkle_root = self.calculate_merkle_branches(coinbase_tx_hash, tx_hashes)
            
            # Create job
            job = {
                'version': version,
                'prev_block_hash': prev_block_hash,
                'coinbase': coinbase_tx,
                'merkle_branches': merkle_branches,
                'height': height,
                'bits': bits,
                'transactions': [tx.get('data', '') for tx in transactions],
                'merkle_root': binascii.hexlify(merkle_root).decode()
            }
            
            return job
        except Exception as e:
            logger.error(f"Error creating mining job: {str(e)}")
            logger.debug(traceback.format_exc())
            return None
    
    def create_coinbase_tx(self, height, coinbase_value):
        """Create a coinbase transaction with extranonce placeholder"""
        # Create a simple coinbase transaction
        # This is a simplified version, a real implementation would create a proper scriptPubKey
        
        # Version
        tx = struct.pack('<I', 1)
        
        # Input count
        tx += struct.pack('<B', 1)
        
        # Previous output hash (zeros for coinbase)
        tx += b'\x00' * 32
        
        # Previous output index (0xFFFFFFFF for coinbase)
        tx += struct.pack('<I', 0xFFFFFFFF)
        
        # Script length (variable)
        height_script = struct.pack('<I', height) + self.coinbase_message
        script_len = len(height_script) + 8  # Add 8 bytes for extranonce
        tx += struct.pack('<B', script_len)
        
        # Coinbase script with height and extranonce placeholder
        tx += height_script
        
        # Extranonce placeholder (8 bytes)
        tx += b'\x00\x00\x00\x00\x00\x00\x00\x00'
        
        # Sequence
        tx += struct.pack('<I', 0xFFFFFFFF)
        
        # Output count
        tx += struct.pack('<B', 1)
        
        # Output value
        tx += struct.pack('<Q', coinbase_value)
        
        # Output script length
        # P2PKH script for the pool address
        # This is a simplified version, a real implementation would create a proper scriptPubKey
        script = b'\x76\xa9\x14' + b'\x00' * 20 + b'\x88\xac'  # OP_DUP OP_HASH160 <20-byte-hash> OP_EQUALVERIFY OP_CHECKSIG
        tx += struct.pack('<B', len(script))
        
        # Output script
        tx += script
        
        # Locktime
        tx += struct.pack('<I', 0)
        
        # Calculate the hash of the coinbase transaction
        coinbase_hash = hashlib.sha256(hashlib.sha256(tx).digest()).digest()
        
        return tx, coinbase_hash
    
    def calculate_merkle_branches(self, coinbase_hash, tx_hashes):
        """Calculate merkle branches for the coinbase transaction"""
        # Start with the coinbase hash
        merkle_tree = [coinbase_hash]
        
        # Add transaction hashes
        merkle_tree.extend(tx_hashes)
        
        # Calculate merkle branches
        branches = []
        
        # If there are no transactions, return empty branches
        if not tx_hashes:
            return branches, coinbase_hash
        
        # Calculate the merkle root
        while len(merkle_tree) > 1:
            # If odd number of elements, duplicate the last one
            if len(merkle_tree) % 2 == 1:
                merkle_tree.append(merkle_tree[-1])
            
            # Create branches for the current level
            if len(merkle_tree) > 2:  # Only add branches if not at the root level
                branches.append(merkle_tree[1])  # Add the second element as a branch
            
            # Calculate the next level
            next_level = []
            for i in range(0, len(merkle_tree), 2):
                # Concatenate and hash
                concat = merkle_tree[i] + merkle_tree[i+1]
                next_hash = hashlib.sha256(hashlib.sha256(concat).digest()).digest()
                next_level.append(next_hash)
            
            # Update the tree
            merkle_tree = next_level
        
        # Return branches and root
        return branches, merkle_tree[0]
    
    def send_job_to_all_clients(self, job_id, job, clean_jobs=False):
        """Send the current job to all connected clients"""
        disconnected_clients = set()
        for client in self.clients.values():
            if client.authorized:
                try:
                    client.send_job(
                        job_id,
                        job['prev_block_hash'],
                        binascii.hexlify(job['coinbase'][:42]).decode(),
                        binascii.hexlify(job['coinbase'][42+8:]).decode(),
                        [binascii.hexlify(branch).decode() for branch in job['merkle_branches']],
                        f"{job['version']:08x}",
                        f"{job['bits']:08x}",
                        f"{int(time.time()):08x}",
                        clean_jobs
                    )
                except Exception as e:
                    logger.error(f"Error sending job to client {client.client_id}: {str(e)}")
                    logger.debug(traceback.format_exc())
                    disconnected_clients.add(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            self.remove_client(client)
    
    def send_job_to_client(self, client):
        """Send the current job to a client"""
        try:
            # Get the latest job
            if not self.jobs:
                # If no jobs, get a new block template
                job_id, job = self.update_block_template()
            else:
                # Use the most recent job
                job_id = max(self.jobs.keys())
                job = self.jobs[job_id]
            
            if job:
                # Split coinbase transaction
                coinbase_tx = job['coinbase']
                pos = coinbase_tx.find(b'\x00\x00\x00\x00\x00\x00\x00\x00')
                
                if pos != -1:
                    coinbase1 = binascii.hexlify(coinbase_tx[:pos]).decode()
                    coinbase2 = binascii.hexlify(coinbase_tx[pos+8:]).decode()
                    
                    # Convert merkle branches to hex
                    merkle_branches_hex = [binascii.hexlify(branch).decode() for branch in job['merkle_branches']]
                    
                    # Send job to client
                    client.send_job(
                        job_id,
                        job['prev_block_hash'],
                        coinbase1,
                        coinbase2,
                        merkle_branches_hex,
                        f"{job['version']:08x}",
                        f"{job['bits']:08x}",
                        f"{int(time.time()):08x}",
                        True
                    )
                    
                    logger.debug(f"Sent job {job_id} to client {client.client_id}")
                else:
                    logger.error("Extranonce placeholder not found in coinbase")
        except Exception as e:
            logger.error(f"Error sending job to client: {str(e)}")
            logger.debug(traceback.format_exc())
    
    def process_submission(self, worker_name, job_id, extranonce2, time_hex, nonce_hex, extranonce1, difficulty):
        """Process a share submission and check if it's valid"""
        # Get the job
        job = self.current_jobs.get(job_id)
        if not job:
            logger.warning(f"Job not found: {job_id}")
            return {'valid': False, 'error': f'Job not found: {job_id}'}
        
        logger.debug(f"Processing submission for job {job_id} with difficulty {difficulty}")
        logger.debug(f"Job details: height={job.get('height')}, bits={job.get('bits')}")
        
        try:
            # Construct the coinbase transaction
            coinbase_tx = job['coinbase']
            
            # Insert the extranonce values
            extranonce1_bin = binascii.unhexlify(extranonce1)
            extranonce2_bin = binascii.unhexlify(extranonce2)
            
            # Log the extranonce values for debugging
            logger.debug(f"Extranonce1: {extranonce1} (len={len(extranonce1_bin)})")
            logger.debug(f"Extranonce2: {extranonce2} (len={len(extranonce2_bin)})")
            
            # Find the position to insert the extranonce
            pos = coinbase_tx.find(b'\x00\x00\x00\x00\x00\x00\x00\x00')
            if pos == -1:
                logger.error("Extranonce placeholder not found in coinbase")
                return {'valid': False, 'error': 'Extranonce placeholder not found in coinbase'}
            
            # Insert the extranonce values
            coinbase_tx_with_extranonce = coinbase_tx[:pos] + extranonce1_bin + extranonce2_bin + coinbase_tx[pos+8:]
            
            # Calculate the merkle root with the updated coinbase
            coinbase_hash = hashlib.sha256(hashlib.sha256(coinbase_tx_with_extranonce).digest()).digest()
            merkle_root = coinbase_hash
            for branch in job['merkle_branches']:
                branch_bin = binascii.unhexlify(branch)
                merkle_root = hashlib.sha256(hashlib.sha256(merkle_root + branch_bin).digest()).digest()
            
            # Convert time and nonce to binary
            time_bin = binascii.unhexlify(time_hex)
            nonce_bin = binascii.unhexlify(nonce_hex)
            
            # Construct the block header
            version = struct.pack('<I', job['version'])
            prev_hash = binascii.unhexlify(job['prev_block_hash'])
            bits = struct.pack('<I', job['bits'])
            
            # Log the header components for debugging
            logger.debug(f"Header components:")
            logger.debug(f"  Version: {binascii.hexlify(version).decode()}")
            logger.debug(f"  Prev hash: {binascii.hexlify(prev_hash).decode()}")
            logger.debug(f"  Merkle root: {binascii.hexlify(merkle_root).decode()}")
            logger.debug(f"  Time: {time_hex}")
            logger.debug(f"  Bits: {binascii.hexlify(bits).decode()}")
            logger.debug(f"  Nonce: {nonce_hex}")
            
            # Assemble the header
            header = version + prev_hash + merkle_root + time_bin + bits + nonce_bin
            
            # Calculate the hash of the header
            hash_result = hash_block_header(header)
            hash_hex = binascii.hexlify(hash_result).decode()
            hash_int = int.from_bytes(hash_result, byteorder='little')
            
            # Calculate targets
            diff1_target = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
            share_target = int(diff1_target / difficulty)
            network_target = bits_to_target(job['bits'])
            
            # Log the targets and hash for debugging
            logger.debug(f"Share target: {share_target:064x}")
            logger.debug(f"Network target: {network_target:064x}")
            logger.debug(f"Hash: {hash_hex} (int: {hash_int})")
            
            # Check if the hash meets the share target
            valid_share = hash_int <= share_target
            valid_block = hash_int <= network_target
            
            if valid_share:
                logger.info(f"Valid share found! Hash: {hash_hex}")
                
                if valid_block:
                    logger.info(f"BLOCK FOUND! Hash: {hash_hex}")
                    
                    # Construct the full block
                    block = header + encode_varint(len(job['transactions']) + 1)
                    block += coinbase_tx_with_extranonce
                    
                    for tx_data in job['transactions']:
                        block += binascii.unhexlify(tx_data)
                    
                    # Submit the block to the Bitcoin network
                    block_hex = binascii.hexlify(block).decode()
                    try:
                        result = self.bitcoin_rpc.submitblock(block_hex)
                        if result is None or result == '':
                            logger.info("Block accepted by the network!")
                            return {
                                'valid': True,
                                'block_accepted': True,
                                'hash': hash_hex,
                                'height': job['height']
                            }
                        else:
                            logger.warning(f"Block rejected by the network: {result}")
                            return {
                                'valid': True,
                                'block_accepted': False,
                                'error': f"Block rejected: {result}",
                                'hash': hash_hex,
                                'height': job['height']
                            }
                    except Exception as e:
                        logger.error(f"Error submitting block to network: {str(e)}")
                        return {
                            'valid': True,
                            'block_accepted': False,
                            'error': f"Error submitting block: {str(e)}",
                            'hash': hash_hex,
                            'height': job['height']
                        }
                else:
                    return {'valid': True}
            else:
                logger.warning(f"Invalid share: hash {hash_hex} > target {share_target:064x}")
                return {'valid': False, 'error': f'Share did not meet target difficulty (hash: {hash_hex}, target: {share_target:064x})'}
        except Exception as e:
            logger.error(f"Error validating share: {str(e)}")
            logger.debug(traceback.format_exc())
            return {'valid': False, 'error': f'Error validating share: {str(e)}'}
    
    def get_new_extranonce1(self):
        """Generate a new extranonce1 value"""
        self.extranonce1_counter += 1
        return binascii.hexlify(struct.pack('<I', self.extranonce1_counter)).decode()
    
    def add_client(self, client):
        """Add a client to the factory"""
        self.clients[client.client_id] = client
        logger.info(f"Client added: {client.client_id}, total clients: {len(self.clients)}")
        
        # Add client to statistics
        self.stats.add_client(client.client_id, client.worker_name)
    
    def remove_client(self, client):
        """Remove a client from the factory"""
        if client.client_id in self.clients:
            del self.clients[client.client_id]
            logger.info(f"Client removed: {client.client_id}, total clients: {len(self.clients)}")
            
            # Update statistics
            if client.worker_name:
                self.stats.remove_client(client.worker_name)

def hash_block_header(header):
    """Hash a block header"""
    return hashlib.sha256(hashlib.sha256(header).digest()).digest()

def bits_to_target(bits):
    """Convert bits to target"""
    bits_int = int.from_bytes(bits, byteorder='little')
    exponent = bits_int >> 24
    mantissa = bits_int & 0xFFFFFF
    return mantissa * (2 ** (8 * (exponent - 3)))

def encode_varint(n):
    """Encode a variable-length integer"""
    if n < 0:
        raise ValueError("Negative numbers are not supported")
    elif n < 0xFD:
        return struct.pack('<B', n)
    elif n < 0xFFFF:
        return struct.pack('<B', 0xFD) + struct.pack('<H', n)
    elif n < 0xFFFFFFFF:
        return struct.pack('<B', 0xFE) + struct.pack('<I', n)
    else:
        return struct.pack('<B', 0xFF) + struct.pack('<Q', n)
