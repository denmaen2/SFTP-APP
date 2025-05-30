import sqlite3
import json
import os
from contextlib import contextmanager

class DatabaseManager:
    def __init__(self, db_path='./data/exchange_monitor.db'):
        self.db_path = db_path
        # Ensure directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            # Servers table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hostname TEXT UNIQUE NOT NULL,
                    ip_address TEXT NOT NULL,
                    last_exchange TEXT,
                    total_sent INTEGER DEFAULT 0,
                    total_received INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # File exchanges table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS file_exchanges (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    target_server TEXT,
                    filename TEXT,
                    status TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (server_id) REFERENCES servers (id)
                )
            ''')
            
            # Received files table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS received_files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    server_id INTEGER,
                    filename TEXT NOT NULL,
                    source_server TEXT,
                    received_date TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (server_id) REFERENCES servers (id)
                )
            ''')
            
            # System metadata table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_exchanges_server_id ON file_exchanges(server_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_exchanges_timestamp ON file_exchanges(timestamp)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_received_server_id ON received_files(server_id)')
    
    def upsert_server(self, hostname, ip_address):
        """Insert or update server information"""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO servers (hostname, ip_address, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(hostname) DO UPDATE SET
                ip_address = excluded.ip_address,
                updated_at = CURRENT_TIMESTAMP
            ''', (hostname, ip_address))
            
            # Get server ID
            cursor = conn.execute('SELECT id FROM servers WHERE hostname = ?', (hostname,))
            return cursor.fetchone()['id']
    
    def update_server_stats(self, hostname, total_sent, total_received, last_exchange):
        """Update server statistics"""
        with self.get_connection() as conn:
            conn.execute('''
                UPDATE servers 
                SET total_sent = ?, total_received = ?, last_exchange = ?, updated_at = CURRENT_TIMESTAMP
                WHERE hostname = ?
            ''', (total_sent, total_received, last_exchange, hostname))
    
    def insert_file_exchange(self, server_id, timestamp, action, target_server, filename, status):
        """Insert file exchange record"""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO file_exchanges (server_id, timestamp, action, target_server, filename, status)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (server_id, timestamp, action, target_server, filename, status))
    
    def insert_received_file(self, server_id, filename, source_server, received_date):
        """Insert received file record"""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO received_files (server_id, filename, source_server, received_date)
                VALUES (?, ?, ?, ?)
            ''', (server_id, filename, source_server, received_date))
    
    def clear_server_data(self, hostname):
        """Clear existing data for a server before re-importing"""
        with self.get_connection() as conn:
            server_id = conn.execute('SELECT id FROM servers WHERE hostname = ?', (hostname,)).fetchone()
            if server_id:
                server_id = server_id['id']
                conn.execute('DELETE FROM file_exchanges WHERE server_id = ?', (server_id,))
                conn.execute('DELETE FROM received_files WHERE server_id = ?', (server_id,))
    
    def get_all_servers(self):
        """Get all server information with statistics"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT hostname, ip_address, total_sent, total_received, last_exchange
                FROM servers
                ORDER BY hostname
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def get_server_details(self, hostname):
        """Get detailed information for a specific server"""
        with self.get_connection() as conn:
            # Get server info
            server_cursor = conn.execute('''
                SELECT id, hostname, ip_address, total_sent, total_received, last_exchange
                FROM servers WHERE hostname = ?
            ''', (hostname,))
            server = server_cursor.fetchone()
            
            if not server:
                return None
            
            server_dict = dict(server)
            server_id = server['id']
            
            # Get sent files
            sent_cursor = conn.execute('''
                SELECT timestamp, target_server as target, filename, status
                FROM file_exchanges
                WHERE server_id = ? AND action = 'sent'
                ORDER BY timestamp DESC
            ''', (server_id,))
            server_dict['sent_files'] = [dict(row) for row in sent_cursor.fetchall()]
            
            # Get received files
            received_cursor = conn.execute('''
                SELECT filename, source_server as source, received_date as date
                FROM received_files
                WHERE server_id = ?
                ORDER BY received_date DESC
            ''', (server_id,))
            server_dict['received_files'] = [dict(row) for row in received_cursor.fetchall()]
            
            # Get history
            history_cursor = conn.execute('''
                SELECT timestamp, ? as hostname, action, target_server as target_servers, filename, status
                FROM file_exchanges
                WHERE server_id = ?
                ORDER BY timestamp DESC
            ''', (hostname, server_id))
            server_dict['history'] = [dict(row) for row in history_cursor.fetchall()]
            
            return server_dict
    
    def get_summary_stats(self):
        """Get summary statistics"""
        with self.get_connection() as conn:
            # Get totals
            cursor = conn.execute('''
                SELECT 
                    COUNT(*) as server_count,
                    SUM(total_sent) as total_files_sent,
                    SUM(total_received) as total_files_received
                FROM servers
            ''')
            stats = dict(cursor.fetchone())
            
            # Get server IPs
            ip_cursor = conn.execute('SELECT hostname, ip_address FROM servers')
            server_ips = {row['hostname']: row['ip_address'] for row in ip_cursor.fetchall()}
            
            stats['server_ips'] = server_ips
            return stats
    
    def get_recent_exchanges(self, limit=20):
        """Get recent file exchanges across all servers"""
        with self.get_connection() as conn:
            cursor = conn.execute('''
                SELECT 
                    fe.timestamp,
                    s.hostname as source,
                    fe.action,
                    fe.target_server as target_servers,
                    fe.filename as file,
                    fe.status
                FROM file_exchanges fe
                JOIN servers s ON fe.server_id = s.id
                ORDER BY fe.timestamp DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def set_metadata(self, key, value):
        """Set system metadata"""
        with self.get_connection() as conn:
            conn.execute('''
                INSERT INTO system_metadata (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = CURRENT_TIMESTAMP
            ''', (key, str(value)))
    
    def get_metadata(self, key, default=None):
        """Get system metadata"""
        with self.get_connection() as conn:
            cursor = conn.execute('SELECT value FROM system_metadata WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row['value'] if row else default
    
    def get_database_info(self):
        """Get database statistics"""
        with self.get_connection() as conn:
            info = {}
            
            # Table counts
            for table in ['servers', 'file_exchanges', 'received_files']:
                cursor = conn.execute(f'SELECT COUNT(*) as count FROM {table}')
                info[f'{table}_count'] = cursor.fetchone()['count']
            
            # Database size
            cursor = conn.execute("SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size()")
            info['database_size_bytes'] = cursor.fetchone()['size']
            
            return info
