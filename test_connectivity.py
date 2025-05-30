import socket
import sys

def test_connection(ip, port=22):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((ip, port))
        sock.close()
        return result == 0
    except Exception as e:
        print(f"Error testing {ip}: {str(e)}")
        return False

ips = ['192.168.56.101', '192.168.56.102', '192.168.56.103']
reachable = 0

print("Testing VM connectivity from Docker container:")
for ip in ips:
    if test_connection(ip):
        print(f"✅ {ip}: Connected")
        reachable += 1
    else:
        print(f"❌ {ip}: Failed")

print(f"\nContainer connectivity: {reachable}/3 VMs reachable")
sys.exit(0 if reachable > 0 else 1)
