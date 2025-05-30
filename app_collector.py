import os
import sqlite3
import time
import json
import threading
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, render_template_string
from ssh_collector import SSHLogCollector
from incremental_updater import IncrementalUpdater

app = Flask(__name__)
DB_PATH = './data/monitor.db'

collector = SSHLogCollector()
updater = IncrementalUpdater(DB_PATH)

# Import the enhanced statistics module
try:
    from enhanced_statistics import EnhancedStatistics
    stats_manager = EnhancedStatistics(DB_PATH)
except ImportError:
    stats_manager = None

def init_db():
    os.makedirs('./data', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    
    conn.execute('''CREATE TABLE IF NOT EXISTS servers 
                    (name TEXT PRIMARY KEY, ip TEXT, sent INTEGER, received INTEGER, last_update TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS metadata 
                    (key TEXT PRIMARY KEY, value TEXT)''')
    conn.execute('''CREATE TABLE IF NOT EXISTS daily_stats 
                    (date TEXT, server TEXT, sent INTEGER, received INTEGER, 
                     PRIMARY KEY (date, server))''')
    conn.execute('''CREATE TABLE IF NOT EXISTS collection_log 
                    (timestamp TEXT, server TEXT, status TEXT, message TEXT)''')
    
    conn.commit()
    conn.close()
    
    updater.init_incremental_tables()
    if stats_manager:
        stats_manager.init_statistics_tables()

def log_collection_event(server, status, message):
    conn = sqlite3.connect(DB_PATH)
    conn.execute('INSERT INTO collection_log VALUES (?, ?, ?, ?)',
                (datetime.now().isoformat(), server, status, message))
    conn.commit()
    conn.close()

def collect_logs_background():
    try:
        print("🚀 Starting SSH log collection from all servers...")
        log_collection_event("ALL", "START", "Starting SSH log collection from all servers")
        
        collection_result = collector.collect_all_logs()
        
        if collection_result["success"]:
            print(f"✅ Log collection completed: {collection_result['total_files']} files from {collection_result['successful_servers']} servers")
            log_collection_event("ALL", "SUCCESS", 
                f"Log collection completed: {collection_result['total_files']} files from {collection_result['successful_servers']}/{collection_result['total_servers']} servers")
            
            print("⚡ Starting incremental data processing...")
            update_result = updater.incremental_update_all()
            
            # Update enhanced statistics
            if stats_manager:
                print("📊 Updating enhanced statistics...")
                stats_manager.update_all_statistics()
            
            log_collection_event("ALL", "UPDATE", 
                f"Incremental update: {update_result['new_exchanges']} new exchanges, {update_result['new_received']} new received files")
            
            print(f"📊 Processing completed: {update_result}")
            return True
        else:
            error_msg = f"Log collection failed: {collection_result.get('error', 'Unknown error')}"
            print(f"❌ {error_msg}")
            log_collection_event("ALL", "FAILED", error_msg)
            return False
            
    except Exception as e:
        error_msg = f"Collection error: {str(e)}"
        print(f"❌ {error_msg}")
        log_collection_event("ALL", "ERROR", error_msg)
        return False

# Enhanced HTML template with advanced graphics
ENHANCED_HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>VM Exchange Monitor - Advanced Statistics</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/chartjs-adapter-date-fns@3.0.0/dist/chartjs-adapter-date-fns.bundle.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/d3@7.8.5/dist/d3.min.js"></script>
    <style>
        /* Previous styles plus new advanced graphics styles */
        *{margin:0;padding:0;box-sizing:border-box}
        body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f1f5f9;padding:20px;color:#334155}
        .container{max-width:1600px;margin:0 auto}
        .card{background:white;padding:20px;margin:15px 0;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.08);border:1px solid #e2e8f0}
        .header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:white;padding:20px;border-radius:12px}
        .stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;margin-bottom:20px}
        .stat{text-align:center;background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);color:white;padding:20px;border-radius:12px;box-shadow:0 4px 12px rgba(79,70,229,0.3)}
        .stat h3{margin-bottom:8px;opacity:0.9;font-size:14px}
        .stat p{font-size:28px;font-weight:bold}
        .charts-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(400px,1fr));gap:20px;margin-bottom:20px}
        .chart-container{position:relative;height:350px;padding:15px}
        
        /* Advanced Graphics Styles */
        .heatmap-container{background:#fff;border-radius:8px;padding:15px;margin:10px 0}
        .network-graph{background:#fff;border-radius:8px;padding:15px;margin:10px 0;height:400px}
        .timeline-chart{background:#fff;border-radius:8px;padding:15px;margin:10px 0;height:300px}
        .radial-progress{background:#fff;border-radius:8px;padding:15px;margin:10px 0;height:300px;text-align:center}
        .gauge-container{background:#fff;border-radius:8px;padding:15px;margin:10px 0;height:250px}
        
        /* D3 Styling */
        .node{cursor:pointer}
        .link{stroke:#999;stroke-opacity:0.6}
        .node circle{stroke:#fff;stroke-width:1.5px}
        .node text{font:12px sans-serif;pointer-events:none;text-anchor:middle}
        
        /* Heatmap styling */
        .heatmap-cell{cursor:pointer;stroke:white;stroke-width:1px}
        .heatmap-label{font-size:12px;text-anchor:middle}
        
        /* Tabs and navigation */
        .tabs{display:flex;border-bottom:2px solid #e2e8f0;margin-bottom:20px;background:white;border-radius:8px 8px 0 0;overflow:hidden}
        .tab{padding:15px 25px;cursor:pointer;border-bottom:3px solid transparent;font-weight:500;transition:all 0.3s ease;background:white}
        .tab:hover{background:#f8fafc}
        .tab.active{border-bottom-color:#4f46e5;color:#4f46e5;background:#faf5ff}
        .tab-content{display:none;background:white;border-radius:0 0 8px 8px;padding:20px}
        .tab-content.active{display:block}
        
        /* Advanced controls */
        .controls{background:#f8fafc;padding:15px;border-radius:8px;margin:10px 0;display:flex;gap:15px;align-items:center;flex-wrap:wrap}
        .control-group{display:flex;align-items:center;gap:8px}
        .control-group label{font-weight:500;color:#475569}
        .control-group select,.control-group input{padding:8px 12px;border:1px solid #d1d5db;border-radius:6px;font-size:14px}
        
        /* Performance indicators */
        .perf-indicator{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:8px}
        .perf-good{background:#10b981}
        .perf-warning{background:#f59e0b}
        .perf-critical{background:#ef4444}
        
        /* Responsive */
        @media (max-width:768px){
            .charts-grid{grid-template-columns:1fr}
            .header{flex-direction:column;gap:10px;text-align:center}
            .controls{flex-direction:column;align-items:stretch}
        }
        
        /* Animation styles */
        .fade-in{animation:fadeIn 0.5s ease-in}
        @keyframes fadeIn{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}
        
        /* Tooltip styles */
        .tooltip{position:absolute;background:rgba(0,0,0,0.8);color:white;padding:8px 12px;border-radius:4px;font-size:12px;pointer-events:none;z-index:1000}
        
        /* Status indicators */
        .status-indicator{width:8px;height:8px;border-radius:50%;display:inline-block;margin-right:6px}
        .status-active{background:#10b981}
        .status-inactive{background:#ef4444}
        .status-warning{background:#f59e0b}
        
        /* Button enhancements */
        .btn{background:linear-gradient(135deg,#4f46e5 0%,#7c3aed 100%);color:white;padding:12px 24px;border:none;border-radius:8px;cursor:pointer;font-weight:500;margin:5px;transition:all 0.3s ease;box-shadow:0 2px 8px rgba(79,70,229,0.3)}
        .btn:hover{transform:translateY(-2px);box-shadow:0 4px 16px rgba(79,70,229,0.4)}
        .btn-success{background:linear-gradient(135deg,#10b981 0%,#059669 100%)}
        .btn-warning{background:linear-gradient(135deg,#f59e0b 0%,#d97706 100%)}
        .btn-info{background:linear-gradient(135deg,#06b6d4 0%,#0891b2 100%)}
        
        table{width:100%;border-collapse:collapse;margin-top:15px}
        th,td{padding:12px;text-align:left;border-bottom:1px solid #e2e8f0}
        th{background:#f8fafc;font-weight:600;color:#475569}
        tr:hover{background:#f8fafc}
        
        .loading{opacity:0.6}
        .status-success{color:#10b981;font-weight:bold}
        .status-failed{color:#ef4444;font-weight:bold}
        .status-pending{color:#f59e0b;font-weight:bold}
        .collection-status{background:#f0f9ff;border:1px solid #0ea5e9;padding:15px;border-radius:8px;margin:10px 0}
        .incremental-info{background:#f0fdf4;border:1px solid #10b981;padding:15px;border-radius:8px;margin:10px 0}
        .new-badge{background:#10b981;color:white;padding:3px 8px;border-radius:4px;font-size:11px;margin-left:8px}
        .cron-info{background:#fffbeb;border:1px solid #f59e0b;padding:15px;border-radius:8px;margin:10px 0}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div>
                <h1>📡 VM Exchange Monitor - Advanced Analytics</h1>
                <p style="opacity:0.9;margin-top:5px">Real-time monitoring with advanced data visualization</p>
            </div>
            <div>
                <button class="btn btn-success" onclick="collectLogs()">📥 Collect Logs</button>
                <button class="btn btn-info" onclick="incrementalRefresh()">⚡ Process Data</button>
                <button class="btn btn-warning" onclick="testConnectivity()">🔗 Test SSH</button>
                <button class="btn" onclick="refreshData()">🔄 Refresh</button>
            </div>
        </div>

        <div class="cron-info">
            <strong>📋 System Info:</strong> Advanced monitoring with real-time analytics, network graphs, heat maps, and performance metrics.
        </div>

        <div class="collection-status" id="collection-status">
            <strong>Collection Status:</strong> <span id="status-text">Ready to collect logs</span>
            <div id="collection-details" style="margin-top:10px;font-size:13px;color:#475569"></div>
        </div>

        <div class="incremental-info" id="incremental-info">
            <strong>📈 Processing Status:</strong> <span id="incremental-text">Click "Process Data" to analyze collected logs</span>
        </div>

        <!-- Key Performance Indicators -->
        <div class="stats">
            <div class="stat">
                <h3>📤 Total Files Sent</h3>
                <p id="total-sent">0</p>
            </div>
            <div class="stat">
                <h3>📥 Total Files Received</h3>
                <p id="total-received">0</p>
            </div>
            <div class="stat">
                <h3>🖥️ Active Servers</h3>
                <p id="server-count">0</p>
            </div>
            <div class="stat">
                <h3>🕒 Last Update</h3>
                <p id="last-collection" style="font-size:16px">Never</p>
            </div>
            <div class="stat">
                <h3>📊 Exchange Rate (24h)</h3>
                <p id="exchange-rate-24h">0</p>
            </div>
            <div class="stat">
                <h3>🚀 Avg Throughput</h3>
                <p id="avg-throughput" style="font-size:20px">0 MB/h</p>
            </div>
        </div>

        <!-- Advanced Analytics Tabs -->
        <div class="card">
            <div class="tabs">
                <div class="tab active" onclick="showTab('overview')">📊 Overview</div>
                <div class="tab" onclick="showTab('network')">🌐 Network Graph</div>
                <div class="tab" onclick="showTab('heatmap')">🔥 Activity Heatmap</div>
                <div class="tab" onclick="showTab('timeline')">📈 Timeline</div>
                <div class="tab" onclick="showTab('performance')">⚡ Performance</div>
                <div class="tab" onclick="showTab('analytics')">🧠 Analytics</div>
            </div>
            
            <!-- Overview Tab -->
            <div id="overview" class="tab-content active">
                <div class="controls">
                    <div class="control-group">
                        <label>Time Range:</label>
                        <select id="timeRange" onchange="updateTimeRange()">
                            <option value="24h">Last 24 Hours</option>
                            <option value="7d" selected>Last 7 Days</option>
                            <option value="30d">Last 30 Days</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label>View Mode:</label>
                        <select id="viewMode" onchange="updateViewMode()">
                            <option value="combined">Combined View</option>
                            <option value="sent">Sent Only</option>
                            <option value="received">Received Only</option>
                        </select>
                    </div>
                </div>
                
                <div class="charts-grid">
                    <div class="card">
                        <h4>📈 Server Activity Distribution</h4>
                        <div class="chart-container">
                            <canvas id="sentChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>📊 Data Flow Comparison</h4>
                        <div class="chart-container">
                            <canvas id="receivedChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>📅 Daily Activity Trend</h4>
                        <div class="chart-container">
                            <canvas id="dailyTrendChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>🕐 Hourly Pattern</h4>
                        <div class="chart-container">
                            <canvas id="hourlyPatternChart"></canvas>
                        </div>
                    </div>
                </div>
                
                <table>
                    <thead>
                        <tr><th>Server</th><th>IP</th><th>Files Sent</th><th>Files Received</th><th>Last Activity</th><th>Status</th><th>Performance</th></tr>
                    </thead>
                    <tbody id="server-table">
                        <tr><td colspan="7">Loading server data...</td></tr>
                    </tbody>
                </table>
            </div>
            
            <!-- Network Graph Tab -->
            <div id="network" class="tab-content">
                <div class="controls">
                    <div class="control-group">
                        <label>Layout:</label>
                        <select id="networkLayout" onchange="updateNetworkLayout()">
                            <option value="force">Force Layout</option>
                            <option value="circular">Circular</option>
                            <option value="hierarchical">Hierarchical</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label>Show Labels:</label>
                        <input type="checkbox" id="showLabels" checked onchange="toggleNetworkLabels()">
                    </div>
                </div>
                <div class="network-graph" id="networkGraph"></div>
                <div id="network-details"></div>
            </div>
            
            <!-- Heatmap Tab -->
            <div id="heatmap" class="tab-content">
                <div class="controls">
                    <div class="control-group">
                        <label>Metric:</label>
                        <select id="heatmapMetric" onchange="updateHeatmap()">
                            <option value="files">File Count</option>
                            <option value="bytes">Data Size</option>
                            <option value="frequency">Frequency</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label>Period:</label>
                        <select id="heatmapPeriod" onchange="updateHeatmap()">
                            <option value="hour">Hourly</option>
                            <option value="day">Daily</option>
                            <option value="week">Weekly</option>
                        </select>
                    </div>
                </div>
                <div class="heatmap-container" id="heatmapContainer"></div>
                <div id="heatmap-legend"></div>
            </div>
            
            <!-- Timeline Tab -->
            <div id="timeline" class="tab-content">
                <div class="controls">
                    <div class="control-group">
                        <label>Granularity:</label>
                        <select id="timelineGranularity" onchange="updateTimeline()">
                            <option value="minute">Per Minute</option>
                            <option value="hour">Per Hour</option>
                            <option value="day">Per Day</option>
                        </select>
                    </div>
                    <div class="control-group">
                        <label>Server Filter:</label>
                        <select id="serverFilter" onchange="updateTimeline()">
                            <option value="all">All Servers</option>
                            <option value="ubuntu-server-1">Ubuntu Server 1</option>
                            <option value="ubuntu-server-2">Ubuntu Server 2</option>
                            <option value="ubuntu-server-3">Ubuntu Server 3</option>
                        </select>
                    </div>
                </div>
                <div class="timeline-chart" id="timelineChart"></div>
                <div id="timeline-stats"></div>
            </div>
            
            <!-- Performance Tab -->
            <div id="performance" class="tab-content">
                <div class="charts-grid">
                    <div class="gauge-container">
                        <h4>🚀 System Throughput</h4>
                        <div id="throughputGauge"></div>
                    </div>
                    <div class="radial-progress">
                        <h4>📊 Server Load Distribution</h4>
                        <div id="loadProgress"></div>
                    </div>
                    <div class="card">
                        <h4>⚡ Performance Metrics</h4>
                        <div class="chart-container">
                            <canvas id="performanceChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>📈 Efficiency Trends</h4>
                        <div class="chart-container">
                            <canvas id="efficiencyChart"></canvas>
                        </div>
                    </div>
                </div>
                <div id="performance-details"></div>
            </div>
            
            <!-- Analytics Tab -->
            <div id="analytics" class="tab-content">
                <div class="charts-grid">
                    <div class="card">
                        <h4>📄 File Type Analysis</h4>
                        <div class="chart-container">
                            <canvas id="fileTypesChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>🔄 Server Pair Analysis</h4>
                        <div class="chart-container">
                            <canvas id="serverPairsChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>📊 Pattern Recognition</h4>
                        <div class="chart-container">
                            <canvas id="patternChart"></canvas>
                        </div>
                    </div>
                    <div class="card">
                        <h4>🎯 Predictive Analytics</h4>
                        <div class="chart-container">
                            <canvas id="predictiveChart"></canvas>
                        </div>
                    </div>
                </div>
                <div id="analytics-insights"></div>
            </div>
        </div>

        <!-- Recent Activity Log -->
        <div class="card">
            <h3>📋 Real-time Activity Stream</h3>
            <div id="collection-log" style="max-height:200px;overflow-y:auto;font-family:monospace;font-size:12px;background:#f8fafc;padding:15px;border-radius:8px">
                Loading activity history...
            </div>
        </div>
    </div>

    <script>
        // Global chart instances
        let charts = {};
        let networkGraph = null;
        let currentTimeRange = '7d';
        let currentViewMode = 'combined';
        
        // Chart.js default configuration
        Chart.defaults.font.family = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif';
        Chart.defaults.color = '#64748b';
        Chart.defaults.borderColor = '#e2e8f0';
        
        function initCharts() {
            // Initialize all charts
            initOverviewCharts();
            initPerformanceCharts();
            initAnalyticsCharts();
        }
        
        function initOverviewCharts() {
            // Sent files chart
            const sentCtx = document.getElementById('sentChart').getContext('2d');
            charts.sent = new Chart(sentCtx, {
                type: 'doughnut',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        backgroundColor: [
                            'rgba(59, 130, 246, 0.8)',
                            'rgba(16, 185, 129, 0.8)',
                            'rgba(245, 158, 11, 0.8)',
                            'rgba(139, 92, 246, 0.8)'
                        ],
                        borderColor: [
                            'rgb(59, 130, 246)',
                            'rgb(16, 185, 129)',
                            'rgb(245, 158, 11)',
                            'rgb(139, 92, 246)'
                        ],
                        borderWidth: 2
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'bottom'},
                        tooltip: {
                            callbacks: {
                                label: function(context) {
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const percentage = ((context.parsed / total) * 100).toFixed(1);
                                    return `${context.label}: ${context.parsed} (${percentage}%)`;
                                }
                            }
                        }
                    },
                    animation: {
                        animateRotate: true,
                        duration: 1000
                    }
                }
            });

            // Received files chart
            const receivedCtx = document.getElementById('receivedChart').getContext('2d');
            charts.received = new Chart(receivedCtx, {
                type: 'bar',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Files Received',
                        data: [],
                        backgroundColor: 'rgba(139, 92, 246, 0.8)',
                        borderColor: 'rgb(139, 92, 246)',
                        borderWidth: 2,
                        borderRadius: 6,
                        borderSkipped: false
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {display: false}
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            grid: {color: 'rgba(226, 232, 240, 0.5)'}
                        },
                        x: {
                            grid: {display: false}
                        }
                    },
                    animation: {
                        delay: (context) => context.dataIndex * 100
                    }
                }
            });
            
            // Daily trend chart
            const dailyCtx = document.getElementById('dailyTrendChart').getContext('2d');
            charts.dailyTrend = new Chart(dailyCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'}
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Files Exchanged'
                            }
                        }
                    },
                    interaction: {
                        intersect: false,
                        mode: 'index'
                    }
                }
            });
            
            // Hourly pattern chart
            const hourlyCtx = document.getElementById('hourlyPatternChart').getContext('2d');
            charts.hourlyPattern = new Chart(hourlyCtx, {
                type: 'radar',
                data: {
                    labels: [],
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'}
                    },
                    scales: {
                        r: {
                            beginAtZero: true,
                            grid: {color: 'rgba(226, 232, 240, 0.5)'}
                        }
                    }
                }
            });
        }
        
        function initPerformanceCharts() {
            // Performance metrics chart
            const perfCtx = document.getElementById('performanceChart').getContext('2d');
            charts.performance = new Chart(perfCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'}
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Performance Metrics'
                            }
                        }
                    }
                }
            });
            
            // Efficiency chart
            const effCtx = document.getElementById('efficiencyChart').getContext('2d');
            charts.efficiency = new Chart(effCtx, {
                type: 'area',
                data: {
                    labels: [],
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'},
                        filler: {
                            propagate: false
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Efficiency %'
                            }
                        }
                    }
                }
            });
        }
        
        function initAnalyticsCharts() {
            // File types chart
            const fileTypesCtx = document.getElementById('fileTypesChart').getContext('2d');
            charts.fileTypes = new Chart(fileTypesCtx, {
                type: 'pie',
                data: {
                    labels: [],
                    datasets: [{
                        data: [],
                        backgroundColor: [
                            '#FF6384', '#36A2EB', '#FFCE56', '#4BC0C0', 
                            '#9966FF', '#FF9F40', '#FF6384', '#C9CBCF'
                        ],
                        borderWidth: 2,
                        borderColor: '#ffffff'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'right'}
                    }
                }
            });
            
            // Server pairs chart
            const pairsCtx = document.getElementById('serverPairsChart').getContext('2d');
            charts.serverPairs = new Chart(pairsCtx, {
                type: 'bubble',
                data: {
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'}
                    },
                    scales: {
                        x: {
                            title: {
                                display: true,
                                text: 'Source Server'
                            }
                        },
                        y: {
                            title: {
                                display: true,
                                text: 'Target Server'
                            }
                        }
                    }
                }
            });
            
            // Pattern recognition chart
            const patternCtx = document.getElementById('patternChart').getContext('2d');
            charts.pattern = new Chart(patternCtx, {
                type: 'scatter',
                data: {
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'}
                    }
                }
            });
            
            // Predictive analytics chart
            const predictiveCtx = document.getElementById('predictiveChart').getContext('2d');
            charts.predictive = new Chart(predictiveCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: []
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {position: 'top'}
                    },
                    scales: {
                        y: {
                            beginAtZero: true,
                            title: {
                                display: true,
                                text: 'Predicted Activity'
                            }
                        }
                    }
                }
            });
        }
        
        function showTab(tabName) {
            // Remove active class from all tabs and content
            document.querySelectorAll('.tab').forEach(tab => tab.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));
            
            // Add active class to selected tab and content
            event.target.classList.add('active');
            document.getElementById(tabName).classList.add('active');
            
            // Load specific tab data
            loadTabData(tabName);
        }
        
        function loadTabData(tabName) {
            switch(tabName) {
                case 'network':
                    loadNetworkGraph();
                    break;
                case 'heatmap':
                    loadHeatmap();
                    break;
                case 'timeline':
                    loadTimeline();
                    break;
                case 'performance':
                    loadPerformanceData();
                    break;
                case 'analytics':
                    loadAnalyticsData();
                    break;
            }
        }
        
        function loadNetworkGraph() {
            fetch('/api/statistics/server-pairs')
                .then(r => r.json())
                .then(data => {
                    createNetworkVisualization(data);
                })
                .catch(error => {
                    console.error('Error loading network data:', error);
                });
        }
        
        function createNetworkVisualization(data) {
            const container = document.getElementById('networkGraph');
            container.innerHTML = '';
            
            const width = container.clientWidth;
            const height = 400;
            
            const svg = d3.select(container)
                .append('svg')
                .attr('width', width)
                .attr('height', height);
            
            // Create nodes and links from server pair data
            const nodes = [];
            const links = [];
            const nodeMap = new Set();
            
            data.forEach(pair => {
                if (!nodeMap.has(pair.source)) {
                    nodes.push({id: pair.source, group: 1});
                    nodeMap.add(pair.source);
                }
                if (!nodeMap.has(pair.target)) {
                    nodes.push({id: pair.target, group: 2});
                    nodeMap.add(pair.target);
                }
                links.push({
                    source: pair.source,
                    target: pair.target,
                    value: pair.files,
                    bytes: pair.bytes
                });
            });
            
            // Create force simulation
            const simulation = d3.forceSimulation(nodes)
                .force('link', d3.forceLink(links).id(d => d.id).distance(100))
                .force('charge', d3.forceManyBody().strength(-300))
                .force('center', d3.forceCenter(width / 2, height / 2));
            
            // Add links
            const link = svg.append('g')
                .selectAll('line')
                .data(links)
                .enter()
                .append('line')
                .attr('class', 'link')
                .attr('stroke-width', d => Math.sqrt(d.value) * 2);
            
            // Add nodes
            const node = svg.append('g')
                .selectAll('circle')
                .data(nodes)
                .enter()
                .append('circle')
                .attr('r', 20)
                .attr('fill', d => d.group === 1 ? '#4f46e5' : '#10b981')
                .attr('class', 'node')
                .call(d3.drag()
                    .on('start', dragstarted)
                    .on('drag', dragged)
                    .on('end', dragended));
            
            // Add labels
            const labels = svg.append('g')
                .selectAll('text')
                .data(nodes)
                .enter()
                .append('text')
                .text(d => d.id.replace('ubuntu-server-', 'S'))
                .attr('class', 'node text')
                .attr('dy', 5);
            
            // Update positions on tick
            simulation.on('tick', () => {
                link
                    .attr('x1', d => d.source.x)
                    .attr('y1', d => d.source.y)
                    .attr('x2', d => d.target.x)
                    .attr('y2', d => d.target.y);
                
                node
                    .attr('cx', d => d.x)
                    .attr('cy', d => d.y);
                
                labels
                    .attr('x', d => d.x)
                    .attr('y', d => d.y);
            });
            
            // Drag functions
            function dragstarted(event, d) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                d.fx = d.x;
                d.fy = d.y;
            }
            
            function dragged(event, d) {
                d.fx = event.x;
                d.fy = event.y;
            }
            
            function dragended(event, d) {
                if (!event.active) simulation.alphaTarget(0);
                d.fx = null;
                d.fy = null;
            }
            
            // Add tooltips
            node.append('title')
                .text(d => `${d.id}\nGroup: ${d.group}`);
            
            link.append('title')
                .text(d => `${d.source.id} → ${d.target.id}\nFiles: ${d.value}\nData: ${formatBytes(d.bytes)}`);
        }
        
        function loadHeatmap() {
            fetch('/api/statistics/hourly')
                .then(r => r.json())
                .then(data => {
                    createHeatmap(data);
                })
                .catch(error => {
                    console.error('Error loading heatmap data:', error);
                });
        }
        
        function createHeatmap(data) {
            const container = document.getElementById('heatmapContainer');
            container.innerHTML = '';
            
            const margin = {top: 50, right: 50, bottom: 50, left: 100};
            const width = container.clientWidth - margin.left - margin.right;
            const height = 400 - margin.top - margin.bottom;
            
            const svg = d3.select(container)
                .append('svg')
                .attr('width', width + margin.left + margin.right)
                .attr('height', height + margin.top + margin.bottom)
                .append('g')
                .attr('transform', `translate(${margin.left},${margin.top})`);
            
            // Prepare data for heatmap
            const hours = Object.keys(data).sort();
            const servers = ['ubuntu-server-1', 'ubuntu-server-2', 'ubuntu-server-3'];
            
            const heatmapData = [];
            hours.forEach((hour, hourIndex) => {
                servers.forEach((server, serverIndex) => {
                    const serverData = data[hour] && data[hour][server];
                    const value = serverData ? (serverData.files_sent + serverData.files_received) : 0;
                    heatmapData.push({
                        hour: hour,
                        server: server,
                        value: value,
                        x: hourIndex,
                        y: serverIndex
                    });
                });
            });
            
            // Color scale
            const maxValue = d3.max(heatmapData, d => d.value) || 1;
            const colorScale = d3.scaleSequential(d3.interpolateBlues)
                .domain([0, maxValue]);
            
            // Scales
            const xScale = d3.scaleBand()
                .domain(hours)
                .range([0, width])
                .padding(0.1);
                
            const yScale = d3.scaleBand()
                .domain(servers)
                .range([0, height])
                .padding(0.1);
            
            // Add rectangles
            svg.selectAll('.heatmap-cell')
                .data(heatmapData)
                .enter()
                .append('rect')
                .attr('class', 'heatmap-cell')
                .attr('x', d => xScale(d.hour))
                .attr('y', d => yScale(d.server))
                .attr('width', xScale.bandwidth())
                .attr('height', yScale.bandwidth())
                .attr('fill', d => colorScale(d.value))
                .append('title')
                .text(d => `${d.server}\n${d.hour}\nFiles: ${d.value}`);
            
            // Add axes
            svg.append('g')
                .attr('transform', `translate(0,${height})`)
                .call(d3.axisBottom(xScale))
                .selectAll('text')
                .style('text-anchor', 'end')
                .attr('dx', '-.8em')
                .attr('dy', '.15em')
                .attr('transform', 'rotate(-45)');
            
            svg.append('g')
                .call(d3.axisLeft(yScale));
        }
        
        function loadTimeline() {
            // Timeline implementation would go here
            console.log('Loading timeline...');
        }
        
        function loadPerformanceData() {
            fetch('/api/statistics/comprehensive')
                .then(r => r.json())
                .then(data => {
                    updatePerformanceCharts(data);
                    createGauges(data);
                })
                .catch(error => {
                    console.error('Error loading performance data:', error);
                });
        }
        
        function loadAnalyticsData() {
            // Load file types
            fetch('/api/statistics/file-types')
                .then(r => r.json())
                .then(data => {
                    updateFileTypesChart(data);
                })
                .catch(error => {
                    console.error('Error loading analytics data:', error);
                });
                
            // Load server pairs for bubble chart
            fetch('/api/statistics/server-pairs')
                .then(r => r.json())
                .then(data => {
                    updateServerPairsChart(data);
                })
                .catch(error => {
                    console.error('Error loading server pairs data:', error);
                });
        }
        
        function updateFileTypesChart(data) {
            const labels = data.map(item => item.extension || 'unknown');
            const counts = data.map(item => item.files);
            
            charts.fileTypes.data.labels = labels;
            charts.fileTypes.data.datasets[0].data = counts;
            charts.fileTypes.update();
        }
        
        function updateServerPairsChart(data) {
            const bubbleData = data.map((pair, index) => ({
                x: index % 3,
                y: Math.floor(index / 3),
                r: Math.sqrt(pair.files) * 5,
                label: `${pair.source} → ${pair.target}`,
                files: pair.files,
                bytes: pair.bytes
            }));
            
            charts.serverPairs.data.datasets = [{
                label: 'Server Exchanges',
                data: bubbleData,
                backgroundColor: 'rgba(79, 70, 229, 0.6)',
                borderColor: 'rgb(79, 70, 229)',
                borderWidth: 2
            }];
            charts.serverPairs.update();
        }
        
        function createGauges(data) {
            // Create throughput gauge using Chart.js doughnut chart
            createThroughputGauge();
            createLoadProgress();
        }
        
        function createThroughputGauge() {
            const container = document.getElementById('throughputGauge');
            container.innerHTML = '<canvas id="throughputCanvas" width="200" height="200"></canvas>';
            
            const ctx = document.getElementById('throughputCanvas').getContext('2d');
            
            // Simulate throughput data
            const throughputValue = Math.random() * 100;
            
            new Chart(ctx, {
                type: 'doughnut',
                data: {
                    datasets: [{
                        data: [throughputValue, 100 - throughputValue],
                        backgroundColor: [
                            throughputValue > 80 ? '#ef4444' : throughputValue > 50 ? '#f59e0b' : '#10b981',
                            '#e5e7eb'
                        ],
                        borderWidth: 0,
                        cutout: '80%'
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { enabled: false }
                    }
                },
                plugins: [{
                    beforeDraw: function(chart) {
                        const ctx = chart.ctx;
                        const centerX = chart.chartArea.left + (chart.chartArea.right - chart.chartArea.left) / 2;
                        const centerY = chart.chartArea.top + (chart.chartArea.bottom - chart.chartArea.top) / 2;
                        
                        ctx.save();
                        ctx.font = 'bold 24px Arial';
                        ctx.fillStyle = '#374151';
                        ctx.textAlign = 'center';
                        ctx.fillText(Math.round(throughputValue) + '%', centerX, centerY);
                        ctx.font = '12px Arial';
                        ctx.fillText('Throughput', centerX, centerY + 20);
                        ctx.restore();
                    }
                }]
            });
        }
        
        function createLoadProgress() {
            const container = document.getElementById('loadProgress');
            container.innerHTML = '';
            
            const servers = ['Server 1', 'Server 2', 'Server 3'];
            const loads = [Math.random() * 100, Math.random() * 100, Math.random() * 100];
            
            servers.forEach((server, index) => {
                const progressDiv = document.createElement('div');
                progressDiv.style.marginBottom = '15px';
                
                const label = document.createElement('div');
                label.textContent = `${server}: ${Math.round(loads[index])}%`;
                label.style.fontSize = '14px';
                label.style.marginBottom = '5px';
                label.style.fontWeight = '500';
                
                const progressBar = document.createElement('div');
                progressBar.style.width = '100%';
                progressBar.style.height = '8px';
                progressBar.style.backgroundColor = '#e5e7eb';
                progressBar.style.borderRadius = '4px';
                progressBar.style.overflow = 'hidden';
                
                const progressFill = document.createElement('div');
                progressFill.style.width = loads[index] + '%';
                progressFill.style.height = '100%';
                progressFill.style.backgroundColor = loads[index] > 80 ? '#ef4444' : loads[index] > 50 ? '#f59e0b' : '#10b981';
                progressFill.style.transition = 'width 1s ease-in-out';
                
                progressBar.appendChild(progressFill);
                progressDiv.appendChild(label);
                progressDiv.appendChild(progressBar);
                container.appendChild(progressDiv);
            });
        }
        
        function updatePerformanceCharts(data) {
            // Update performance metrics chart
            if (data.performance_trends) {
                const trends = data.performance_trends;
                const dates = [];
                const datasets = [];
                
                Object.keys(trends).forEach((metric, index) => {
                    const metricData = trends[metric];
                    const colors = ['#4f46e5', '#10b981', '#f59e0b'];
                    
                    datasets.push({
                        label: metric.replace('_', ' ').toUpperCase(),
                        data: metricData.map(item => item.value),
                        borderColor: colors[index % colors.length],
                        backgroundColor: colors[index % colors.length] + '20',
                        tension: 0.4
                    });
                    
                    if (dates.length === 0) {
                        dates.push(...metricData.map(item => item.date));
                    }
                });
                
                charts.performance.data.labels = dates;
                charts.performance.data.datasets = datasets;
                charts.performance.update();
            }
        }
        
        // Utility functions
        function formatBytes(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
        
        function updateTimeRange() {
            currentTimeRange = document.getElementById('timeRange').value;
            loadData();
        }
        
        function updateViewMode() {
            currentViewMode = document.getElementById('viewMode').value;
            updateCharts();
        }
        
        function updateNetworkLayout() {
            // Reload network graph with new layout
            loadNetworkGraph();
        }
        
        function toggleNetworkLabels() {
            // Toggle network labels visibility
            const showLabels = document.getElementById('showLabels').checked;
            d3.selectAll('.node text').style('display', showLabels ? 'block' : 'none');
        }
        
        function updateHeatmap() {
            loadHeatmap();
        }
        
        function updateTimeline() {
            loadTimeline();
        }
        
        // Main data loading and chart update functions
        function updateCharts(data) {
            if (!data) return;
            
            const labels = data.servers.map(s => s.name);
            const sentData = data.servers.map(s => s.sent || 0);
            const receivedData = data.servers.map(s => s.received || 0);
            
            // Update overview charts
            charts.sent.data.labels = labels;
            charts.sent.data.datasets[0].data = sentData;
            charts.sent.update();

            charts.received.data.labels = labels;
            charts.received.data.datasets[0].data = receivedData;
            charts.received.update();
            
            // Update daily trend chart
            updateDailyTrendChart();
            
            // Update hourly pattern chart
            updateHourlyPatternChart();
        }
        
        function updateDailyTrendChart() {
            fetch('/api/statistics/daily')
                .then(r => r.json())
                .then(data => {
                    const dates = Object.keys(data).sort().reverse().slice(0, 7);
                    const servers = ['ubuntu-server-1', 'ubuntu-server-2', 'ubuntu-server-3'];
                    
                    charts.dailyTrend.data.labels = dates;
                    charts.dailyTrend.data.datasets = [];
                    
                    servers.forEach((server, index) => {
                        const colors = ['#4f46e5', '#10b981', '#f59e0b'];
                        const sentData = dates.map(date => data[date]?.[server]?.files_sent || 0);
                        const receivedData = dates.map(date => data[date]?.[server]?.files_received || 0);
                        
                        charts.dailyTrend.data.datasets.push({
                            label: server + ' (Sent)',
                            data: sentData,
                            borderColor: colors[index],
                            backgroundColor: colors[index] + '20',
                            tension: 0.4
                        });
                        
                        charts.dailyTrend.data.datasets.push({
                            label: server + ' (Received)',
                            data: receivedData,
                            borderColor: colors[index],
                            backgroundColor: colors[index] + '40',
                            borderDash: [5, 5],
                            tension: 0.4
                        });
                    });
                    
                    charts.dailyTrend.update();
                })
                .catch(error => console.error('Error updating daily trend:', error));
        }
        
        function updateHourlyPatternChart() {
            fetch('/api/statistics/hourly')
                .then(r => r.json())
                .then(data => {
                    const hours = Object.keys(data).sort().slice(0, 24);
                    const hourLabels = hours.map(hour => hour.split(' ')[1]?.substring(0, 5) || hour);
                    const servers = ['ubuntu-server-1', 'ubuntu-server-2', 'ubuntu-server-3'];
                    
                    charts.hourlyPattern.data.labels = hourLabels;
                    charts.hourlyPattern.data.datasets = [];
                    
                    servers.forEach((server, index) => {
                        const colors = ['#4f46e5', '#10b981', '#f59e0b'];
                        const activityData = hours.map(hour => {
                            const serverData = data[hour]?.[server];
                            return serverData ? (serverData.files_sent + serverData.files_received) : 0;
                        });
                        
                        charts.hourlyPattern.data.datasets.push({
                            label: server,
                            data: activityData,
                            borderColor: colors[index],
                            backgroundColor: colors[index] + '30',
                            pointBackgroundColor: colors[index],
                            pointBorderColor: '#fff',
                            pointHoverBackgroundColor: '#fff',
                            pointHoverBorderColor: colors[index]
                        });
                    });
                    
                    charts.hourlyPattern.update();
                })
                .catch(error => console.error('Error updating hourly pattern:', error));
        }
        
        // API interaction functions
        function collectLogs() {
            document.getElementById('status-text').textContent = 'Collecting logs from servers via SSH...';
            document.getElementById('status-text').className = 'status-pending';
            
            fetch('/api/collect', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        document.getElementById('status-text').textContent = 'Log collection and processing completed successfully';
                        document.getElementById('status-text').className = 'status-success';
                        loadData();
                    } else {
                        document.getElementById('status-text').textContent = `Collection failed: ${data.error || 'Unknown error'}`;
                        document.getElementById('status-text').className = 'status-failed';
                    }
                })
                .catch(error => {
                    document.getElementById('status-text').textContent = 'Collection error occurred';
                    document.getElementById('status-text').className = 'status-failed';
                });
        }

        function incrementalRefresh() {
            document.getElementById('incremental-text').textContent = 'Processing collected log files...';
            
            fetch('/api/incremental-update', {method: 'POST'})
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        const newExchanges = data.result.new_exchanges;
                        const newReceived = data.result.new_received;
                        
                        if (newExchanges > 0 || newReceived > 0) {
                            document.getElementById('incremental-text').innerHTML = 
                                `✅ Processed ${newExchanges} new exchanges and ${newReceived} new received files 
                                 <span class="new-badge">NEW</span>`;
                            loadData();
                        } else {
                            document.getElementById('incremental-text').textContent = '✅ No new data found - all logs processed';
                        }
                    } else {
                        document.getElementById('incremental-text').textContent = '❌ Processing failed';
                    }
                })
                .catch(error => {
                    document.getElementById('incremental-text').textContent = '❌ Error during processing';
                });
        }

        function testConnectivity() {
            document.getElementById('status-text').textContent = 'Testing SSH connectivity and checking log directories...';
            document.getElementById('status-text').className = 'status-pending';
            
            fetch('/api/test-ssh')
                .then(r => r.json())
                .then(data => {
                    const results = Object.values(data.results);
                    const successful = results.filter(r => r.status === 'success').length;
                    
                    document.getElementById('status-text').textContent = `SSH Test: ${successful}/${results.length} servers accessible`;
                    document.getElementById('status-text').className = successful === results.length ? 'status-success' : 'status-failed';
                    
                    const details = Object.entries(data.results).map(([server, result]) => {
                        if (result.status === 'success') {
                            return `${server}: ✅ ${result.files_available} files available`;
                        } else {
                            return `${server}: ❌ ${result.error}`;
                        }
                    }).join(' | ');
                    document.getElementById('collection-details').textContent = details;
                });
        }

        function refreshData() {
            loadData();
        }

        function loadData() {
            fetch('/api/data')
                .then(r => r.json())
                .then(data => {
                    // Update summary statistics
                    document.getElementById('total-sent').textContent = data.total_sent;
                    document.getElementById('total-received').textContent = data.total_received;
                    document.getElementById('server-count').textContent = data.servers.length;
                    
                    // Calculate additional metrics
                    const totalExchanges = data.total_sent + data.total_received;
                    document.getElementById('exchange-rate-24h').textContent = Math.round(totalExchanges / 24);
                    document.getElementById('avg-throughput').textContent = formatBytes(totalExchanges * 1024 * 100) + '/h';
                    
                    // Update server table
                    const tbody = document.getElementById('server-table');
                    tbody.innerHTML = '';
                    data.servers.forEach(server => {
                        const row = tbody.insertRow();
                        const status = server.last_update ? '🟢 Active' : '🔴 Inactive';
                        const performance = server.sent > 50 ? '🟢 Good' : server.sent > 20 ? '🟡 Fair' : '🔴 Low';
                        
                        row.innerHTML = `
                            <td><strong>${server.name}</strong></td>
                            <td>${server.ip}</td>
                            <td><span style="color:#4f46e5;font-weight:bold">${server.sent || 0}</span></td>
                            <td><span style="color:#10b981;font-weight:bold">${server.received || 0}</span></td>
                            <td>${server.last_update || 'N/A'}</td>
                            <td>${status}</td>
                            <td>${performance}</td>
                        `;
                    });

                    updateCharts(data);
                })
                .catch(error => console.error('Error loading data:', error));
            
            // Load activity log
            fetch('/api/collection-log')
                .then(r => r.json())
                .then(logs => {
                    const logDiv = document.getElementById('collection-log');
                    logDiv.innerHTML = logs.map(log => 
                        `<div><span style="color:#64748b">${log.timestamp.split('T')[1]?.split('.')[0] || log.timestamp}</span> <strong>${log.server}</strong> ${log.status}: ${log.message}</div>`
                    ).join('');
                    logDiv.scrollTop = logDiv.scrollHeight;
                })
                .catch(error => console.error('Error loading logs:', error));
        }

        // Initialize application
        window.onload = function() {
            initCharts();
            loadData();
            
            // Auto-refresh every 5 minutes
            setInterval(() => {
                loadData();
            }, 300000);
        };
    </script>
</body>
</html>'''

@app.route('/')
def index():
    return ENHANCED_HTML_TEMPLATE

# Existing API routes
@app.route('/api/data')
def get_data():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    servers = []
    total_sent = 0
    total_received = 0
    
    for row in conn.execute('SELECT * FROM servers ORDER BY name'):
        server = dict(row)
        servers.append(server)
        total_sent += server['sent'] or 0
        total_received += server['received'] or 0
    
    last_update = conn.execute('SELECT value FROM metadata WHERE key=?', ('last_update',)).fetchone()
    conn.close()
    
    return jsonify({
        'servers': servers,
        'total_sent': total_sent,
        'total_received': total_received,
        'last_update': last_update['value'] if last_update else 'Never'
    })

# Enhanced statistics API routes
@app.route('/api/statistics/daily')
def get_daily_statistics():
    if not stats_manager:
        return jsonify({"error": "Statistics module not available"})
    
    days = request.args.get('days', 7, type=int)
    data = stats_manager.get_daily_server_activity(days)
    return jsonify(data)

@app.route('/api/statistics/hourly')
def get_hourly_statistics():
    if not stats_manager:
        return jsonify({"error": "Statistics module not available"})
    
    date = request.args.get('date')
    data = stats_manager.get_hourly_activity(date)
    return jsonify(data)

@app.route('/api/statistics/server-pairs')
def get_server_pairs_statistics():
    if not stats_manager:
        return jsonify({"error": "Statistics module not available"})
    
    days = request.args.get('days', 7, type=int)
    data = stats_manager.get_server_pair_summary(days)
    return jsonify(data)

@app.route('/api/statistics/file-types')
def get_file_types_statistics():
    if not stats_manager:
        return jsonify({"error": "Statistics module not available"})
    
    days = request.args.get('days', 7, type=int)
    data = stats_manager.get_file_type_summary(days)
    return jsonify(data)

@app.route('/api/statistics/comprehensive')
def get_comprehensive_statistics():
    if not stats_manager:
        return jsonify({"error": "Statistics module not available"})
    
    days = request.args.get('days', 7, type=int)
    report = stats_manager.get_comprehensive_report(days)
    return jsonify(report)

@app.route('/api/collect', methods=['POST'])
def trigger_collection():
    try:
        thread = threading.Thread(target=collect_logs_background)
        thread.start()
        return jsonify({"success": True, "message": "Log collection started"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/incremental-update', methods=['POST'])
def trigger_incremental_update():
    try:
        log_collection_event("ALL", "INCREMENTAL_START", "Starting incremental processing")
        result = updater.incremental_update_all()
        
        if stats_manager:
            stats_manager.update_all_statistics()
        
        log_collection_event("ALL", "INCREMENTAL_SUCCESS", 
            f"Processing completed: {result['new_exchanges']} new exchanges, {result['new_received']} new received")
        
        return jsonify({
            "success": True, 
            "result": result,
            "message": f"Processed {result['new_exchanges']} exchanges, {result['new_received']} received"
        })
    except Exception as e:
        error_msg = f"Processing error: {str(e)}"
        log_collection_event("ALL", "INCREMENTAL_ERROR", error_msg)
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/test-ssh')
def test_ssh():
    try:
        results = collector.test_connectivity()
        return jsonify({"success": True, "results": results})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/collection-log')
def get_collection_log():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    
    logs = []
    for row in conn.execute('SELECT * FROM collection_log ORDER BY timestamp DESC LIMIT 50'):
        logs.append(dict(row))
    
    conn.close()
    return jsonify(logs)

@app.route('/api/status')
def status():
    return jsonify({'status': 'ok', 'timestamp': int(time.time())})

if __name__ == '__main__':
    init_db()
    
    try:
        initial_update = updater.incremental_update_all()
        if stats_manager:
            stats_manager.update_all_statistics()
        print(f"📊 Initial processing: {initial_update}")
    except Exception as e:
        print(f"Initial processing error: {e}")
    
    def periodic_collection():
        while True:
            time.sleep(14400)  # 4 hours
            collect_logs_background()
    
    threading.Thread(target=periodic_collection, daemon=True).start()
    
    print("🚀 VM Log Collection Monitor started with Advanced Analytics")
    print("📡 Features: Network graphs, heatmaps, performance metrics, predictive analytics")
    print("🔄 Automatic collection every 4 hours")
    
    app.run(host='0.0.0.0', port=5000, debug=False)
