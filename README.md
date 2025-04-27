# Bitcoin Solo Mining Pool

A simple Python-based Bitcoin solo mining pool that connects to a local Bitcoin Core node via RPC and exposes a Stratum server for miners to connect.

## Features

- Connects to a local Bitcoin Core node via RPC
- Implements the Stratum mining protocol
- Supports solo mining (all rewards go to a single address)
- Automatic variable difficulty adjustment for optimal share rates
- Real-time mining statistics tracking
- Web interface for monitoring pool performance
- Robust error handling and recovery

## Requirements

- Python 3.6+
- Bitcoin Core node with RPC enabled
- Stratum-compatible mining software

## Installation

1. Clone this repository:
   ```
   git clone https://github.com/yourusername/bitcoin-solo-pool.git
   cd bitcoin-solo-pool
   ```

2. Create a virtual environment (recommended):
   ```
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

   **Note:** If you encounter an error like "error: externally-managed-environment", you have a few options:
   
   a. Use the `--break-system-packages` flag (not recommended for production):
   ```
   pip install --break-system-packages -r requirements.txt
   ```
   
   b. Use a virtual environment (recommended):
   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```
   
   c. Use pipx for isolated installation:
   ```
   pipx install -r requirements.txt
   ```

## Configuration

1. Edit `config.ini` with your Bitcoin Core RPC credentials:

```ini
[bitcoind]
rpcuser = your_rpc_username
rpcpassword = your_rpc_password
rpchost = 127.0.0.1
rpcport = 8332

[pool]
address = your_bitcoin_address
coinbase_message = Your Pool Name
difficulty = 1
```

## Usage

Start the mining pool:

```
python3 solo_pool.py --address your_bitcoin_address --verbose
```

### Command Line Options

- `--address`: Bitcoin address for block rewards
- `--port`: Port for Stratum server (default: 3333)
- `--host`: Interface to listen on (default: 0.0.0.0)
- `--difficulty`: Initial mining difficulty (default: 1)
- `--coinbase-msg`: Coinbase message (default: "Python Solo Mining Pool")
- `--config`: Path to config file (default: config.ini)
- `--verbose`: Enable verbose logging
- `--web`: Enable web statistics interface
- `--web-port`: Port for web statistics (default: 8080)

### Connecting Miners

Connect your mining software to the pool using:

- Server: your_server_ip
- Port: 3333 (or your custom port)
- Username: any_username (not used for authentication)
- Password: x (not used for authentication)

Example for cgminer:
```
cgminer -o stratum+tcp://your_server_ip:3333 -u worker1 -p x
```

## Advanced Features

### Variable Difficulty

The pool automatically adjusts difficulty for each miner to optimize share submission rates. This helps reduce network traffic while maintaining accurate hashrate statistics.

### Web Statistics

Enable the web interface with the `--web` flag to monitor pool performance in real-time:

```
python3 solo_pool.py --address your_bitcoin_address --web
```

Then access the statistics at: http://your_server_ip:8080

### JSON API

Access raw statistics data via the JSON API endpoint:
```
http://your_server_ip:8080/api
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This software is provided for educational purposes only. Mining Bitcoin consumes significant electricity and may not be profitable depending on your circumstances. Use at your own risk.
