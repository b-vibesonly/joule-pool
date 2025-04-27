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
                'hashrate': stats.get('hashrate', 0),
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
        
        # Format worker stats as HTML table rows
        worker_rows = ""
        for worker, stats in worker_stats.items():
            worker_rows += f"""
            <tr>
                <td>{worker}</td>
                <td>{stats.get('shares', {}).get('valid', 0)}</td>
                <td>{stats.get('shares', {}).get('invalid', 0)}</td>
                <td>{stats.get('blocks_found', 0)}</td>
                <td>{stats.get('hashrate', 0):.2f} H/s</td>
                <td>{datetime.fromtimestamp(stats.get('last_share_time', 0)).strftime('%Y-%m-%d %H:%M:%S') if stats.get('last_share_time', 0) > 0 else 'Never'}</td>
            </tr>
            """
        
        # Get current job information
        current_job_info = "No active job"
        if self.factory.jobs:
            # Get the latest job
            job_id = max(self.factory.jobs.keys())
            job = self.factory.jobs[job_id]
            
            # Format job info
            current_job_info = f"""
            <p><strong>Current Job:</strong> {job_id}</p>
            <p><strong>Height:</strong> {job.get('height', 'Unknown')}</p>
            <p><strong>Difficulty:</strong> {bits_to_difficulty(job.get('bits', 0))}</p>
            <p><strong>Transactions:</strong> {len(job.get('transactions', []))}</p>
            """
        
        # Create HTML directly
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bitcoin Solo Mining Pool - Statistics</title>
    <style>
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        h1, h2, h3 {{
            color: #0066cc;
        }}
        .card {{
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }}
        .stat-box {{
            background: #f9f9f9;
            border-radius: 4px;
            padding: 15px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 24px;
            font-weight: bold;
            color: #0066cc;
        }}
        .stat-label {{
            font-size: 14px;
            color: #666;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f2f2f2;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .refresh-button {{
            background-color: #0066cc;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-bottom: 20px;
        }}
        .refresh-button:hover {{
            background-color: #0052a3;
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
        }}
        .auto-refresh label {{
            margin-right: 10px;
        }}
        .footer {{
            text-align: center;
            margin-top: 30px;
            color: #666;
            font-size: 14px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Bitcoin Solo Mining Pool</h1>
        <div class="auto-refresh">
            <label for="auto-refresh">Auto refresh:</label>
            <select id="auto-refresh" onchange="setAutoRefresh()">
                <option value="0">Off</option>
                <option value="5" selected>5 seconds</option>
                <option value="15">15 seconds</option>
                <option value="30">30 seconds</option>
                <option value="60">1 minute</option>
            </select>
        </div>
    </div>
    
    <button class="refresh-button" onclick="location.reload()">Refresh Statistics</button>
    
    <div class="card">
        <h2>Pool Information</h2>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-value">Current Job</div>
                <div class="stat-label">{current_job_info}</div>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>Pool Statistics</h2>
        <div class="stats-grid">
            <div class="stat-box">
                <div class="stat-value">{pool_stats.get('hashrate', 0):.2f} H/s</div>
                <div class="stat-label">Pool Hashrate</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pool_stats.get('total_shares', 0)}</div>
                <div class="stat-label">Total Shares</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pool_stats.get('valid_shares', 0)}</div>
                <div class="stat-label">Valid Shares</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pool_stats.get('invalid_shares', 0)}</div>
                <div class="stat-label">Invalid Shares</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pool_stats.get('blocks_found', 0)}</div>
                <div class="stat-label">Blocks Found</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pool_stats.get('connected_miners', 0)}</div>
                <div class="stat-label">Connected Miners</div>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>Worker Statistics</h2>
        <table>
            <thead>
                <tr>
                    <th>Worker</th>
                    <th>Valid Shares</th>
                    <th>Invalid Shares</th>
                    <th>Blocks Found</th>
                    <th>Hashrate</th>
                    <th>Last Share</th>
                </tr>
            </thead>
            <tbody>
                {worker_rows}
            </tbody>
        </table>
    </div>
    
    <div class="footer">
        <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        <p>Bitcoin Solo Mining Pool | <a href="/api">JSON API</a></p>
    </div>
    
    <script>
        let refreshInterval;
        
        function setAutoRefresh() {{
            // Clear existing interval
            if (refreshInterval) {{
                clearInterval(refreshInterval);
            }}
            
            // Get selected refresh time
            const refreshTime = document.getElementById('auto-refresh').value;
            
            // Set new interval if not disabled
            if (refreshTime > 0) {{
                refreshInterval = setInterval(() => {{
                    location.reload();
                }}, refreshTime * 1000);
            }}
        }}
        
        // Initialize auto-refresh
        setAutoRefresh();
    </script>
</body>
</html>"""
        
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
