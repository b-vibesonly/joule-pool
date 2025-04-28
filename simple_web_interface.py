#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
import re
import logging
from twisted.web import server, resource
from twisted.internet import reactor
from datetime import datetime

class JSONStatsResource(resource.Resource):
    """Resource for JSON API access to pool statistics"""
    
    isLeaf = True
    
    def __init__(self, factory):
        resource.Resource.__init__(self)
        self.factory = factory
    
    def render_GET(self, request):
        """Render JSON API response"""
        request.setHeader(b"content-type", b"application/json; charset=utf-8")
        
        # Get pool stats
        pool_stats = self.factory.stats.get_pool_stats()
        
        # Get worker stats
        worker_stats = self.factory.stats.get_worker_stats()
        
        # Format worker stats for JSON
        formatted_workers = {}
        for worker_name, stats in worker_stats.items():
            formatted_workers[worker_name] = {
                'valid_shares': stats.get('shares', {}).get('valid', 0),
                'invalid_shares': stats.get('shares', {}).get('invalid', 0),
                'blocks_found': stats.get('blocks_found', 0),
                'last_share_time': stats.get('last_share_time', 0)
            }
        
        # Build response
        response = {
            'pool': {
                'hashrate': pool_stats.get('hashrate', 0),
                'total_shares': pool_stats.get('total_shares', 0),
                'valid_shares': pool_stats.get('valid_shares', 0),
                'invalid_shares': pool_stats.get('invalid_shares', 0),
                'blocks_found': pool_stats.get('blocks_found', 0),
                'connected_miners': pool_stats.get('connected_miners', 0),
                'uptime': pool_stats.get('uptime', 0)
            },
            'workers': formatted_workers,
            'timestamp': int(time.time())
        }
        
        return json.dumps(response, indent=4).encode('utf-8')

class PoolStatsPage(resource.Resource):
    """Pool statistics page"""
    isLeaf = True
    
    def __init__(self, factory):
        resource.Resource.__init__(self)
        self.factory = factory
        self.last_difficulty = 1.0
        self.difficulty_history = []  # Store recent difficulty values
        
    def get_latest_difficulty_from_logs(self):
        """Extract the latest mining difficulty from log messages"""
        try:
            # Define the log file path - adjust as needed
            log_files = [
                "mining_pool.log",  # Default log file
                "/var/log/mining_pool.log",  # System log location
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "mining_pool.log"),  # Same directory as script
                os.path.join(os.path.expanduser("~"), "mining_pool.log"),  # User's home directory
                "/tmp/mining_pool.log",  # Temporary directory
                "solo_pool.log",  # Alternative name
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "solo_pool.log"),
                "logs/mining_pool.log",
                "logs/solo_pool.log",
                "../logs/mining_pool.log",
            ]
            
            # Try to find an existing log file
            log_file = None
            for file_path in log_files:
                if os.path.exists(file_path):
                    log_file = file_path
                    break
            
            if log_file is None:
                # If no log file found, check if we can access stdout/stderr
                return None
                
            # Patterns to match difficulty in log messages
            patterns = [
                r"Sent new difficulty ([0-9.]+) to",
                r"Halving difficulty from [0-9.]+ to ([0-9.]+)",
                r"difficulty from [0-9.]+ to ([0-9.]+)",
                r"new difficulty ([0-9.]+) to",
                r"difficulty: ([0-9.]+)"
            ]
            
            # Read the last 50 lines of the log file
            with open(log_file, 'r') as f:
                # Get file size
                f.seek(0, 2)
                file_size = f.tell()
                
                # Start from the end and read up to 20KB
                f.seek(max(0, file_size - 20000), 0)
                lines = f.readlines()
                
                # Take the last 100 lines
                lines = lines[-100:]
            
            # Search for difficulty values in reverse order (newest first)
            for line in reversed(lines):
                for pattern in patterns:
                    match = re.search(pattern, line)
                    if match:
                        difficulty = float(match.group(1))
                        # Add to history
                        self.difficulty_history.append(difficulty)
                        if len(self.difficulty_history) > 5:
                            self.difficulty_history = self.difficulty_history[-5:]
                        return difficulty
                    
            return None
        except Exception as e:
            logging.error(f"Error extracting difficulty from logs: {str(e)}")
            return None
    
    def get_difficulty_from_stdout(self):
        """Try to capture difficulty values from stdout/stderr"""
        try:
            # This is a fallback method to get difficulty values
            # Check if we have any values in history
            if self.difficulty_history:
                return self.difficulty_history[-1]
            return None
        except Exception as e:
            logging.error(f"Error getting difficulty from stdout: {str(e)}")
            return None
    
    def render_GET(self, request):
        """Render the stats page"""
        request.setHeader(b"content-type", b"text/html; charset=utf-8")
        
        # Get pool stats
        pool_stats = self.factory.stats.get_pool_stats()
        
        # Get worker stats
        worker_stats = self.factory.stats.get_worker_stats()
        
        # Get current job information to extract block number
        block_number = "Unknown"
        if self.factory.jobs:
            # Get the latest job
            job_id = max(self.factory.jobs.keys())
            job = self.factory.jobs[job_id]
            block_number = job.get('height', 'Unknown')
        
        # Get the reward address (last 4 characters)
        reward_address = "Unknown"
        full_reward_address = "Unknown"
        
        if hasattr(self.factory, 'pool_address') and self.factory.pool_address:
            full_address = self.factory.pool_address
            # Mask the middle characters, keeping first 2 and last 2
            if len(full_address) > 4:
                full_reward_address = full_address[:2] + '*' * (len(full_address) - 4) + full_address[-2:]
            else:
                full_reward_address = full_address
            reward_address = full_address[-4:] if len(full_address) >= 4 else full_address
        elif pool_stats.get('reward_address'):
            full_address = pool_stats.get('reward_address')
            # Mask the middle characters, keeping first 2 and last 2
            if len(full_address) > 4:
                full_reward_address = full_address[:2] + '*' * (len(full_address) - 4) + full_address[-2:]
            else:
                full_reward_address = full_address
            reward_address = full_address[-4:] if len(full_address) >= 4 else full_address
        
        # Get command history
        command_history = self.factory.stats.get_stratum_command_history()
        
        # Sort by timestamp in descending order (newest first)
        command_history.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Limit to 10 most recent commands
        command_history = command_history[:10]
        
        # Format worker stats as HTML table rows
        worker_rows = ""
        for worker, stats in worker_stats.items():
            # Only show workers with 1 or more valid shares
            if stats.get('shares', {}).get('valid', 0) < 1:
                continue
                
            # Calculate time since last share
            time_since_last_share = "Never"
            if stats.get('last_share_time', 0) > 0:
                seconds_since = time.time() - stats.get('last_share_time', 0)
                time_since_last_share = f"{int(seconds_since)} seconds"
                if seconds_since >= 60:
                    minutes = int(seconds_since / 60)
                    seconds = int(seconds_since % 60)
                    time_since_last_share = f"{minutes}m {seconds}s"
                if seconds_since >= 3600:
                    hours = int(seconds_since / 3600)
                    minutes = int((seconds_since % 3600) / 60)
                    time_since_last_share = f"{hours}h {minutes}m"
            
            worker_rows += f"""
            <tr>
                <td>{block_number}</td>
                <td>{time_since_last_share}</td>
                <td>{stats.get('shares', {}).get('valid', 0)}</td>
                <td>{reward_address}</td>
            </tr>
            """
        
        # Format stratum command history
        command_history_rows = ""
        # Reverse the command history to show newest first and take 10 commands
        for cmd in command_history:
            timestamp = datetime.fromtimestamp(cmd.get('timestamp', 0)).strftime('%H:%M:%S')
            sender = cmd.get('sender', 'unknown')
            method = cmd.get('method', 'unknown')
            params = cmd.get('params', None)
            
            # Format parameters as a string, truncate if too long
            params_str = ""
            if params:
                try:
                    # Special handling for mining.submit to exclude the first parameter (worker name/address)
                    if method == 'mining.submit' and isinstance(params, list) and len(params) > 1:
                        # Create a copy of params without the first element
                        filtered_params = params[1:]
                        params_str = str(filtered_params)
                    elif isinstance(params, list) and len(params) > 0:
                        params_str = str(params)
                    elif isinstance(params, dict) and len(params) > 0:
                        params_str = str(params)
                    
                    # Truncate if too long
                    if len(params_str) > 50:
                        params_str = params_str[:47] + "..."
                except:
                    params_str = "Error formatting params"
            
            # Determine row class based on sender
            row_class = "miner-command" if sender == "miner" else "pool-command"
            
            command_history_rows += f"""
            <tr class="{row_class}">
                <td>{timestamp}</td>
                <td>{sender}</td>
                <td>{method}</td>
                <td>{params_str}</td>
            </tr>
            """
        
        # Get the mining difficulty directly from the difficulty adjuster
        try:
            # Get the difficulty directly from the adjuster
            mining_difficulty = 0
            
            # Try to get the difficulty from the clients dictionary in the adjuster
            if hasattr(self.factory, 'difficulty_adjuster') and hasattr(self.factory.difficulty_adjuster, 'client_difficulties'):
                # Get the first client's difficulty
                if self.factory.difficulty_adjuster.client_difficulties:
                    # Get any client ID
                    client_id = next(iter(self.factory.difficulty_adjuster.client_difficulties))
                    mining_difficulty = self.factory.difficulty_adjuster.client_difficulties[client_id]
            
            # If that failed, try to get it from the worker stats
            if mining_difficulty == 0:
                for worker, stats in worker_stats.items():
                    if stats.get('active', False):
                        mining_difficulty = stats.get('difficulty', 1.0)
                        break
            
            # If still no value, use the initial difficulty
            if mining_difficulty == 0:
                mining_difficulty = self.factory.difficulty_adjuster.initial_difficulty
        except Exception as e:
            logging.error(f"Error getting mining difficulty: {str(e)}")
            mining_difficulty = self.last_difficulty  # Use the last known value
        
        # Store this difficulty for future use
        self.last_difficulty = mining_difficulty
        
        # Get miner agent if available
        miner_agent = "Unknown"
        
        # First check if it's directly in worker stats
        for worker, stats in worker_stats.items():
            if stats.get('active', False) and 'agent' in stats:
                miner_agent = stats.get('agent', 'Unknown')
                break
        
        # If not found, check command history for mining.subscribe messages
        if miner_agent == "Unknown":
            for cmd in self.factory.stats.get_stratum_command_history():
                if cmd.get('method') == 'mining.subscribe' and cmd.get('sender') == 'miner' and cmd.get('params'):
                    try:
                        # The first parameter of mining.subscribe is the miner agent
                        if isinstance(cmd['params'], list) and len(cmd['params']) > 0:
                            agent_str = str(cmd['params'][0])
                            if agent_str and agent_str != "None":
                                miner_agent = agent_str
                                # If it's a Bitaxe miner, prioritize it
                                if "bitaxe" in agent_str.lower():
                                    break
                    except Exception as e:
                        logging.error(f"Error extracting miner agent from command history: {str(e)}")
        
        # Create HTML directly
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mining Dashboard</title>
    <style>
        body {{
            background-color: #000000;
            color: #eee;
            font-family: 'Courier New', monospace;
            margin: 0;
            padding: 20px;
        }}
        .card {{
            background-color: #000000;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.2);
        }}
        h1, h2 {{
            color: #0066cc;
            text-align: center;
        }}
        .bitcoin-logo {{
            color: #FF8000;
            font-size: 24px;
            font-weight: bold;
            margin-left: 10px;
        }}
        .stats-container {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            grid-template-rows: 1fr 1fr;
            gap: 40px;
            margin: 40px auto;
            max-width: 500px;
        }}
        .stat-cube {{
            height: 150px;
            width: 150px;
            margin: 0 auto;
            perspective: 600px;
        }}
        .cube {{
            width: 100%;
            height: 100%;
            position: relative;
            transform-style: preserve-3d;
            transform: rotateX(20deg) rotateY(20deg);
            transition: transform 0.8s ease-out;
            --cube-color: #0066cc;
        }}
        .cube-face {{
            position: absolute;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background-color: rgba(0, 0, 0, 0.9);
            border: 2px solid var(--cube-color);
            backface-visibility: visible;
            box-sizing: border-box;
            padding: 10px;
        }}
        /* Create all six faces of the cube */
        .cube-face.front {{
            transform: translateZ(75px);
        }}
        .cube-face.back {{
            transform: rotateY(180deg) translateZ(75px);
        }}
        .cube-face.right {{
            transform: rotateY(90deg) translateZ(75px);
        }}
        .cube-face.left {{
            transform: rotateY(-90deg) translateZ(75px);
        }}
        .cube-face.top {{
            transform: rotateX(90deg) translateZ(75px);
        }}
        .cube-face.bottom {{
            transform: rotateX(-90deg) translateZ(75px);
        }}
        /* Add cube edges */
        .cube::after {{
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            border: 2px solid rgba(0, 102, 204, 0.5);
            box-sizing: border-box;
            transform: translateZ(-75px);
        }}
        /* Add color change animation */
        @keyframes colorPulse {{
            0% {{ border-color: var(--highlight-color); }}
            50% {{ border-color: var(--highlight-color); box-shadow: 0 0 15px var(--highlight-color); }}
            100% {{ border-color: var(--highlight-color); }}
        }}
        
        /* 360-degree rotation animation */
        @keyframes rotate360 {{
            0% {{ transform: rotateY(0deg); }}
            100% {{ transform: rotateY(360deg); }}
        }}
        
        .rotate360 {{
            animation: rotate360 1.5s ease-in-out;
        }}
        
        .color-change .cube-face {{
            animation: colorPulse 1.5s ease-in-out;
        }}
        
        /* Hover effect */
        .stat-cube:hover .cube {{
            transform: rotateX(25deg) rotateY(25deg);
        }}
        .value {{
            font-size: 24px;
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 5px;
        }}
        .label {{
            font-size: 12px;
            color: #999;
            text-transform: uppercase;
        }}
        .reward-address-title {{
            font-size: 20px;
            color: #0066cc;
            margin-bottom: 15px;
            text-align: center;
            font-weight: normal;
            font-family: 'Consolas', 'Courier New', monospace;
        }}
        /* Terminal-style command history */
        .terminal-history {{
            background-color: #0c0c0c;
            border: none;
            border-radius: 0;
            font-family: 'Consolas', 'Courier New', monospace;
            color: #f0f0f0;
            padding: 10px;
            position: relative;
            overflow: hidden;
        }}
        .stratum-history-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 12px;
            background-color: #0c0c0c;
            border: none;
        }}
        .stratum-history-table th, 
        .stratum-history-table td {{
            padding: 6px;
            text-align: left;
            border: none;
        }}
        .stratum-history-table th {{
            background-color: #1a1a1a;
            font-size: 13px;
            color: #0066cc;
            border: none;
        }}
        .stratum-history-table tr {{
            transition: background-color 0.3s;
            border: none;
        }}
        .stratum-history-table tr.miner-command {{
            background-color: #0066cc;
            color: #000000;
            font-weight: bold;
        }}
        .stratum-history-table tr.pool-command {{
            background-color: #0c0c0c;
            color: #0066cc;
        }}
        .new-row {{
            animation: slideDown 0.5s ease-out;
        }}
        @keyframes slideDown {{
            from {{ transform: translateY(-100%); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}
        .row-exit {{
            animation: slideDownExit 0.5s ease-out;
            animation-fill-mode: forwards;
        }}
        @keyframes slideDownExit {{
            from {{ transform: translateY(0); opacity: 1; }}
            to {{ transform: translateY(100%); opacity: 0; }}
        }}
        /* Typing effect */
        .typing-effect {{
            position: relative;
            overflow: hidden;
            border-right: 0.15em solid #0066cc;
            white-space: nowrap;
            animation: typing 0.5s steps(30, end), blink-caret 0.75s step-end infinite;
        }}
        
        @keyframes typing {{
            from {{ width: 0 }}
            to {{ width: 100% }}
        }}
        
        @keyframes blink-caret {{
            from, to {{ border-color: transparent }}
            50% {{ border-color: #0066cc }}
        }}
    </style>
</head>
<body>
    <div class="card">
        <h2>Miner Agent: {miner_agent} <span class="bitcoin-logo">₿</span></h2>
    </div>
    
    <div class="card">
        <div class="stats-container">
            <div class="stat-cube" id="block-number-cube">
                <div class="cube">
                    <div class="cube-face front">
                        <div class="value">{block_number}</div>
                        <div class="label">Block Number</div>
                    </div>
                    <div class="cube-face back">
                        <div class="value">{block_number}</div>
                        <div class="label">Block Number</div>
                    </div>
                    <div class="cube-face right"></div>
                    <div class="cube-face left"></div>
                    <div class="cube-face top"></div>
                    <div class="cube-face bottom"></div>
                </div>
            </div>
            
            <div class="stat-cube" id="time-since-share-cube">
                <div class="cube">
                    <div class="cube-face front">
                        <div class="value">{time_since_last_share if 'time_since_last_share' in locals() else 'N/A'}</div>
                        <div class="label">Time Since Share</div>
                    </div>
                    <div class="cube-face back">
                        <div class="value">{time_since_last_share if 'time_since_last_share' in locals() else 'N/A'}</div>
                        <div class="label">Time Since Share</div>
                    </div>
                    <div class="cube-face right"></div>
                    <div class="cube-face left"></div>
                    <div class="cube-face top"></div>
                    <div class="cube-face bottom"></div>
                </div>
            </div>
            
            <div class="stat-cube" id="valid-shares-cube">
                <div class="cube">
                    <div class="cube-face front">
                        <div class="value">{stats.get('shares', {}).get('valid', 0) if 'stats' in locals() else pool_stats.get('valid_shares', 0)}</div>
                        <div class="label">Valid Shares</div>
                    </div>
                    <div class="cube-face back">
                        <div class="value">{stats.get('shares', {}).get('valid', 0) if 'stats' in locals() else pool_stats.get('valid_shares', 0)}</div>
                        <div class="label">Valid Shares</div>
                    </div>
                    <div class="cube-face right"></div>
                    <div class="cube-face left"></div>
                    <div class="cube-face top"></div>
                    <div class="cube-face bottom"></div>
                </div>
            </div>
            
            <div class="stat-cube" id="mining-difficulty-cube">
                <div class="cube">
                    <div class="cube-face front">
                        <div class="value">{mining_difficulty}</div>
                        <div class="label">Mining Difficulty</div>
                    </div>
                    <div class="cube-face back">
                        <div class="value">{mining_difficulty}</div>
                        <div class="label">Mining Difficulty</div>
                    </div>
                    <div class="cube-face right"></div>
                    <div class="cube-face left"></div>
                    <div class="cube-face top"></div>
                    <div class="cube-face bottom"></div>
                </div>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2 class="reward-address-title">Reward Address: {full_reward_address}</h2>
    </div>
    
    <div class="footer">
        <!-- Footer content removed -->
    </div>
    
    <script>
        // Function to update cube values and apply appropriate color
        function updateCubeValue(cubeId, newValue) {{
            const cube = document.getElementById(cubeId);
            if (!cube) return;
            
            // Get the current value
            const cubeValue = cube.querySelector('.cube-face.front .value').textContent.trim();
            
            // Check if the value has changed
            if (cubeValue !== newValue) {{
                // Use orange color for block height cube, blue for others
                const color = cubeId === 'block-number-cube' ? '#FF8000' : '#0066cc';
                
                // Get all cube elements
                const cubeElement = cube.querySelector('.cube');
                const allFaces = cube.querySelectorAll('.cube-face');
                
                // Apply color to all faces and borders
                allFaces.forEach(face => {{
                    face.style.borderColor = color;
                }});
                
                // Apply color to the cube itself
                cubeElement.style.setProperty('--cube-color', color);
                
                // Apply color to the value text
                const frontValue = cube.querySelector('.cube-face.front .value');
                const backValue = cube.querySelector('.cube-face.back .value');
                frontValue.style.color = color;
                backValue.style.color = color;
                
                // Apply rotation effect for all cubes
                const rotateX = Math.random() * 360;
                const rotateY = Math.random() * 360;
                const rotateZ = Math.random() * 360;
                
                // Apply the rotation
                cubeElement.style.transform = 'rotateX(' + rotateX + 'deg) rotateY(' + rotateY + 'deg) rotateZ(' + rotateZ + 'deg)';
                
                // Reset the rotation after animation
                setTimeout(() => {{
                    cubeElement.style.transform = 'rotateX(20deg) rotateY(20deg)';
                    
                    // Update the value after rotation
                    frontValue.textContent = newValue;
                    backValue.textContent = newValue;
                }}, 800);
            }}
        }}
        
        // Auto-refresh every 5 seconds
        setInterval(function() {{
            fetch(window.location.href)
                .then(response => response.text())
                .then(html => {{
                    // Parse the HTML
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    
                    // Update each stat cube if value has changed
                    updateCubeValue('block-number-cube', doc.getElementById('block-number-cube').querySelector('.cube-face.front .value').textContent.trim());
                    updateCubeValue('time-since-share-cube', doc.getElementById('time-since-share-cube').querySelector('.cube-face.front .value').textContent.trim());
                    updateCubeValue('valid-shares-cube', doc.getElementById('valid-shares-cube').querySelector('.cube-face.front .value').textContent.trim());
                    updateCubeValue('mining-difficulty-cube', doc.getElementById('mining-difficulty-cube').querySelector('.cube-face.front .value').textContent.trim());
                }});
        }}, 5000);
        
        // Initialize all cubes with the correct color
        document.addEventListener('DOMContentLoaded', function() {{
            // Get all stat cubes
            const statCubes = document.querySelectorAll('.stat-cube');
            
            statCubes.forEach(cube => {{
                const valueElement = cube.querySelector('.cube-face.front .value');
                if (valueElement) {{
                    // Use orange for block height cube, blue for others
                    const color = cube.id === 'block-number-cube' ? '#FF8000' : '#0066cc';
                    
                    // Get all cube elements
                    const cubeElement = cube.querySelector('.cube');
                    const allFaces = cube.querySelectorAll('.cube-face');
                    
                    // Apply color to all faces and borders
                    allFaces.forEach(face => {{
                        face.style.borderColor = color;
                    }});
                    
                    // Apply color to the cube itself
                    cubeElement.style.setProperty('--cube-color', color);
                    
                    // Apply color to the value text
                    const frontValue = cube.querySelector('.cube-face.front .value');
                    const backValue = cube.querySelector('.cube-face.back .value');
                    if (frontValue) frontValue.style.color = color;
                    if (backValue) backValue.style.color = color;
                }}
            }});
        }});
    </script>
</body>
</html>
"""
        
        return html.encode('utf-8')

def bits_to_difficulty(bits):
    """Convert bits to difficulty"""
    if not bits:
        return "Unknown"
    try:
        # Convert bits to target
        exp = bits >> 24
        mant = bits & 0xFFFFFF
        target = mant * (2 ** (8 * (exp - 3)))
        
        # Calculate difficulty
        diff1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
        difficulty = diff1 / target
        return f"{difficulty:.2f}"
    except Exception:
        return "Unknown"

def setup_web_interface(factory, port=8080):
    """Set up a web interface for the mining pool"""
    # Create root resource
    root = resource.Resource()
    
    # Add HTML stats page
    root.putChild(b'', PoolStatsPage(factory))
    
    # Add JSON API endpoint
    root.putChild(b'api', JSONStatsResource(factory))
    
    # Create and start the web server
    site = server.Site(root)
    reactor.listenTCP(port, site)
    
    return f"http://localhost:{port}"
