import os
import paramiko
import time
import tempfile
from datetime import datetime
import logging
import socket
import stat

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SSHLogCollector:
    def __init__(self):
        self.servers = [
            {"name": "ubuntu-server-1", "ip": "192.168.56.101"},
            {"name": "ubuntu-server-2", "ip": "192.168.56.102"},
            {"name": "ubuntu-server-3", "ip": "192.168.56.103"}
        ]
        self.ssh_user = "vagrant"
        self.ssh_keys_path = "/app/ssh_keys"
        self.output_dir = "/app/exchange_results"
        self.remote_log_dir = "/home/vagrant/exchange/logs"
        
        # SSH connection settings
        self.connection_timeout = 15
        self.banner_timeout = 15
        self.auth_timeout = 15
        
    def validate_ssh_keys_directory(self):
        """Validate SSH keys directory and list available keys"""
        if not os.path.exists(self.ssh_keys_path):
            logger.error(f"❌ SSH keys directory not found: {self.ssh_keys_path}")
            return False
        
        try:
            # List all files in SSH keys directory
            all_files = os.listdir(self.ssh_keys_path)
            logger.info(f"📂 SSH keys directory contents: {len(all_files)} files")
            
            # Find ed25519 private keys (not .pub files)
            private_keys = [f for f in all_files if f.endswith("id_ed25519") and not f.endswith(".pub")]
            
            if not private_keys:
                logger.error(f"❌ No ed25519 private keys found in {self.ssh_keys_path}")
                logger.info(f"Available files: {all_files}")
                return False
            
            logger.info(f"🔑 Found {len(private_keys)} ed25519 private keys")
            return True
            
        except Exception as e:
            logger.error(f"❌ Error validating SSH keys directory: {str(e)}")
            return False
    
    def get_ssh_key_path(self, server_name):
        """Get the SSH key path for a specific server"""
        if not self.validate_ssh_keys_directory():
            raise FileNotFoundError(f"SSH keys directory validation failed: {self.ssh_keys_path}")
        
        # Try server-specific key first
        specific_key = os.path.join(self.ssh_keys_path, f"{server_name}_id_ed25519")
        if os.path.exists(specific_key):
            logger.info(f"🔑 Using server-specific key for {server_name}")
            return specific_key
        
        # Fall back to generic key
        try:
            for file in os.listdir(self.ssh_keys_path):
                if file.endswith("id_ed25519") and not file.endswith(".pub"):
                    key_path = os.path.join(self.ssh_keys_path, file)
                    logger.info(f"🔑 Using fallback key {file} for {server_name}")
                    return key_path
        except Exception as e:
            logger.error(f"❌ Error scanning for keys: {str(e)}")
        
        raise FileNotFoundError(f"No SSH key found for {server_name}")
    
    def test_network_connectivity(self, server_ip, port=22):
        """Test basic network connectivity before SSH"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((server_ip, port))
            sock.close()
            
            if result == 0:
                logger.info(f"✅ Network connectivity to {server_ip}:{port} successful")
                return True
            else:
                logger.error(f"❌ Network connectivity to {server_ip}:{port} failed")
                return False
        except Exception as e:
            logger.error(f"❌ Network test to {server_ip} failed: {str(e)}")
            return False
    
    def create_ssh_client(self, server_ip, key_path):
        """Create and configure SSH client"""
        # First test network connectivity
        if not self.test_network_connectivity(server_ip):
            logger.error(f"❌ Network unreachable: {server_ip}")
            return None
        
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        temp_key_path = None
        try:
            # Validate key file
            if not os.path.exists(key_path):
                logger.error(f"❌ SSH key file not found: {key_path}")
                return None
            
            # Create temporary copy with proper permissions
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.key') as temp_key:
                with open(key_path, 'r') as original_key:
                    key_content = original_key.read()
                    if not key_content.strip():
                        logger.error(f"❌ SSH key file is empty: {key_path}")
                        return None
                    temp_key.write(key_content)
                temp_key_path = temp_key.name
            
            os.chmod(temp_key_path, 0o600)
            
            # Load private key
            try:
                private_key = paramiko.Ed25519Key.from_private_key_file(temp_key_path)
                logger.info(f"🔑 Loaded Ed25519 key successfully")
            except Exception as e:
                logger.error(f"❌ Failed to load SSH key: {str(e)}")
                return None
            
            # Connect
            logger.info(f"🔗 Attempting SSH connection to {self.ssh_user}@{server_ip}...")
            
            client.connect(
                hostname=server_ip,
                username=self.ssh_user,
                pkey=private_key,
                timeout=self.connection_timeout,
                banner_timeout=self.banner_timeout,
                auth_timeout=self.auth_timeout,
                look_for_keys=False,
                allow_agent=False
            )
            
            # Test connection
            stdin, stdout, stderr = client.exec_command('echo "SSH test successful"', timeout=10)
            test_output = stdout.read().decode().strip()
            
            if "SSH test successful" in test_output:
                logger.info(f"✅ SSH connection verified for {server_ip}")
                return client
            else:
                logger.error(f"❌ SSH connection test failed for {server_ip}")
                client.close()
                return None
            
        except paramiko.AuthenticationException:
            logger.error(f"❌ SSH authentication failed for {server_ip}")
            client.close()
            return None
        except paramiko.SSHException as e:
            logger.error(f"❌ SSH connection failed for {server_ip}: {str(e)}")
            client.close()
            return None
        except socket.timeout:
            logger.error(f"❌ SSH connection timeout for {server_ip}")
            client.close()
            return None
        except Exception as e:
            logger.error(f"❌ Unexpected error connecting to {server_ip}: {str(e)}")
            client.close()
            return None
        finally:
            # Clean up temporary key
            if temp_key_path and os.path.exists(temp_key_path):
                try:
                    os.unlink(temp_key_path)
                except:
                    pass
    
    def verify_remote_directory(self, ssh_client, server_name):
        """Verify remote log directory exists"""
        try:
            stdin, stdout, stderr = ssh_client.exec_command(f'test -d {self.remote_log_dir} && echo "EXISTS" || echo "MISSING"', timeout=10)
            result = stdout.read().decode().strip()
            
            if result == "MISSING":
                logger.error(f"❌ Remote log directory missing on {server_name}: {self.remote_log_dir}")
                return False
            
            logger.info(f"✅ Remote log directory accessible on {server_name}")
            return True
                
        except Exception as e:
            logger.error(f"❌ Error verifying remote directory on {server_name}: {str(e)}")
            return False
    
    def download_file_with_backup(self, sftp, remote_path, local_path):
        """Download a file via SFTP"""
        try:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # Backup existing file
            if os.path.exists(local_path):
                backup_path = f"{local_path}.backup.{int(time.time())}"
                os.rename(local_path, backup_path)
                logger.info(f"📦 Backed up existing file")
            
            # Download file
            sftp.get(remote_path, local_path)
            
            if os.path.exists(local_path):
                file_size = os.path.getsize(local_path)
                logger.info(f"📥 Downloaded: {os.path.basename(remote_path)} ({file_size} bytes)")
                return True
            else:
                logger.error(f"❌ Download failed: {remote_path}")
                return False
            
        except FileNotFoundError:
            logger.warning(f"⚠️  Remote file not found: {remote_path}")
            return False
        except Exception as e:
            logger.error(f"❌ Failed to download {remote_path}: {str(e)}")
            return False
    
    def collect_server_logs(self, server):
        """Download logs from a single server"""
        server_name = server["name"]
        server_ip = server["ip"]
        
        logger.info(f"🔄 Collecting logs from {server_name} ({server_ip})")
        
        try:
            # Get SSH key
            key_path = self.get_ssh_key_path(server_name)
            
            # Create SSH client
            ssh_client = self.create_ssh_client(server_ip, key_path)
            if not ssh_client:
                return {"success": False, "error": "SSH connection failed"}
            
            # Verify remote directory
            if not self.verify_remote_directory(ssh_client, server_name):
                ssh_client.close()
                return {"success": False, "error": "Remote log directory not accessible"}
            
            # Create SFTP client
            try:
                sftp = ssh_client.open_sftp()
            except Exception as e:
                logger.error(f"❌ Failed to create SFTP connection: {str(e)}")
                ssh_client.close()
                return {"success": False, "error": f"SFTP failed: {str(e)}"}
            
            # Create local directory
            server_dir = os.path.join(self.output_dir, server_name, "logs")
            os.makedirs(server_dir, exist_ok=True)
            
            # List remote files
            try:
                remote_files = sftp.listdir(self.remote_log_dir)
                logger.info(f"📋 Found {len(remote_files)} files in remote directory")
            except Exception as e:
                logger.error(f"❌ Error listing remote directory: {str(e)}")
                sftp.close()
                ssh_client.close()
                return {"success": False, "error": str(e)}
            
            if not remote_files:
                logger.warning(f"⚠️  No files found in remote directory")
                sftp.close()
                ssh_client.close()
                return {"success": False, "error": "No log files found"}
            
            # Download files
            downloaded_files = []
            
            for filename in remote_files:
                remote_path = f"{self.remote_log_dir}/{filename}"
                local_path = os.path.join(server_dir, filename)
                
                if self.download_file_with_backup(sftp, remote_path, local_path):
                    downloaded_files.append(filename)
                
                time.sleep(0.1)  # Small delay
            
            # Close connections
            sftp.close()
            ssh_client.close()
            
            logger.info(f"✅ Collection completed: {len(downloaded_files)}/{len(remote_files)} files")
            
            return {
                "success": len(downloaded_files) > 0,
                "files_collected": len(downloaded_files),
                "total_files": len(remote_files),
                "files": downloaded_files
            }
            
        except Exception as e:
            logger.error(f"❌ Error collecting from {server_name}: {str(e)}")
            return {"success": False, "error": str(e)}
    
    def collect_all_logs(self):
        """Download logs from all servers"""
        logger.info(f"🚀 Starting log collection at {datetime.now()}")
        
        # Validate SSH keys
        if not self.validate_ssh_keys_directory():
            return {"success": False, "error": "SSH keys validation failed"}
        
        results = {}
        success_count = 0
        total_files = 0
        
        for server in self.servers:
            server_name = server["name"]
            logger.info(f"\n📡 Processing {server_name}...")
            
            result = self.collect_server_logs(server)
            results[server_name] = result
            
            if result["success"]:
                success_count += 1
                total_files += result.get("files_collected", 0)
            else:
                logger.error(f"❌ {server_name}: {result.get('error', 'Unknown error')}")
            
            time.sleep(1)  # Delay between servers
        
        # Create metadata
        collection_metadata = {
            "collection_time": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            "successful_servers": success_count,
            "total_servers": len(self.servers),
            "total_files_collected": total_files,
            "server_results": results
        }
        
        # Save metadata
        try:
            metadata_file = os.path.join(self.output_dir, "collection_metadata.json")
            with open(metadata_file, 'w') as f:
                import json
                json.dump(collection_metadata, f, indent=2)
        except Exception as e:
            logger.error(f"❌ Failed to save metadata: {str(e)}")
        
        # Summary
        if success_count > 0:
            logger.info(f"✅ Collection completed: {success_count}/{len(self.servers)} servers, {total_files} files")
        else:
            logger.error(f"❌ Collection failed for all servers")
            logger.error("🔧 Troubleshooting tips:")
            logger.error("   1. Check if VMs are running: vagrant status")
            logger.error("   2. Test network: ping 192.168.56.101")
            logger.error("   3. Test SSH manually: ssh -i /path/to/key vagrant@192.168.56.101")
        
        return {
            "success": success_count > 0,
            "successful_servers": success_count,
            "total_servers": len(self.servers),
            "total_files": total_files,
            "results": results
        }
    
    def test_connectivity(self):
        """Test SSH connectivity to all servers"""
        logger.info("🔗 Testing SSH connectivity...")
        
        results = {}
        
        # Validate SSH keys first
        if not self.validate_ssh_keys_directory():
            return {"error": "SSH keys validation failed"}
        
        for server in self.servers:
            server_name = server["name"]
            server_ip = server["ip"]
            
            logger.info(f"🧪 Testing {server_name} ({server_ip})...")
            
            try:
                # Test network connectivity
                if not self.test_network_connectivity(server_ip):
                    results[server_name] = {
                        "status": "failed",
                        "ip": server_ip,
                        "error": "Network unreachable - VMs may not be running"
                    }
                    continue
                
                # Get SSH key
                key_path = self.get_ssh_key_path(server_name)
                
                # Test SSH connection
                ssh_client = self.create_ssh_client(server_ip, key_path)
                
                if ssh_client:
                    # Test remote directory and count files
                    directory_accessible = self.verify_remote_directory(ssh_client, server_name)
                    
                    file_count = 0
                    if directory_accessible:
                        try:
                            stdin, stdout, stderr = ssh_client.exec_command(f'ls {self.remote_log_dir} 2>/dev/null | wc -l')
                            count_output = stdout.read().decode().strip()
                            file_count = int(count_output) if count_output.isdigit() else 0
                        except:
                            file_count = 0
                    
                    ssh_client.close()
                    
                    results[server_name] = {
                        "status": "success",
                        "ip": server_ip,
                        "log_directory": self.remote_log_dir,
                        "files_available": file_count,
                        "response": f"Connected successfully, {file_count} log files available"
                    }
                    logger.info(f"✅ {server_name}: Connected, {file_count} files available")
                else:
                    results[server_name] = {
                        "status": "failed",
                        "ip": server_ip,
                        "error": "SSH authentication failed - check SSH keys"
                    }
                    
            except Exception as e:
                results[server_name] = {
                    "status": "error",
                    "ip": server_ip,
                    "error": str(e)
                }
                logger.error(f"❌ {server_name}: {str(e)}")
        
        # Summary
        successful = sum(1 for r in results.values() if r.get("status") == "success")
        logger.info(f"📊 Connectivity test: {successful}/{len(self.servers)} servers accessible")
        
        if successful == 0:
            logger.error("❌ No servers are accessible!")
            logger.error("🔧 Make sure:")
            logger.error("   1. VMs are running: vagrant up")
            logger.error("   2. Network is configured correctly")
            logger.error("   3. SSH keys are properly installed on VMs")
        
        return results
    
    def get_collection_status(self):
        """Get status of last collection"""
        metadata_file = os.path.join(self.output_dir, "collection_metadata.json")
        
        if not os.path.exists(metadata_file):
            return {"status": "no_collection", "message": "No collections performed yet"}
        
        try:
            with open(metadata_file, 'r') as f:
                import json
                metadata = json.load(f)
            
            return {
                "status": "available",
                "last_collection": metadata.get("collection_time"),
                "successful_servers": metadata.get("successful_servers", 0),
                "total_servers": metadata.get("total_servers", 0),
                "total_files": metadata.get("total_files_collected", 0)
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
