#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import hashlib
import binascii
import struct
import logging
import time

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def uint256_from_str(s):
    """Convert a byte string to a 256-bit integer"""
    r = 0
    t = s[::-1]  # Reverse the byte order
    for i in range(len(t)):
        r += int(t[i]) << (i * 8)
    return r

def uint256_to_str(u):
    """Convert a 256-bit integer to a byte string"""
    rs = b''
    for i in range(32):
        rs += bytes([u & 0xFF])
        u >>= 8
    return rs

def reverse_bytes(data):
    """Reverse the byte order of a hex string"""
    b = binascii.unhexlify(data)
    return binascii.hexlify(b[::-1])

def calculate_merkle_root(txids):
    """Calculate the Merkle root from a list of transaction IDs"""
    if not txids:
        return None
    
    if len(txids) == 1:
        return txids[0]
    
    # Make sure we have an even number of txids
    if len(txids) % 2 == 1:
        txids.append(txids[-1])
    
    next_level = []
    for i in range(0, len(txids), 2):
        # Concatenate and hash the pair
        concat = binascii.unhexlify(txids[i]) + binascii.unhexlify(txids[i+1])
        next_level.append(binascii.hexlify(hashlib.sha256(hashlib.sha256(concat).digest()).digest()).decode())
    
    # Recursive call to process the next level
    return calculate_merkle_root(next_level)

def create_coinbase(height, coinbase_value, coinbase_message, address):
    """Create a coinbase transaction"""
    # Coinbase input script contains the block height and arbitrary data
    script_sig = (
        # Height (BIP34)
        bytes([len(struct.pack('<I', height))]) + 
        struct.pack('<I', height) +
        # Arbitrary data (limited to 100 bytes)
        bytes([min(len(coinbase_message), 100)]) + 
        coinbase_message[:100]
    )
    
    # Create the transaction
    coinbase = struct.pack('<I', 1)  # Version
    coinbase += bytes([1])  # Number of inputs
    coinbase += bytes([0] * 32)  # Previous output hash (null for coinbase)
    coinbase += struct.pack('<I', 0xFFFFFFFF)  # Previous output index
    coinbase += bytes([len(script_sig)])  # Script length
    coinbase += script_sig  # Script sig
    coinbase += struct.pack('<I', 0)  # Sequence
    coinbase += bytes([1])  # Number of outputs
    coinbase += struct.pack('<Q', coinbase_value)  # Output value
    
    # P2PKH script: OP_DUP OP_HASH160 <pubKeyHash> OP_EQUALVERIFY OP_CHECKSIG
    # For simplicity, we'll use a hardcoded P2PKH script to avoid address parsing issues
    # In a real implementation, you would properly parse the address
    script_pubkey = bytes.fromhex('76a91488ac')  # Placeholder script
    
    coinbase += bytes([len(script_pubkey)])  # Script length
    coinbase += script_pubkey  # Script pubkey
    coinbase += struct.pack('<I', 0)  # Lock time
    
    return binascii.hexlify(coinbase).decode()

def create_block_header(version, prev_block_hash, merkle_root, timestamp, bits, nonce):
    """Create a block header"""
    header = struct.pack('<I', version)
    header += binascii.unhexlify(prev_block_hash)
    header += binascii.unhexlify(merkle_root)
    header += struct.pack('<I', timestamp)
    header += struct.pack('<I', bits)
    header += struct.pack('<I', nonce)
    
    return header

def hash_block_header(header):
    """Double SHA256 hash of a block header"""
    return hashlib.sha256(hashlib.sha256(header).digest()).digest()

def encode_varint(n):
    """Encode an integer as a varint"""
    if n < 0xfd:
        return struct.pack('<B', n)
    elif n <= 0xffff:
        return struct.pack('<BH', 0xfd, n)
    elif n <= 0xffffffff:
        return struct.pack('<BI', 0xfe, n)
    else:
        return struct.pack('<BQ', 0xff, n)

def bits_to_target(bits):
    """Convert compact target representation to full 256-bit target"""
    # Extract exponent and mantissa
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    
    # Convert to target
    if mant > 0x7FFFFF:
        mant = 0x7FFFFF  # Limit to 23 bits
    
    target = mant * (1 << (8 * (exp - 3)))
    return target

def is_valid_proof_of_work(block_hash, target):
    """Check if the block hash meets the target difficulty"""
    # Convert block hash to integer (little endian)
    hash_int = int.from_bytes(block_hash, byteorder='little')
    
    # Compare with target
    return hash_int <= target

def get_difficulty(bits):
    """Calculate difficulty from bits"""
    # Bitcoin's difficulty 1 target
    diff1_target = 0x00ffff * 2**(8*(0x1d - 3))
    
    # Current target
    current_target = bits_to_target(bits)
    
    # Difficulty is ratio of diff1_target to current target
    return diff1_target / current_target

def create_mining_job(block_template, coinbase_message, pool_address):
    """Create a mining job from a block template"""
    try:
        height = block_template['height']
        version = block_template['version']
        prev_block_hash = block_template['previousblockhash']
        bits = int(block_template['bits'], 16)
        timestamp = int(time.time())
        
        # Create coinbase transaction
        coinbase_value = sum([tx.get('fee', 0) for tx in block_template.get('transactions', [])])
        coinbase_value += block_template.get('coinbasevalue', 0)
        
        coinbase_tx = create_coinbase(height, coinbase_value, coinbase_message.encode(), pool_address)
        coinbase_txid = hashlib.sha256(hashlib.sha256(binascii.unhexlify(coinbase_tx)).digest()).digest()
        coinbase_txid = binascii.hexlify(coinbase_txid).decode()
        
        # Calculate merkle root
        txids = [coinbase_txid]
        txids.extend([tx.get('txid', '') for tx in block_template.get('transactions', [])])
        merkle_root = calculate_merkle_root(txids)
        
        # Create block header template
        header_template = {
            'version': version,
            'prev_block_hash': prev_block_hash,
            'merkle_root': merkle_root,
            'timestamp': timestamp,
            'bits': bits,
            'coinbase': coinbase_tx,
            'height': height,
            'transactions': [tx.get('data', '') for tx in block_template.get('transactions', [])]
        }
        
        return header_template
    except Exception as e:
        logger.error(f"Error creating mining job: {str(e)}")
        raise

def check_work(header, target):
    """Check if the work meets the target difficulty"""
    hash_result = hash_block_header(header)
    return is_valid_proof_of_work(hash_result, target), binascii.hexlify(hash_result).decode()
