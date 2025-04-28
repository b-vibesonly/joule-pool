#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import time
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
        for cmd in pool_stats.get('stratum_command_history', [])[:5]:
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
        
        # Create HTML directly
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Mining Dashboard</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #f0f0f0;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #0c0c0c;
        }}
        h1, h2, h3 {{
            color: #0066cc;
        }}
        .card {{
            background: #0c0c0c;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #333;
        }}
        th {{
            background-color: #252525;
            color: #0066cc;
        }}
        tr:hover {{
            background-color: #252525;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }}
        .auto-refresh {{
            display: flex;
            align-items: center;
            color: #f0f0f0;
        }}
        .auto-refresh label {{
            margin-right: 10px;
        }}
        .auto-refresh select {{
            background-color: #333;
            color: #f0f0f0;
            border: 1px solid #444;
            padding: 5px;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: #888;
            font-size: 14px;
            display: none;
        }}
        .stats-container {{
            display: flex;
            flex-wrap: wrap;
            justify-content: space-around;
            gap: 40px;
            margin-bottom: 30px;
            margin-top: 60px;
        }}
        .stat-cube {{
            width: 200px;
            height: 200px;
            position: relative;
            perspective: 1200px;
        }}
        .cube {{
            width: 100%;
            height: 100%;
            position: relative;
            transform-style: preserve-3d;
            transition: transform 0.8s;
            transform: rotateX(15deg) rotateY(15deg);
        }}
        .cube-face {{
            position: absolute;
            width: 100%;
            height: 100%;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            background-color: rgba(40, 40, 40, 0.9);
            border: 2px solid #0066cc;
            backface-visibility: hidden;
        }}
        /* Create all six faces of the cube */
        .cube-face.front {{
            transform: translateZ(100px);
        }}
        .cube-face.back {{
            transform: rotateY(180deg) translateZ(100px);
        }}
        .cube-face.right {{
            transform: rotateY(90deg) translateZ(100px);
            opacity: 0.3;
        }}
        .cube-face.left {{
            transform: rotateY(-90deg) translateZ(100px);
            opacity: 0.3;
        }}
        .cube-face.top {{
            transform: rotateX(90deg) translateZ(100px);
            opacity: 0.3;
        }}
        .cube-face.bottom {{
            transform: rotateX(-90deg) translateZ(100px);
            opacity: 0.3;
        }}
        /* Add cube edges */
        .cube::after {{
            content: '';
            position: absolute;
            width: 100%;
            height: 100%;
            border: 2px solid rgba(0, 102, 204, 0.5);
            box-sizing: border-box;
            transform: translateZ(-100px);
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
        .stat-value {{
            font-size: 32px;
            font-weight: bold;
            color: #0066cc;
            margin-bottom: 15px;
        }}
        .stat-label {{
            font-size: 16px;
            color: #ccc;
            font-weight: 500;
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
    <div class="header">
        <div></div>
        <div></div>
    </div>
    
    <div class="card">
        <div class="stats-container">
            <div class="stat-cube" id="block-number-cube">
                <div class="cube">
                    <div class="cube-face front">
                        <div class="stat-value">{block_number}</div>
                        <div class="stat-label">Block Number</div>
                    </div>
                    <div class="cube-face back">
                        <div class="stat-value">{block_number}</div>
                        <div class="stat-label">Block Number</div>
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
                        <div class="stat-value" id="time-since-share-value">
                            {time_since_last_share if 'time_since_last_share' in locals() else 'N/A'}
                        </div>
                        <div class="stat-label">Time Since Last Share</div>
                    </div>
                    <div class="cube-face back">
                        <div class="stat-value" id="time-since-share-value-back">
                            {time_since_last_share if 'time_since_last_share' in locals() else 'N/A'}
                        </div>
                        <div class="stat-label">Time Since Last Share</div>
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
                        <div class="stat-value">
                            {stats.get('shares', {}).get('valid', 0) if 'stats' in locals() else pool_stats.get('valid_shares', 0)}
                        </div>
                        <div class="stat-label">Valid Shares</div>
                    </div>
                    <div class="cube-face back">
                        <div class="stat-value">
                            {stats.get('shares', {}).get('valid', 0) if 'stats' in locals() else pool_stats.get('valid_shares', 0)}
                        </div>
                        <div class="stat-label">Valid Shares</div>
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
        <div class="terminal-history">
            <table class="stratum-history-table">
                <thead>
                    <tr>
                        <th>Time</th>
                        <th>Sender</th>
                        <th>Method</th>
                        <th>Parameters</th>
                    </tr>
                </thead>
                <tbody id="command-history-tbody">
                    {command_history_rows}
                </tbody>
            </table>
        </div>
    </div>
    
    <div class="footer">
        <!-- Footer content removed -->
    </div>
    
    <script>
        // Set fixed refresh interval of 5 seconds
        let refreshInterval = setInterval(() => {{
            fetch(window.location.href)
                .then(response => response.text())
                .then(html => {{
                    const parser = new DOMParser();
                    const doc = parser.parseFromString(html, 'text/html');
                    
                    // Update each stat cube if value has changed
                    updateCubeIfChanged('block-number-cube', doc);
                    updateCubeIfChanged('time-since-share-cube', doc);
                    updateCubeIfChanged('valid-shares-cube', doc);
                    
                    // Function to update command history
                    function updateCommandHistory() {{
                        // Fetch the updated HTML
                        fetch('/command_history')
                            .then(response => response.text())
                            .then(html => {{
                                // Parse the HTML
                                const parser = new DOMParser();
                                const doc = parser.parseFromString(html, 'text/html');
                                
                                // Get new command history data
                                const newHistoryRows = Array.from(doc.querySelectorAll('#command-history-tbody tr'));
                                const currentHistoryRows = Array.from(document.querySelectorAll('#command-history-tbody tr'));
                                
                                // Create a map to track unique commands by their content
                                const uniqueCommands = new Map();
                                
                                // Process new rows to get unique commands (limit to 10)
                                for (const row of newHistoryRows) {{
                                    // Create a key from timestamp, sender, method, and params to identify unique commands
                                    const timestamp = row.cells[0].textContent.trim();
                                    const sender = row.cells[1].textContent.trim();
                                    const method = row.cells[2].textContent.trim();
                                    const params = row.cells[3].textContent.trim();
                                    const key = timestamp + '-' + sender + '-' + method + '-' + params;
                                    
                                    // Only add if we don't already have this command
                                    if (!uniqueCommands.has(key)) {{
                                        uniqueCommands.set(key, row);
                                        
                                        // Limit to 10 unique commands
                                        if (uniqueCommands.size >= 10) {{
                                            break;
                                        }}
                                    }}
                                }}
                                
                                // Get the unique rows in the correct order
                                const limitedNewRows = Array.from(uniqueCommands.values());
                                
                                // Check if there are new commands by comparing first row's content
                                let hasNewCommands = false;
                                
                                if (currentHistoryRows.length === 0 || limitedNewRows.length === 0) {{
                                    hasNewCommands = true;
                                }} else {{
                                    const currentFirstRow = currentHistoryRows[0];
                                    const newFirstRow = limitedNewRows[0];
                                    
                                    hasNewCommands = currentFirstRow.textContent.trim() !== newFirstRow.textContent.trim();
                                }}
                                
                                // If there are new commands, update the table
                                if (hasNewCommands) {{
                                    // Get the table body
                                    const tbody = document.getElementById('command-history-tbody');
                                    
                                    // Clear the current content
                                    tbody.innerHTML = '';
                                    
                                    // Process one row at a time with delay
                                    const processNextRow = (index) => {{
                                        if (index >= limitedNewRows.length) return;
                                        
                                        // Clone the row from the new data
                                        const newRow = limitedNewRows[index].cloneNode(true);
                                        newRow.classList.add('new-row');
                                        
                                        // Insert at the top
                                        tbody.appendChild(newRow);
                                        
                                        // Process the next row after delay
                                        setTimeout(() => processNextRow(index + 1), 250);
                                    }};
                                    
                                    // Start processing rows
                                    processNextRow(0);
                                }}
                            }})
                            .catch(error => console.error('Error updating command history:', error));
                    }}
                    
                    // Call the function to update command history
                    updateCommandHistory();
                }});
        }}, 5000);
        
        function updateCubeIfChanged(cubeId, newDoc) {{
            const cube = document.getElementById(cubeId);
            const cubeValue = cube.querySelector('.stat-value').textContent.trim();
            const newValue = newDoc.getElementById(cubeId).querySelector('.stat-value').textContent.trim();
            
            if (cubeValue !== newValue) {{
                // Special handling for block number cube - no effects, just update value
                if (cubeId === 'block-number-cube') {{
                    // Update value immediately
                    cube.querySelector('.cube-face.front .stat-value').textContent = newValue;
                    cube.querySelector('.cube-face.back .stat-value').textContent = newValue;
                    
                    // Change color based on even/odd number
                    const blockNumber = parseInt(newValue);
                    const isEven = blockNumber % 2 === 0;
                    const color = isEven ? '#0066cc' : '#FF8000'; // Blue for even, Orange for odd
                    
                    // Apply color to the value text
                    const frontValue = cube.querySelector('.cube-face.front .stat-value');
                    const backValue = cube.querySelector('.cube-face.back .stat-value');
                    frontValue.style.color = color;
                    backValue.style.color = color;
                    
                    // Apply color to the cube borders
                    const faces = cube.querySelectorAll('.cube-face');
                    faces.forEach(face => {{
                        face.style.borderColor = color;
                    }});
                }} else {{
                    // For other cubes, use random rotation
                    // Generate random rotation values
                    const randomX = Math.floor(Math.random() * 360) - 180;
                    const randomY = Math.floor(Math.random() * 360) - 180;
                    const randomZ = Math.floor(Math.random() * 90) - 45;
                    
                    // Apply random rotation animation
                    cube.querySelector('.cube').style.transform = 'rotateX(' + randomX + 'deg) rotateY(' + randomY + 'deg) rotateZ(' + randomZ + 'deg)';
                    
                    // Update back face value
                    setTimeout(() => {{
                        cube.querySelector('.cube-face.back .stat-value').textContent = newValue;
                        
                        // Reset to original position after full rotation
                        setTimeout(() => {{
                            cube.querySelector('.cube').style.transform = 'rotateX(15deg) rotateY(15deg)';
                            cube.querySelector('.cube-face.front .stat-value').textContent = newValue;
                        }}, 800);
                    }}, 400);
                }}
            }}
        }}
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
