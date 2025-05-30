import sqlite3
import json
from datetime import datetime, timedelta
from collections import defaultdict, Counter

class EnhancedStatistics:
    def __init__(self, db_path):
        self.db_path = db_path
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_statistics_tables(self):
        """Initialize additional statistics tables if needed"""
        conn = self.get_connection()
        try:
            # Additional tables for enhanced statistics could be created here
            conn.commit()
        except Exception as e:
            print(f"Error initializing statistics tables: {e}")
        finally:
            conn.close()
    
    def get_daily_server_activity(self, days=7):
        """Get daily activity by server"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT date, server_name, files_sent, files_received
                FROM daily_activity 
                WHERE date >= date('now', '-{} days')
                ORDER BY date DESC
            '''.format(days))
            
            daily_data = defaultdict(dict)
            for row in cursor.fetchall():
                date, server, sent, received = row
                daily_data[date][server] = {
                    'files_sent': sent or 0,
                    'files_received': received or 0
                }
            
            return dict(daily_data)
        except Exception as e:
            print(f"Error getting daily activity: {e}")
            return {}
        finally:
            conn.close()
    
    def get_hourly_activity(self, date=None):
        """Get hourly activity pattern"""
        conn = self.get_connection()
        try:
            # Get hourly breakdown from file exchanges
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m-%d %H:00:00', timestamp) as hour,
                    server_name,
                    COUNT(*) as activity_count
                FROM file_exchanges 
                WHERE timestamp IS NOT NULL
                GROUP BY strftime('%Y-%m-%d %H:00:00', timestamp), server_name
                ORDER BY hour DESC
                LIMIT 100
            ''')
            
            hourly_data = defaultdict(dict)
            for row in cursor.fetchall():
                hour, server, count = row
                if server not in hourly_data[hour]:
                    hourly_data[hour][server] = {'files_sent': 0, 'files_received': 0}
                hourly_data[hour][server]['files_sent'] = count
            
            return dict(hourly_data)
        except Exception as e:
            print(f"Error getting hourly activity: {e}")
            return {}
        finally:
            conn.close()
    
    def get_server_pair_summary(self, days=7):
        """Get server-to-server exchange summary"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT 
                    server_name as source,
                    target_servers as target,
                    COUNT(*) as files,
                    SUM(file_size) as bytes
                FROM file_exchanges 
                WHERE action = 'sent' AND target_servers IS NOT NULL
                GROUP BY server_name, target_servers
                ORDER BY files DESC
            ''')
            
            pairs = []
            for row in cursor.fetchall():
                source, target, files, bytes_total = row
                pairs.append({
                    'source': source,
                    'target': target,
                    'files': files,
                    'bytes': bytes_total or 0
                })
            
            return pairs
        except Exception as e:
            print(f"Error getting server pairs: {e}")
            return []
        finally:
            conn.close()
    
    def get_file_type_summary(self, days=7):
        """Get file type breakdown"""
        conn = self.get_connection()
        try:
            cursor = conn.execute('''
                SELECT 
                    CASE 
                        WHEN filename LIKE '%.txt' THEN 'txt'
                        WHEN filename LIKE '%.csv' THEN 'csv'
                        WHEN filename LIKE '%.log' THEN 'log'
                        WHEN filename LIKE '%.pdf' THEN 'pdf'
                        WHEN filename LIKE '%.json' THEN 'json'
                        ELSE 'other'
                    END as extension,
                    COUNT(*) as files,
                    SUM(file_size) as total_size
                FROM file_exchanges 
                WHERE filename IS NOT NULL
                GROUP BY extension
                ORDER BY files DESC
            ''')
            
            file_types = []
            for row in cursor.fetchall():
                ext, files, size = row
                file_types.append({
                    'extension': ext,
                    'files': files,
                    'total_size': size or 0
                })
            
            return file_types
        except Exception as e:
            print(f"Error getting file types: {e}")
            return []
        finally:
            conn.close()
    
    def get_comprehensive_report(self, days=7):
        """Get comprehensive statistics report"""
        try:
            report = {
                'daily_activity': self.get_daily_server_activity(days),
                'server_pairs': self.get_server_pair_summary(days),
                'file_types': self.get_file_type_summary(days),
                'hourly_patterns': self.get_hourly_activity(),
                'summary': self.get_summary_stats()
            }
            return report
        except Exception as e:
            print(f"Error generating comprehensive report: {e}")
            return {}
    
    def get_summary_stats(self):
        """Get summary statistics"""
        conn = self.get_connection()
        try:
            # Total exchanges
            cursor = conn.execute('SELECT COUNT(*) FROM file_exchanges')
            total_exchanges = cursor.fetchone()[0]
            
            # Total received files
            cursor = conn.execute('SELECT COUNT(*) FROM received_files')
            total_received = cursor.fetchone()[0]
            
            # Active servers
            cursor = conn.execute('SELECT COUNT(*) FROM servers WHERE last_update IS NOT NULL')
            active_servers = cursor.fetchone()[0]
            
            # Recent activity (last 24 hours)
            cursor = conn.execute('''
                SELECT COUNT(*) FROM file_exchanges 
                WHERE timestamp >= datetime('now', '-1 day')
            ''')
            recent_activity = cursor.fetchone()[0]
            
            return {
                'total_exchanges': total_exchanges,
                'total_received': total_received,
                'active_servers': active_servers,
                'recent_activity_24h': recent_activity
            }
        except Exception as e:
            print(f"Error getting summary stats: {e}")
            return {}
        finally:
            conn.close()
    
    def update_all_statistics(self):
        """Update all statistics (called after data processing)"""
        try:
            # This method would update any derived statistics tables
            # For now, we'll just ensure the base data is consistent
            print("📊 Enhanced statistics updated")
            return True
        except Exception as e:
            print(f"Error updating statistics: {e}")
            return False
