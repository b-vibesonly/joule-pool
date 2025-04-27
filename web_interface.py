#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
from twisted.web import server, resource, static
from twisted.web.template import Element, renderer, XMLFile, flattenString
from twisted.internet import reactor, task
from twisted.python.filepath import FilePath

class PoolStatsElement(Element):
    """Element for rendering pool statistics"""
    
    loader = XMLFile(FilePath(os.path.join(os.path.dirname(__file__), 'templates', 'stats.html')))
    
    def __init__(self, factory):
        self.factory = factory
        super(PoolStatsElement, self).__init__()
    
    @renderer
    def pool_stats(self, request, tag):
        """Render pool statistics"""
        stats = self.factory.stats.get_stats()
        
        # Update tag attributes with stats
        tag.fillSlots(
            uptime=stats['uptime_human'],
            hashrate=stats['hashrate_human'],
            valid_shares=stats['shares']['valid'],
            invalid_shares=stats['shares']['invalid'],
            stale_shares=stats['shares']['stale'],
            blocks_found=stats['blocks_found'],
            connected_miners=stats['clients']
        )
        
        return tag
    
    @renderer
    def worker_stats(self, request, tag):
        """Render worker statistics"""
        worker_stats = self.factory.stats.get_worker_stats()
        
        for worker_name, stats in worker_stats.items():
            # Clone the tag for each worker
            worker_tag = tag.clone()
            
            # Fill in worker stats
            worker_tag.fillSlots(
                worker_name=worker_name,
                hashrate=stats['hashrate_human'],
                valid_shares=stats['shares']['valid'],
                invalid_shares=stats['shares']['invalid'],
                stale_shares=stats['shares']['stale'],
                difficulty=f"{stats['difficulty']:.2f}",
                last_share=stats['last_share_ago']
            )
            
            yield worker_tag
        
        # If no workers, return empty message
        if not worker_stats:
            empty_tag = tag.clone()
            empty_tag.fillSlots(
                worker_name="No miners connected",
                hashrate="0 H/s",
                valid_shares="0",
                invalid_shares="0",
                stale_shares="0",
                difficulty="0",
                last_share="Never"
            )
            yield empty_tag

class PoolStatsPage(resource.Resource):
    """Resource for the pool statistics page"""
    
    isLeaf = True
    
    def __init__(self, factory):
        self.factory = factory
        self.element = PoolStatsElement(factory)
        resource.Resource.__init__(self)
    
    def render_GET(self, request):
        request.setHeader(b"content-type", b"text/html; charset=utf-8")
        
        d = flattenString(request, self.element)
        d.addCallback(lambda html: request.write(html))
        d.addCallback(lambda _: request.finish())
        
        return server.NOT_DONE_YET

class JSONStatsResource(resource.Resource):
    """Resource for JSON API access to pool statistics"""
    
    isLeaf = True
    
    def __init__(self, factory):
        self.factory = factory
        resource.Resource.__init__(self)
    
    def render_GET(self, request):
        request.setHeader(b"content-type", b"application/json")
        
        # Get stats from the pool
        stats = self.factory.stats.get_stats()
        worker_stats = self.factory.stats.get_worker_stats()
        
        # Network info
        network_info = {}
        if self.factory.current_block_template:
            network_info = {
                'height': self.factory.current_block_template.get('height', 0),
                'difficulty': self.factory.current_block_template.get('difficulty', 0),
                'bits': self.factory.current_block_template.get('bits', ''),
                'previous_block': self.factory.current_block_template.get('previousblockhash', '')
            }
        
        # Combine stats into a single JSON response
        response = {
            'pool': stats,
            'workers': worker_stats,
            'network': network_info,
            'pool_address': self.factory.pool_address,
            'coinbase_message': self.factory.coinbase_message.decode()
        }
        
        return json.dumps(response, indent=4).encode('utf-8')

def create_templates_directory():
    """Create the templates directory if it doesn't exist"""
    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    if not os.path.exists(templates_dir):
        os.makedirs(templates_dir)
    
    # Create the stats.html template
    stats_html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bitcoin Solo Mining Pool - Statistics</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        h1, h2, h3 {
            color: #0066cc;
        }
        .card {
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            padding: 20px;
            margin-bottom: 20px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
            gap: 15px;
        }
        .stat-box {
            background: #f9f9f9;
            border-radius: 4px;
            padding: 15px;
            text-align: center;
        }
        .stat-value {
            font-size: 24px;
            font-weight: bold;
            color: #0066cc;
        }
        .stat-label {
            font-size: 14px;
            color: #666;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .refresh-button {
            background-color: #0066cc;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 4px;
            cursor: pointer;
            font-size: 16px;
            margin-bottom: 20px;
        }
        .refresh-button:hover {
            background-color: #0052a3;
        }
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
        }
        .auto-refresh {
            display: flex;
            align-items: center;
        }
        .auto-refresh label {
            margin-right: 10px;
        }
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
        <h2>Pool Statistics</h2>
        <div class="stats-grid" nevow:render="pool_stats">
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="hashrate" /></div>
                <div class="stat-label">Pool Hashrate</div>
            </div>
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="valid_shares" /></div>
                <div class="stat-label">Valid Shares</div>
            </div>
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="invalid_shares" /></div>
                <div class="stat-label">Invalid Shares</div>
            </div>
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="stale_shares" /></div>
                <div class="stat-label">Stale Shares</div>
            </div>
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="blocks_found" /></div>
                <div class="stat-label">Blocks Found</div>
            </div>
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="connected_miners" /></div>
                <div class="stat-label">Connected Miners</div>
            </div>
            <div class="stat-box">
                <div class="stat-value"><nevow:slot name="uptime" /></div>
                <div class="stat-label">Uptime</div>
            </div>
        </div>
    </div>
    
    <div class="card">
        <h2>Worker Statistics</h2>
        <table>
            <thead>
                <tr>
                    <th>Worker</th>
                    <th>Hashrate</th>
                    <th>Valid Shares</th>
                    <th>Invalid Shares</th>
                    <th>Stale Shares</th>
                    <th>Difficulty</th>
                    <th>Last Share</th>
                </tr>
            </thead>
            <tbody>
                <tr nevow:render="worker_stats">
                    <td><nevow:slot name="worker_name" /></td>
                    <td><nevow:slot name="hashrate" /></td>
                    <td><nevow:slot name="valid_shares" /></td>
                    <td><nevow:slot name="invalid_shares" /></td>
                    <td><nevow:slot name="stale_shares" /></td>
                    <td><nevow:slot name="difficulty" /></td>
                    <td><nevow:slot name="last_share" /></td>
                </tr>
            </tbody>
        </table>
    </div>
    
    <script>
        let refreshInterval;
        
        function setAutoRefresh() {
            // Clear existing interval
            if (refreshInterval) {
                clearInterval(refreshInterval);
            }
            
            // Get selected refresh time
            const refreshTime = document.getElementById('auto-refresh').value;
            
            // Set new interval if not disabled
            if (refreshTime > 0) {
                refreshInterval = setInterval(() => {
                    location.reload();
                }, refreshTime * 1000);
            }
        }
        
        // Initialize auto-refresh
        setAutoRefresh();
    </script>
</body>
</html>
    """
    
    stats_template_path = os.path.join(templates_dir, 'stats.html')
    if not os.path.exists(stats_template_path):
        with open(stats_template_path, 'w') as f:
            f.write(stats_html)

def setup_web_interface(factory, port=8080):
    """Set up a web interface for the mining pool"""
    # Create templates directory and files
    create_templates_directory()
    
    # Create root resource
    root = resource.Resource()
    
    # Add stats page
    root.putChild(b'', PoolStatsPage(factory))
    
    # Add JSON API endpoint
    root.putChild(b'api', JSONStatsResource(factory))
    
    # Create and start the web server
    site = server.Site(root)
    reactor.listenTCP(port, site)
    
    return f"http://localhost:{port}"

# If run directly, this will just create the template files
if __name__ == "__main__":
    create_templates_directory()
    print("Template files created successfully.")
