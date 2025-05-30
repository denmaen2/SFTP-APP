#!/bin/bash

echo "🐳 VM Exchange Monitor - Docker ASCII Dashboard"
echo "=============================================="

check_container() {
    if ! sudo docker compose ps | grep -q "vm-monitor-optimized.*Up"; then
        echo "❌ Container is not running. Starting it..."
        sudo docker compose up -d
        sleep 10
    fi
}

run_dashboard() {
    echo "📊 Running ASCII dashboard..."
    sudo docker compose exec vm-monitor python simple_dashboard.py
}

run_dashboard_watch() {
    echo "📊 Running dashboard in watch mode (Ctrl+C to stop)..."
    sudo docker compose exec vm-monitor python simple_dashboard.py --watch
}

collect_and_show() {
    echo "📥 Collecting logs..."
    curl -s -X POST http://localhost:5000/api/collect
    
    echo "⏳ Waiting for collection..."
    sleep 15
    
    echo "⚡ Processing data..."
    curl -s -X POST http://localhost:5000/api/incremental-update
    
    echo "📊 Showing dashboard..."
    run_dashboard
}

show_status() {
    echo "🔍 Container Status:"
    sudo docker compose ps
    
    echo ""
    echo "📊 Quick Stats:"
    curl -s http://localhost:5000/api/data | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    print(f'Servers: {len(data.get(\"servers\", []))}')
    print(f'Total Sent: {data.get(\"total_sent\", 0)}')
    print(f'Total Received: {data.get(\"total_received\", 0)}')
except:
    print('❌ No data available')
"
}

case "${1:-dashboard}" in
    "dashboard") check_container; run_dashboard ;;
    "watch") check_container; run_dashboard_watch ;;
    "collect") check_container; collect_and_show ;;
    "status") check_container; show_status ;;
    "logs") sudo docker compose logs vm-monitor --tail=30 ;;
    *) echo "Usage: $0 [dashboard|watch|collect|status|logs]" ;;
esac
