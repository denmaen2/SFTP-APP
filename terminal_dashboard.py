#!/usr/bin/env python3
"""
Terminal-based Dashboard for VM Exchange Monitor using plotext
"""
import sqlite3
import plotext as plt
import time
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict, Counter
import json

class TerminalDashboard:
    def __init__(self, db_path='./data/monitor.db'):
        self.db_path = db_path
        self.colors = ['red', 'green', 'blue', 'yellow', 'magenta', 'cyan']
        
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
            return {}
            
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
    
    def get_daily_activity(self, days=7):
        """Get daily activity data"""
        conn = self.get_connection()
        if not conn:
            return {}
            
        try:
            # Check if daily_activity table exists
            cursor = conn.execute('''
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='daily_activity'
            ''')
            if not cursor.fetchone():
                return {}
                
            cursor = conn.execute('''
                SELECT date, server_name, files_sent, files_received 
                FROM daily_activity 
                WHERE date >= date('now', '-{} days')
                ORDER BY date DESC
            '''.format(days))
            
            daily_data = defaultdict(lambda: defaultdict(lambda: {'sent': 0, 'received': 0}))
            for row in cursor.fetchall():
                date, server, sent, received = row
                daily_data[date][server] = {'sent': sent or 0, 'received': received or 0}
                
            return dict(daily_data)
        except Exception as e:
            print(f"❌ Error getting daily activity: {e}")
            return {}
        finally:
            conn.close()
    
    def get_file_exchanges(self, limit=100):
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
    
    def display_server_overview(self):
        """Display server statistics overview"""
        servers = self.get_server_stats()
        
        if not servers:
            print("❌ No server data available")
            return
            
        print("\n" + "="*80)
        print("📊 VM EXCHANGE MONITOR - SERVER OVERVIEW")
        print("="*80)
        
        # Server statistics table
        print(f"{'Server':<20} {'IP Address':<15} {'Files Sent':<12} {'Files Recv':<12} {'Last Update':<20}")
        print("-" * 80)
        
        total_sent = 0
        total_received = 0
        
        for server in servers:
            status = "🟢" if server['last_update'] else "🔴"
            last_update = server['last_update'][:19] if server['last_update'] else "Never"
            
            print(f"{status} {server['name']:<17} {server['ip']:<15} {server['sent']:<12} {server['received']:<12} {last_update:<20}")
            total_sent += server['sent']
            total_received += server['received']
        
        print("-" * 80)
        print(f"{'TOTAL':<20} {'':<15} {total_sent:<12} {total_received:<12}")
        
        # Create bar charts
        server_names = [s['name'].replace('ubuntu-server-', 'S') for s in servers]
        sent_counts = [s['sent'] for s in servers]
        received_counts = [s['received'] for s in servers]
        
        if any(sent_counts):
            print("\n📤 FILES SENT BY SERVER")
            plt.clear_figure()
            plt.bar(server_names, sent_counts, color='blue')
            plt.title("Files Sent by Server")
            plt.xlabel("Servers")
            plt.ylabel("Files Sent")
            plt.theme('dark')
            plt.plotsize(80, 15)
            plt.show()
        
        if any(received_counts):
            print("\n📥 FILES RECEIVED BY SERVER")
            plt.clear_figure()
            plt.bar(server_names, received_counts, color='green')
            plt.title("Files Received by Server")
            plt.xlabel("Servers")
            plt.ylabel("Files Received")
            plt.theme('dark')
            plt.plotsize(80, 15)
            plt.show()
    
    def display_file_activity(self):
        """Display recent file exchange activity"""
        exchanges = self.get_file_exchanges(50)
        
        if not exchanges:
            print("\n❌ No file exchange data available")
            return
            
        print("\n📋 RECENT FILE EXCHANGE ACTIVITY")
        print("="*100)
        print(f"{'Time':<20} {'Server':<15} {'Action':<8} {'Target':<15} {'File':<25} {'Status':<10} {'Size':<10}")
        print("-" * 100)
        
        for exchange in exchanges[:20]:  # Show top 20
            timestamp = exchange['timestamp'][:19] if exchange['timestamp'] else "Unknown"
            server = exchange['server'].replace('ubuntu-server-', 'S') if exchange['server'] else "Unknown"
            action = exchange['action'][:7] if exchange['action'] else "Unknown"
            target = exchange['target'].replace('ubuntu-server-', 'S') if exchange['target'] else "Unknown"
            filename = exchange['filename'][:24] if exchange['filename'] else "Unknown"
            status = "✅" if exchange['status'] == 'success' else "❌"
            size = f"{exchange['size']}B" if exchange['size'] else "0B"
            
            print(f"{timestamp:<20} {server:<15} {action:<8} {target:<15} {filename:<25} {status:<10} {size:<10}")
        
        # File exchange statistics
        if exchanges:
            actions = [e['action'] for e in exchanges if e['action']]
            statuses = [e['status'] for e in exchanges if e['status']]
            
            action_counts = Counter(actions)
            status_counts = Counter(statuses)
            
            print(f"\n📊 Activity Summary (Last {len(exchanges)} exchanges):")
            print(f"   Actions: {dict(action_counts)}")
            print(f"   Status: {dict(status_counts)}")
    
    def run_dashboard(self):
        """Run the complete terminal dashboard"""
        os.system('clear')  # Clear terminal
        
        print("🚀 VM Exchange Monitor - Terminal Dashboard")
        print(f"📅 Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        # Display all sections
        self.display_server_overview()
        self.display_file_activity()
        
        print("\n" + "="*80)
        print("✅ Dashboard refresh complete!")
        print("💡 Tip: Use 'docker-dashboard.sh watch' for continuous monitoring")
        print("="*80)


def main():
    """Main function"""
    dashboard = TerminalDashboard()
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--watch':
            # Watch mode - refresh every 30 seconds
            try:
                while True:
                    dashboard.run_dashboard()
                    print(f"\n⏰ Refreshing in 30 seconds... (Press Ctrl+C to exit)")
                    time.sleep(30)
            except KeyboardInterrupt:
                print("\n👋 Dashboard stopped.")
                sys.exit(0)
        elif sys.argv[1] == '--help':
            print("VM Exchange Monitor - Terminal Dashboard")
            print("Usage:")
            print("  python terminal_dashboard.py          # Run once")
            print("  python terminal_dashboard.py --watch  # Continuous monitoring")
            print("  python terminal_dashboard.py --help   # Show this help")
            sys.exit(0)
    else:
        # Run once
        dashboard.run_dashboard()


if __name__ == "__main__":
    main()
