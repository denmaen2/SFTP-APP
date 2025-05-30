#!/bin/bash
# Script to setup automated random file exchange between Vagrant VMs
# Run this from your host machine

# Configuration
SERVERS=("ubuntu-server-1" "ubuntu-server-2" "ubuntu-server-3")
IPS=("192.168.56.101" "192.168.56.102" "192.168.56.103")
SSH_USER="vagrant"
LOG_FILE="setup_random_exchange.log"

# Keys directory
SSH_KEYS_PATH="./ssh_keys_for_host"

echo "$(date): Setting up automated random file exchange between VMs" | tee -a "$LOG_FILE"

# Check if the keys directory exists
if [ ! -d "$SSH_KEYS_PATH" ]; then
    echo "ERROR: SSH keys directory not found at $SSH_KEYS_PATH" | tee -a "$LOG_FILE"
    echo "Please export keys from VMs first" | tee -a "$LOG_FILE"
    exit 1
fi

# Create the script that will run on each VM
cat > vm_random_exchange.sh << 'EOF'
#!/bin/bash
# Script to generate and randomly exchange reports with other VMs
# This script will be uploaded to each VM and run via cron every 20 minutes

# Get server information
MY_HOSTNAME=$(hostname)
MY_IP=$(hostname -I | awk '{print $2}')

# Configure other servers based on hostname
case "$MY_HOSTNAME" in
    "ubuntu-server-1")
        OTHER_SERVERS=("ubuntu-server-2" "ubuntu-server-3")
        OTHER_IPS=("192.168.56.102" "192.168.56.103")
        ;;
    "ubuntu-server-2")
        OTHER_SERVERS=("ubuntu-server-1" "ubuntu-server-3")
        OTHER_IPS=("192.168.56.101" "192.168.56.103")
        ;;
    "ubuntu-server-3")
        OTHER_SERVERS=("ubuntu-server-1" "ubuntu-server-2")
        OTHER_IPS=("192.168.56.101" "192.168.56.102")
        ;;
    *)
        echo "Unknown hostname: $MY_HOSTNAME"
        exit 1
        ;;
esac

# Create directories
mkdir -p ~/exchange/sent
mkdir -p ~/exchange/received
mkdir -p ~/exchange/logs

# Set log file
LOG_FILE=~/exchange/logs/exchange.log
echo "$(date): Starting random file exchange process" >> "$LOG_FILE"

# Generate a status report
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE=~/exchange/sent/status_${MY_HOSTNAME}_${TIMESTAMP}.txt

# Create the report
cat > "$REPORT_FILE" << EOL
Status Report from $MY_HOSTNAME
===============================
Date and Time: $(date)
Hostname: $MY_HOSTNAME
IP Address: $MY_IP

System Information:
------------------
Uptime: $(uptime)
Kernel: $(uname -r)
Disk Space: 
$(df -h / | grep -v Filesystem)

Memory:
$(free -m | grep -v total)

Current Active SSH Sessions:
$(who)

Recent Logins:
$(last | head -5)

File Exchange Status:
--------------------
Files Sent: $(ls -1 ~/exchange/sent/ 2>/dev/null | wc -l)
Files Received: $(ls -1 ~/exchange/received/ 2>/dev/null | wc -l)
Exchange Time: $(date)
EOL

echo "$(date): Generated status report: $REPORT_FILE" >> "$LOG_FILE"

# Randomly decide how many servers to send to (1 or 2)
if [ ${#OTHER_SERVERS[@]} -gt 1 ]; then
    # Generate a random number (1 or 2)
    NUM_SERVERS=$((RANDOM % 2 + 1))
    echo "$(date): Randomly decided to send to $NUM_SERVERS server(s)" >> "$LOG_FILE"
    
    # If we're sending to 1 server, randomly select which one
    if [ $NUM_SERVERS -eq 1 ]; then
        RAND_INDEX=$((RANDOM % ${#OTHER_SERVERS[@]}))
        TARGET_SERVERS=(${OTHER_SERVERS[$RAND_INDEX]})
        TARGET_IPS=(${OTHER_IPS[$RAND_INDEX]})
        echo "$(date): Randomly selected server: ${TARGET_SERVERS[0]}" >> "$LOG_FILE"
    else
        # If we're sending to all servers
        TARGET_SERVERS=("${OTHER_SERVERS[@]}")
        TARGET_IPS=("${OTHER_IPS[@]}")
        echo "$(date): Selected all available servers" >> "$LOG_FILE"
    fi
else
    # If there's only one other server, always send to it
    TARGET_SERVERS=("${OTHER_SERVERS[@]}")
    TARGET_IPS=("${OTHER_IPS[@]}")
fi

# Send the report to selected servers
for ((i=0; i<${#TARGET_SERVERS[@]}; i++)); do
    SERVER=${TARGET_SERVERS[$i]}
    IP=${TARGET_IPS[$i]}
    
    DEST_FILE="from_${MY_HOSTNAME}_${TIMESTAMP}.txt"
    
    echo "$(date): Sending report to $SERVER ($IP)" >> "$LOG_FILE"
    
    # Using SCP to transfer the file
    if scp -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=no "$REPORT_FILE" vagrant@$IP:~/exchange/received/$DEST_FILE; then
        echo "$(date): Successfully sent report to $SERVER" >> "$LOG_FILE"
    else
        echo "$(date): Failed to send report to $SERVER" >> "$LOG_FILE"
    fi
done

# Create a summary of received files
SUMMARY_FILE=~/exchange/logs/received_summary.txt

echo "Received Files Summary for $MY_HOSTNAME" > "$SUMMARY_FILE"
echo "Generated: $(date)" >> "$SUMMARY_FILE"
echo "=======================================" >> "$SUMMARY_FILE"
echo "" >> "$SUMMARY_FILE"

# List all received files
echo "Files Received:" >> "$SUMMARY_FILE"
if [ "$(ls -A ~/exchange/received/ 2>/dev/null)" ]; then
    for file in ~/exchange/received/*; do
        if [ -f "$file" ]; then
            filename=$(basename "$file")
            filedate=$(stat -c "%y" "$file")
            filesize=$(stat -c "%s" "$file")
            echo "- $filename (Size: $filesize bytes, Date: $filedate)" >> "$SUMMARY_FILE"
        fi
    done
else
    echo "No files received yet." >> "$SUMMARY_FILE"
fi

echo "" >> "$SUMMARY_FILE"
echo "Total Files: $(ls -1 ~/exchange/received/ 2>/dev/null | wc -l)" >> "$SUMMARY_FILE"

# Create an exchange log entry
EXCHANGE_LOG=~/exchange/logs/history.csv
# Create header if file doesn't exist
if [ ! -f "$EXCHANGE_LOG" ]; then
    echo "timestamp,hostname,action,target_servers,file,status" > "$EXCHANGE_LOG"
fi

# Add log entry for this exchange
for ((i=0; i<${#TARGET_SERVERS[@]}; i++)); do
    echo "$(date +%Y-%m-%d\ %H:%M:%S),$MY_HOSTNAME,sent,${TARGET_SERVERS[$i]},$(basename $REPORT_FILE),success" >> "$EXCHANGE_LOG"
done

echo "$(date): Created received files summary" >> "$LOG_FILE"
echo "$(date): File exchange process completed" >> "$LOG_FILE"

# Print status if running interactively (not from cron)
if [ -t 1 ]; then
    echo ""
    echo "===== File Exchange Complete ====="
    echo "Server: $MY_HOSTNAME ($MY_IP)"
    echo "Report generated: $(basename $REPORT_FILE)"
    echo "Report sent to: ${TARGET_SERVERS[*]}"
    echo "Files in sent directory: $(ls -1 ~/exchange/sent/ | wc -l)"
    echo "Files in received directory: $(ls -1 ~/exchange/received/ | wc -l)"
    echo "Log file: $LOG_FILE"
    echo "Received files summary: $SUMMARY_FILE"
    echo "=================================="
fi
EOF

# Make the script executable
chmod +x vm_random_exchange.sh

# Create a script to set up the cron job
cat > vm_setup_cron.sh << 'EOF'
#!/bin/bash
# Script to set up scheduled random file exchange on VM

# Create the exchange script if it doesn't exist yet
if [ ! -f ~/vm_random_exchange.sh ]; then
    echo "Error: Exchange script not found!"
    exit 1
fi

# Create a cron job to run the exchange script every 20 minutes
(crontab -l 2>/dev/null || echo "") | grep -v "vm_random_exchange.sh" | { cat; echo "*/20 * * * * ~/vm_random_exchange.sh > ~/exchange/logs/cron_run.log 2>&1"; } | crontab -

echo "Scheduled random file exchange to run every 20 minutes"
echo "Check ~/exchange/logs/cron_run.log for output"

# Create a script to view the latest exchange status
cat > ~/view_exchange.sh << 'VIEW'
#!/bin/bash
# Script to view the current exchange status

clear
echo "===== File Exchange Status for $(hostname) ====="
echo "Generated: $(date)"
echo ""

echo "Files Sent: $(ls -1 ~/exchange/sent/ 2>/dev/null | wc -l)"
echo "Files Received: $(ls -1 ~/exchange/received/ 2>/dev/null | wc -l)"
echo ""

echo "Most Recent Files Sent:"
ls -lt ~/exchange/sent/ 2>/dev/null | head -5 | awk '{print $9, $6, $7, $8}'

echo ""
echo "Most Recent Files Received:"
ls -lt ~/exchange/received/ 2>/dev/null | head -5 | awk '{print $9, $6, $7, $8}'

echo ""
echo "Recent Exchange History:"
if [ -f ~/exchange/logs/history.csv ]; then
    # Skip header, show last 10 entries
    tail -10 ~/exchange/logs/history.csv | column -t -s','
else
    echo "No history available yet"
fi

echo ""
echo "To view detailed logs: less ~/exchange/logs/exchange.log"
echo "To view detailed summary: less ~/exchange/logs/received_summary.txt"
echo "=============================================="
VIEW

chmod +x ~/view_exchange.sh
echo "Created status viewer script: view_exchange.sh"
EOF

# Make the script executable
chmod +x vm_setup_cron.sh

# Deploy and run initial exchange on each VM
for ((i=0; i<${#SERVERS[@]}; i++)); do
    SERVER=${SERVERS[$i]}
    IP=${IPS[$i]}
    
    echo "Setting up $SERVER ($IP)..." | tee -a "$LOG_FILE"
    
    # Find the SSH key for this server
    KEY_FILE="${SSH_KEYS_PATH}/${SERVER}_id_ed25519"
    if [ ! -f "$KEY_FILE" ]; then
        echo "Warning: No specific key found for $SERVER, using first available key" | tee -a "$LOG_FILE"
        KEY_FILE=$(find "$SSH_KEYS_PATH" -type f -name "*id_ed25519" -not -name "*.pub" | head -1)
    fi
    
    # Set proper permissions
    chmod 600 "$KEY_FILE"
    
    # Copy the scripts to the VM
    echo "Copying exchange scripts to $SERVER..." | tee -a "$LOG_FILE"
    scp -i "$KEY_FILE" -o StrictHostKeyChecking=no vm_random_exchange.sh vm_setup_cron.sh $SSH_USER@$IP:~/
    
    if [ $? -eq 0 ]; then
        echo "Successfully copied scripts to $SERVER" | tee -a "$LOG_FILE"
        
        # Set up cron job
        echo "Setting up cron job on $SERVER..." | tee -a "$LOG_FILE"
        ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no $SSH_USER@$IP "chmod +x ~/vm_setup_cron.sh && ~/vm_setup_cron.sh"
        
        # Run the exchange script for initial exchange
        echo "Running initial exchange on $SERVER..." | tee -a "$LOG_FILE"
        ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no $SSH_USER@$IP "chmod +x ~/vm_random_exchange.sh && ~/vm_random_exchange.sh"
    else
        echo "Failed to copy scripts to $SERVER" | tee -a "$LOG_FILE"
    fi
done

# Now wait a bit for exchanges to complete
echo "Waiting for initial exchanges to complete..." | tee -a "$LOG_FILE"
sleep 5

# Retrieve logs and summaries from each VM
echo "Retrieving logs and summaries from VMs..." | tee -a "$LOG_FILE"

# Create a directory for the results
mkdir -p exchange_results

for ((i=0; i<${#SERVERS[@]}; i++)); do
    SERVER=${SERVERS[$i]}
    IP=${IPS[$i]}
    
    echo "Retrieving results from $SERVER ($IP)..." | tee -a "$LOG_FILE"
    
    # Find the SSH key for this server
    KEY_FILE="${SSH_KEYS_PATH}/${SERVER}_id_ed25519"
    if [ ! -f "$KEY_FILE" ]; then
        KEY_FILE=$(find "$SSH_KEYS_PATH" -type f -name "*id_ed25519" -not -name "*.pub" | head -1)
    fi
    
    # Create directory for this server
    mkdir -p exchange_results/$SERVER
    
    # Copy logs and summaries
    scp -i "$KEY_FILE" -o StrictHostKeyChecking=no $SSH_USER@$IP:~/exchange/logs/* exchange_results/$SERVER/ 2>/dev/null
    
    # Get exchange status
    echo "Status for $SERVER:" | tee -a "$LOG_FILE"
    ssh -i "$KEY_FILE" -o StrictHostKeyChecking=no $SSH_USER@$IP "~/view_exchange.sh" | tee -a "$LOG_FILE"
    echo "" | tee -a "$LOG_FILE"
done

echo ""
echo "===== Random File Exchange Setup Complete ====="
echo "Cron jobs set up on all VMs to exchange files every 20 minutes"
echo "Each server will randomly send to 1 or 2 other servers"
echo "Initial exchanges have been performed"
echo "Results are available in the exchange_results directory"
echo "Log file: $LOG_FILE"
echo ""
echo "To view exchange status on any VM:"
echo "vagrant ssh <server-name> -c \"./view_exchange.sh\""
echo ""

# Cleanup
rm -f vm_random_exchange.sh vm_setup_cron.sh
