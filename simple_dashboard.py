#!/usr/bin/env python3
"""
Simple ASCII Terminal Dashboard for VM Exchange Monitor
Works reliably in any terminal environment including Docker
"""
import sqlite3
import time
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json

class SimpleTerminalDashboard:
    def __init__(self, db_path='./data/monitor.db'):
        self.db_path = db_path
        
    def get_connection(self):
        """Get database connection"""
        if not os.path.exists(self.db_path):
            print(f"❌ Database not found: {self.db_path}")
            return None
        return sqlite3.connect(self.db_path)
    
    def get_server_stats(self):
        """Get basic server statistics"""
        conn = self.get_connection()
        if not conn:
            return []
            
        try:
            cursor = conn.execute('''
                SELECT name, ip, sent, received, last_update 
                FROM servers 
                ORDER BY name
            ''')
            servers = []
            for row in cursor.fetchall():
                servers.append({
                    'name': row[0],
                    'ip': row[1], 
                    'sent': row[2] or 0,
                    'received': row[3] or 0,
                    'last_update': row[4]
                })
            return servers
        except Exception as e:
            print(f"❌ Error getting server stats: {e}")
            return []
        finally:
            conn.close()
    
    def get_file_exchanges(self, limit=50):
        """Get recent file exchanges"""
        conn = self.get_connection()
        if not conn:
            return []
            
        try:
            cursor = conn.execute('''
                SELECT timestamp, server_name, action, target_servers, filename, status, file_size
                FROM file_exchanges 
                ORDER BY timestamp DESC 
                LIMIT ?
            ''', (limit,))
            
            exchanges = []
            for row in cursor.fetchall():
                exchanges.append({
                    'timestamp': row[0],
                    'server': row[1],
                    'action': row[2],
                    'target': row[3],
                    'filename': row[4],
                    'status': row[5],
                    'size': row[6] or 0
                })
            return exchanges
        except Exception as e:
            print(f"❌ Error getting file exchanges: {e}")
            return []
        finally:
            conn.close()
    
    def create_ascii_bar_chart(self, data, title, max_width=50):
        """Create simple ASCII bar chart"""
        if not data:
            return
            
        print(f"\n{title}")
        print("=" * len(title))
        
        # Find max value for scaling
        max_val = max(data.values()) if data.values() else 1
        
        for name, value in data.items():
            # Calculate bar length
            if max_val > 0:
                bar_length = int((value / max_val) * max_width)
            else:
                bar_length = 0
            
            # Create bar using simple characters
            bar = "#" * bar_length
            
            # Display
            print(f"{name:<15} |{bar:<{max_width}} | {value}")
        
        print("-" * (max_width + 20))
    
    def display_server_overview(self):
        """Display server statistics overview"""
        servers = self.get_server_stats()
        
        if not servers:
            print("❌ No server data available")
            return
            
        print("\n" + "=" * 90)
        print("📊 VM EXCHANGE MONITOR - SERVER OVERVIEW")
        print("=" * 90)
        
        # Server statistics table
        print(f"{'Status':<12} {'Server':<18} {'IP Address':<15} {'Sent':<8} {'Recv':<8} {'Total':<8} {'Last Update':<20}")
        print("-" * 90)
        
        total_sent = 0
        total_received = 0
        
        for server in servers:
            status = "[ACTIVE]" if server['last_update'] else "[INACTIVE]"
            last_update = server['last_update'][:19] if server['last_update'] else "Never"
            total_files = server['sent'] + server['received']
            
            print(f"{status:<12} {server['name']:<18} {server['ip']:<15} {server['sent']:<8} {server['received']:<8} {total_files:<8} {last_update:<20}")
            total_sent += server['sent']
            total_received += server['received']
        
        print("-" * 90)
        print(f"{'TOTAL':<12} {'':<18} {'':<15} {total_sent:<8} {total_received:<8} {total_sent + total_received:<8}")
        
        # ASCII Bar Charts
        if servers:
            sent_data = {s['name'].replace('ubuntu-server-', 'S'): s['sent'] for s in servers}
            received_data = {s['name'].replace('ubuntu-server-', 'S'): s['received'] for s in servers}
            
            self.create_ascii_bar_chart(sent_data, "FILES SENT BY SERVER")
            self.create_ascii_bar_chart(received_data, "FILES RECEIVED BY SERVER")
    
    def display_file_activity(self):
        """Display recent file exchange activity"""
        exchanges = self.get_file_exchanges(20)
        
        if not exchanges:
            print("\n❌ No file exchange data available")
            return
            
        print("\n📋 RECENT FILE EXCHANGE ACTIVITY")
        print("=" * 100)
        print(f"{'Time':<20} {'Server':<12} {'Action':<7} {'Target':<12} {'Filename':<25} {'Status':<8} {'Size':<8}")
        print("-" * 100)
        
        for exchange in exchanges:
            timestamp = exchange['timestamp'][:19] if exchange['timestamp'] else "Unknown"
            server = exchange['server'].replace('ubuntu-server-', 'S') if exchange['server'] else "N/A"
            action = exchange['action'][:6] if exchange['action'] else "N/A"
            target = exchange['target'].replace('ubuntu-server-', 'S') if exchange['target'] else "N/A"
            filename = exchange['filename'][:24] if exchange['filename'] else "N/A"
            status = "[OK]" if exchange['status'] == 'success' else "[FAIL]"
            size = f"{exchange['size']}B" if exchange['size'] else "0B"
            
            print(f"{timestamp:<20} {server:<12} {action:<7} {target:<12} {filename:<25} {status:<8} {size:<8}")
        
        # Activity Statistics
        if exchanges:
            print(f"\n📊 ACTIVITY SUMMARY (Last {len(exchanges)} exchanges)")
            print("-" * 50)
            
            actions = [e['action'] for e in exchanges if e['action']]
            statuses = [e['status'] for e in exchanges if e['status']]
            
            action_counts = Counter(actions)
            status_counts = Counter(statuses)
            
            successful = status_counts.get('success', 0)
            success_rate = (successful / len(exchanges)) * 100 if exchanges else 0
            
            print(f"Success Rate: {success_rate:.1f}% ({successful}/{len(exchanges)})")
            print(f"Actions: {dict(action_counts)}")
    
    def display_network_summary(self):
        """Display network connectivity summary"""
        exchanges = self.get_file_exchanges(100)
        
        if not exchanges:
            print("\n❌ No exchange data for network analysis")
            return
            
        print("\n🌐 NETWORK CONNECTION SUMMARY")
        print("=" * 60)
        
        # Count connections between servers
        connections = defaultdict(int)
        
        for exchange in exchanges:
            if exchange['server'] and exchange['target'] and exchange['action'] == 'sent':
                source = exchange['server'].replace('ubuntu-server-', 'S')
                target = exchange['target'].replace('ubuntu-server-', 'S')
                connections[f"{source} -> {target}"] += 1
        
        if connections:
            print("Server-to-Server Exchange Counts:")
            print("-" * 40)
            
            for connection, count in sorted(connections.items(), key=lambda x: x[1], reverse=True):
                # Create simple bar
                bar_length = min(count // 5, 20)  # Scale down
                bar = "#" * bar_length
                print(f"  {connection:<20} |{bar:<20}| {count:>4}")
                
            print(f"\nTotal Connections: {len(connections)}")
            print(f"Most Active: {max(connections.items(), key=lambda x: x[1])[0]} ({max(connections.values())} exchanges)")
        else:
            print("❌ No server-to-server exchanges found")
    
    def run_dashboard(self):
        """Run the complete terminal dashboard"""
        # Clear screen
        os.system('clear' if os.name == 'posix' else 'cls')
        
        print("🚀 VM Exchange Monitor - ASCII Dashboard")
        print(f"📅 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Display all sections
        self.display_server_overview()
        self.display_file_activity()
        self.display_network_summary()
        
        print("\n" + "=" * 90)
        print("✅ Dashboard complete! Use './docker-dashboard.sh watch' for monitoring")
        print("=" * 90)


def main():
    """Main function"""
    dashboard = SimpleTerminalDashboard()
    
    if len(sys.argv) > 1 and sys.argv[1] == '--watch':
        try:
            while True:
                dashboard.run_dashboard()
                print(f"\n⏰ Refreshing in 30 seconds... (Ctrl+C to exit)")
                time.sleep(30)
        except KeyboardInterrupt:
            print("\n👋 Dashboard stopped.")
            sys.exit(0)
    else:
        dashboard.run_dashboard()


if __name__ == "__main__":
    main()
