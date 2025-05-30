import os
import sqlite3
import csv
import json
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class IncrementalUpdater:
    def __init__(self, db_path='./data/monitor.db'):
        self.db_path = db_path
        self.init_incremental_tables()
    
    def init_incremental_tables(self):
        """Initialize tables with proper schema"""
        conn = sqlite3.connect(self.db_path)
        
        # Drop and recreate tables to fix schema issues
        try:
            conn.execute('DROP TABLE IF EXISTS file_exchanges')
            conn.execute('DROP TABLE IF EXISTS file_checkpoints')
            conn.execute('DROP TABLE IF EXISTS received_files')
            conn.execute('DROP TABLE IF EXISTS daily_activity')
        except:
            pass
        
        # Create tables with correct schema
        conn.execute('''CREATE TABLE IF NOT EXISTS file_exchanges (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT,
            timestamp TEXT,
            hostname TEXT,
            action TEXT,
            target_servers TEXT,
            filename TEXT,
            status TEXT,
            file_size INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(server_name, timestamp, filename, action)
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS received_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_name TEXT,
            filename TEXT,
            source_server TEXT,
            received_date TEXT,
            file_size TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(server_name, filename, received_date)
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS file_checkpoints (
            server_name TEXT PRIMARY KEY,
            last_history_line INTEGER DEFAULT 0,
            last_received_count INTEGER DEFAULT 0,
            last_processed_date TEXT,
            total_processed_exchanges INTEGER DEFAULT 0,
            total_processed_received INTEGER DEFAULT 0,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )''')
        
        conn.execute('''CREATE TABLE IF NOT EXISTS daily_activity (
            date TEXT,
            server_name TEXT,
            files_sent INTEGER DEFAULT 0,
            files_received INTEGER DEFAULT 0,
            total_size_sent INTEGER DEFAULT 0,
            total_size_received INTEGER DEFAULT 0,
            PRIMARY KEY (date, server_name)
        )''')
        
        conn.commit()
        conn.close()
    
    def get_checkpoint(self, server_name):
        """Get the last processing checkpoint for a server"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        checkpoint = conn.execute(
            'SELECT * FROM file_checkpoints WHERE server_name = ?', 
            (server_name,)
        ).fetchone()
        
        conn.close()
        
        if checkpoint:
            return dict(checkpoint)
        else:
            return {
                'server_name': server_name,
                'last_history_line': 0,
                'last_received_count': 0,
                'last_processed_date': None,
                'total_processed_exchanges': 0,
                'total_processed_received': 0
            }
    
    def update_checkpoint(self, server_name, history_lines, received_count, total_exchanges, total_received):
        """Update the processing checkpoint for a server"""
        conn = sqlite3.connect(self.db_path)
        
        conn.execute('''
            INSERT OR REPLACE INTO file_checkpoints 
            (server_name, last_history_line, last_received_count, last_processed_date, 
             total_processed_exchanges, total_processed_received, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (server_name, history_lines, received_count, datetime.now().isoformat(), 
              total_exchanges, total_received))
        
        conn.commit()
        conn.close()
    
    def parse_file_size(self, size_str):
        """Parse file size string and return bytes"""
        if not size_str:
            return 0
        
        try:
            size_str = size_str.lower().strip()
            
            if 'kb' in size_str:
                return int(float(size_str.replace('kb', '').strip()) * 1024)
            elif 'mb' in size_str:
                return int(float(size_str.replace('mb', '').strip()) * 1024 * 1024)
            elif 'gb' in size_str:
                return int(float(size_str.replace('gb', '').strip()) * 1024 * 1024 * 1024)
            elif 'bytes' in size_str:
                return int(size_str.replace('bytes', '').strip())
            else:
                return int(float(size_str))
        except:
            return 0
    
    def process_history_file_incremental(self, server_name, history_file_path):
        """Process history.csv file"""
        if not os.path.exists(history_file_path):
            logger.warning(f"History file not found: {history_file_path}")
            return 0, 0
        
        checkpoint = self.get_checkpoint(server_name)
        last_processed_line = checkpoint['last_history_line']
        
        new_entries = 0
        current_line = 0
        
        conn = sqlite3.connect(self.db_path)
        
        try:
            with open(history_file_path, 'r') as f:
                reader = csv.DictReader(f)
                
                for row in reader:
                    current_line += 1
                    
                    if current_line <= last_processed_line:
                        continue
                    
                    timestamp = row.get('timestamp', '')
                    hostname = row.get('hostname', '')
                    action = row.get('action', '')
                    target_servers = row.get('target_servers', '')
                    filename = row.get('file', '')
                    status = row.get('status', '')
                    file_size = self.parse_file_size(row.get('size', '0'))
                    
                    try:
                        conn.execute('''
                            INSERT OR IGNORE INTO file_exchanges 
                            (server_name, timestamp, hostname, action, target_servers, filename, status, file_size)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (server_name, timestamp, hostname, action, target_servers, filename, status, file_size))
                        
                        new_entries += 1
                        logger.info(f"📊 Recorded {action}: {server_name} -> {target_servers} ({filename})")
                        
                        if timestamp and action == 'sent':
                            date = timestamp.split(' ')[0]
                            self.update_daily_activity(conn, date, server_name, 'sent', file_size)
                        
                    except sqlite3.IntegrityError:
                        pass
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error processing history file for {server_name}: {str(e)}")
            conn.rollback()
        finally:
            conn.close()
        
        return new_entries, current_line
    
    def process_received_summary_incremental(self, server_name, summary_file_path):
        """Process received_summary.txt with the correct format"""
        if not os.path.exists(summary_file_path):
            logger.warning(f"Summary file not found: {summary_file_path}")
            return 0, 0
        
        checkpoint = self.get_checkpoint(server_name)
        last_received_count = checkpoint['last_received_count']
        
        new_files = 0
        current_count = 0
        
        conn = sqlite3.connect(self.db_path)
        
        try:
            with open(summary_file_path, 'r') as f:
                in_files_section = False
                
                for line in f:
                    line = line.strip()
                    
                    if "Files Received:" in line:
                        in_files_section = True
                        continue
                    
                    if in_files_section and line.startswith("- "):
                        current_count += 1
                        
                        if current_count <= last_received_count:
                            continue
                        
                        try:
                            # Parse the format: "- from_ubuntu-server-2_20250514_010156.txt (Size: 931 bytes, Date: 2025-05-14 01:01:57.15534749Z +0000 UTC)"
                            parts = line[2:].split(' (Size: ')
                            filename = parts[0].strip()
                            
                            # Extract source server
                            source_server = "unknown"
                            if filename.startswith("from_ubuntu-server-") and "_" in filename:
                                try:
                                    # Extract server number from "from_ubuntu-server-X_..."
                                    parts_name = filename.split("_")
                                    if len(parts_name) >= 3:
                                        source_server = f"ubuntu-server-{parts_name[2]}"
                                except:
                                    pass
                            
                            file_size_str = ""
                            received_date = ""
                            
                            if len(parts) > 1:
                                # Parse "931 bytes, Date: 2025-05-14 01:01:57.15534749Z +0000 UTC)"
                                size_and_date = parts[1]
                                
                                # Extract size
                                if "bytes, Date:" in size_and_date:
                                    size_part = size_and_date.split(" bytes, Date:")[0].strip()
                                    file_size_str = f"{size_part} bytes"
                                    
                                    # Extract date
                                    date_part = size_and_date.split("Date: ")[1].strip().rstrip(")")
                                    # Simplify the date format
                                    if " " in date_part:
                                        received_date = date_part.split(" ")[0] + " " + date_part.split(" ")[1].split(".")[0]
                            
                            file_size = self.parse_file_size(file_size_str)
                            
                            conn.execute('''
                                INSERT OR IGNORE INTO received_files 
                                (server_name, filename, source_server, received_date, file_size)
                                VALUES (?, ?, ?, ?, ?)
                            ''', (server_name, filename, source_server, received_date, file_size_str))
                            
                            new_files += 1
                            logger.info(f"📥 Recorded received: {server_name} <- {source_server} ({filename}, {file_size_str})")
                            
                            if received_date:
                                date = received_date.split(' ')[0]
                                self.update_daily_activity(conn, date, server_name, 'received', file_size)
                            
                        except sqlite3.IntegrityError:
                            pass
                        except Exception as e:
                            logger.error(f"Error parsing received file line: {line} - {str(e)}")
                    
                    elif in_files_section and line.startswith("Total Files:"):
                        in_files_section = False
            
            conn.commit()
            
        except Exception as e:
            logger.error(f"Error processing summary file for {server_name}: {str(e)}")
            conn.rollback()
        finally:
            conn.close()
        
        return new_files, current_count
    
    def update_daily_activity(self, conn, date, server_name, action, file_size):
        """Update daily activity summary"""
        try:
            if action == 'sent':
                conn.execute('''
                    INSERT INTO daily_activity (date, server_name, files_sent, total_size_sent)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(date, server_name) DO UPDATE SET
                    files_sent = files_sent + 1,
                    total_size_sent = total_size_sent + ?
                ''', (date, server_name, file_size, file_size))
            elif action == 'received':
                conn.execute('''
                    INSERT INTO daily_activity (date, server_name, files_received, total_size_received)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(date, server_name) DO UPDATE SET
                    files_received = files_received + 1,
                    total_size_received = total_size_received + ?
                ''', (date, server_name, file_size, file_size))
        except Exception as e:
            logger.error(f"Error updating daily activity: {str(e)}")
    
    def incremental_update_server(self, server_name):
        """Perform incremental update for a single server"""
        base_dir = './exchange_results'
        server_path = os.path.join(base_dir, server_name, 'logs')
        
        if not os.path.exists(server_path):
            logger.warning(f"Server logs directory not found: {server_path}")
            return {"new_exchanges": 0, "new_received": 0, "total_exchanges": 0, "total_received": 0}
        
        # Process files
        new_exchanges, history_lines = self.process_history_file_incremental(server_name, os.path.join(server_path, 'history.csv'))
        new_received, received_count = self.process_received_summary_incremental(server_name, os.path.join(server_path, 'received_summary.txt'))
        
        # Update checkpoint
        checkpoint = self.get_checkpoint(server_name)
        total_exchanges = checkpoint.get('total_processed_exchanges', 0) + new_exchanges
        total_received = checkpoint.get('total_processed_received', 0) + new_received
        
        self.update_checkpoint(server_name, history_lines, received_count, total_exchanges, total_received)
        self.update_server_totals(server_name)
        
        return {
            "new_exchanges": new_exchanges,
            "new_received": new_received,
            "total_exchanges": total_exchanges,
            "total_received": total_received
        }
    
    def update_server_totals(self, server_name):
        """Update server total counts"""
        conn = sqlite3.connect(self.db_path)
        
        sent_count = conn.execute(
            'SELECT COUNT(*) as count FROM file_exchanges WHERE server_name = ? AND action = "sent"',
            (server_name,)
        ).fetchone()[0]
        
        received_count = conn.execute(
            'SELECT COUNT(*) as count FROM received_files WHERE server_name = ?',
            (server_name,)
        ).fetchone()[0]
        
        latest_exchange = conn.execute(
            'SELECT timestamp FROM file_exchanges WHERE server_name = ? ORDER BY timestamp DESC LIMIT 1',
            (server_name,)
        ).fetchone()
        
        last_exchange = latest_exchange[0] if latest_exchange else None
        
        server_ips = {
            "ubuntu-server-1": "192.168.56.101",
            "ubuntu-server-2": "192.168.56.102", 
            "ubuntu-server-3": "192.168.56.103"
        }
        
        conn.execute('''
            INSERT OR REPLACE INTO servers 
            (name, ip, sent, received, last_update)
            VALUES (?, ?, ?, ?, ?)
        ''', (server_name, server_ips.get(server_name, 'Unknown'), sent_count, received_count, last_exchange))
        
        conn.commit()
        conn.close()
        
        logger.info(f"📊 Updated totals for {server_name}: {sent_count} sent, {received_count} received")
    
    def incremental_update_all(self):
        """Analyze all servers"""
        servers = ["ubuntu-server-1", "ubuntu-server-2", "ubuntu-server-3"]
        total_updates = {"new_exchanges": 0, "new_received": 0, "total_historical": 0}
        
        logger.info("🔍 Starting historical activity analysis...")
        
        for server_name in servers:
            try:
                result = self.incremental_update_server(server_name)
                total_updates["new_exchanges"] += result["new_exchanges"]
                total_updates["new_received"] += result["new_received"]
                total_updates["total_historical"] += result["total_exchanges"] + result["total_received"]
                
                logger.info(f"📈 {server_name}: {result['new_exchanges']} new sent, {result['new_received']} new received")
                
            except Exception as e:
                logger.error(f"Error analyzing {server_name}: {str(e)}")
        
        # Update metadata
        conn = sqlite3.connect(self.db_path)
        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?)',
                    ('last_update', datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.execute('INSERT OR REPLACE INTO metadata VALUES (?, ?)',
                    ('last_incremental_update', datetime.now().isoformat()))
        conn.commit()
        conn.close()
        
        logger.info(f"📊 Analysis completed: {total_updates['new_exchanges']} new exchanges, {total_updates['new_received']} new received files")
        
        return total_updates
    
    def get_incremental_stats(self):
        """Get statistics"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        stats = {}
        
        checkpoints = conn.execute('SELECT * FROM file_checkpoints').fetchall()
        for checkpoint in checkpoints:
            stats[checkpoint['server_name']] = dict(checkpoint)
        
        total_exchanges = conn.execute('SELECT COUNT(*) as count FROM file_exchanges').fetchone()[0]
        total_received = conn.execute('SELECT COUNT(*) as count FROM received_files').fetchone()[0]
        
        stats['totals'] = {
            'total_exchanges': total_exchanges,
            'total_received_files': total_received
        }
        
        last_update = conn.execute('SELECT value FROM metadata WHERE key = "last_incremental_update"').fetchone()
        stats['last_incremental_update'] = last_update[0] if last_update else None
        
        conn.close()
        return stats
