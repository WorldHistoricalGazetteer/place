#!/bin/bash

# Configuration
SERVICES=(
    "whg/svc/tileserver-gl/8080:8080",
    "whg/svc/wordpress/8082:8082",
    # Example of an added service:
    # "default/svc/my-backend/9000:8080"
)
KPROXY_PORT=8001  # Default port for kubectl proxy

PID_FILE="$HOME/k8s_tunnels.pid"

# ANSI Escape Codes for Terminal Formatting
BLUE='\033[0;34m'
BOLD='\033[1m'
GREEN='\033[0;32m'
NC='\033[0m' # No Color/Reset

# Array to hold all final SSH tunnel mappings (e.g., 8010:127.0.0.1:8001)
TUNNEL_MAPPINGS=()

# Array to hold user-friendly access instructions (e.g., "K8s Dashboard: http://localhost:8010/...")
ACCESS_INSTRUCTIONS=()

# --- Functions ---

# Function to start the kubectl proxy for the K8s dashboard
start_dashboard_proxy() {
    echo "--- Kubernetes Dashboard Proxy ---"

    local SSH_LOCAL_PORT=8010
    local DASHBOARD_ACCESS_URL="http://localhost:${SSH_LOCAL_PORT}/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/#/workloads?namespace=whg"

    # Check if kubectl proxy is already running on the KPROXY_PORT
    if ! lsof -iTCP:$KPROXY_PORT -sTCP:LISTEN >/dev/null 2>&1; then
        echo "Starting kubectl proxy on port $KPROXY_PORT..."
        nohup kubectl proxy --address=0.0.0.0 --port=$KPROXY_PORT --disable-filter=true \
            > "$HOME/kubectl_proxy.log" 2>&1 &
        PROXY_PID=$!
        echo $PROXY_PID >> "$PID_FILE"
        echo "kubectl proxy started with PID $PROXY_PID"
    else
        echo "kubectl proxy already running on port $KPROXY_PORT (check for orphaned processes if needed)."
    fi

    # Add the dashboard mapping and instruction to the global arrays
    TUNNEL_MAPPINGS+=("-L ${SSH_LOCAL_PORT}:127.0.0.1:${KPROXY_PORT}")
    ACCESS_INSTRUCTIONS+=("  - **K8s Dashboard**: ${DASHBOARD_ACCESS_URL}")
}

# Function to start service port-forwarding
start_service_forwarding() {
    echo "--- Service Port-Forwarding ---"

    # Base port for local SSH tunnels for services (starting from 8011)
    local SSH_LOCAL_PORT_BASE=8011
    local CURRENT_SSH_PORT=$SSH_LOCAL_PORT_BASE

    for svc_spec in "${SERVICES[@]}"; do
        IFS='/' read -r NAMESPACE SERVICE_TYPE SERVICE_NAME PORT_MAPPING <<< "$svc_spec"
        IFS=':' read -r LOCAL_PORT REMOTE_PORT <<< "$PORT_MAPPING"

        # Check if the remote machine's port is already in use by the port-forward
        if ! lsof -iTCP:$LOCAL_PORT -sTCP:LISTEN >/dev/null 2>&1; then
            echo "Starting port-forwarding for $SERVICE_NAME ($NAMESPACE) on 127.0.0.1:$LOCAL_PORT..."

            # Run in the background and capture PID
            kubectl port-forward -n "$NAMESPACE" "$SERVICE_TYPE/$SERVICE_NAME" "$LOCAL_PORT:$REMOTE_PORT" \
                > "$HOME/${SERVICE_NAME}_pf.log" 2>&1 &
            PF_PID=$!
            echo $PF_PID >> "$PID_FILE"
            echo "Port-forwarding started with PID $PF_PID"

            # Add the service mapping and instruction to the global arrays
            TUNNEL_MAPPINGS+=("-L ${CURRENT_SSH_PORT}:127.0.0.1:${LOCAL_PORT}")

            # Create a clean name for the output
            local CLEAN_NAME=$(echo "$SERVICE_NAME" | tr '[:lower:]' '[:upper:]' | tr '-' ' ')

            # Use http:// for instructions, as most services are web-based
            ACCESS_INSTRUCTIONS+=("  - **${CLEAN_NAME}**: http://localhost:${CURRENT_SSH_PORT}")

            # Increment port for the next service
            CURRENT_SSH_PORT=$((CURRENT_SSH_PORT + 1))
        else
            echo "Port $LOCAL_PORT on the remote machine is already in use, skipping port-forward for $SERVICE_NAME."
        fi
    done

    echo ""
}

# Function to kill all processes listed in the PID file
kill_tunnels() {
    if [ -f "$PID_FILE" ]; then
        echo "Killing processes listed in $PID_FILE..."
        while read -r PID; do
            if kill -0 "$PID" 2>/dev/null; then
                kill "$PID"
                echo "Killed process $PID"
            else
                echo "Process $PID not found or already dead."
            fi
        done < "$PID_FILE"

        rm "$PID_FILE"
        echo "Cleanup complete."
    else
        echo "No tunnel processes found to kill (PID file $PID_FILE not present)."
    fi
}

# --- Main Logic ---

case "$1" in
    start)
        if [ -f "$PID_FILE" ]; then
             echo "Warning: PID file exists. Cleaning up before starting."
             kill_tunnels
        fi
        touch "$PID_FILE"

        # Start background processes and populate arrays
        start_dashboard_proxy
        start_service_forwarding

        echo "✅ All required Kubernetes processes are running in the background."
        echo ""

        # --- Final SSH Command Generation ---
        SSH_HOST="gazetteer.crcd.pitt.edu"
        read -p "Enter your SSH username for ${SSH_HOST}: " -r SSH_USERNAME

        SSH_COMMAND_MAPPINGS=$(IFS=' '; echo "${TUNNEL_MAPPINGS[*]}")

        echo ""
        echo -e " ${BOLD}${BLUE}To access all services from your local machine, run this${NC}"
        echo -e " ${BOLD}${BLUE}chained command in a LOCAL terminal to kill old tunnels and start the new one:${NC}"
        echo ""

        # Single, chained command for the user to copy/paste on their local machine
        SSH_COMMAND="pkill -f 'ssh -fN -L'; sleep 1; ssh -fN ${SSH_COMMAND_MAPPINGS} ${SSH_USERNAME}@${SSH_HOST}"
        echo -e "${GREEN}${SSH_COMMAND}${NC}"
        echo ""

        # Dynamic Access Points Output
        echo -e "  ${BOLD}Access Points (Local Browser):${NC}"
        for instruction in "${ACCESS_INSTRUCTIONS[@]}"; do
            FORMATTED_INSTRUCTION=$(echo "$instruction" | sed 's/\*\*\(.*\)\*\*/\n\t\033[1m\1\033[0m/g')
            FORMATTED_INSTRUCTION=$(echo "$instruction" | sed "s/\*\*\(.*\)\*\*/${BOLD}\1${NC}/g")
            CLEAN_INSTRUCTION=$(echo "$instruction" | sed 's/\*\*//g')
            FORMATTED_INSTRUCTION=$(echo -e "$CLEAN_INSTRUCTION" | sed "s/\(.*\):/${BOLD}\1${NC}:/")
            LABEL=$(echo "$instruction" | cut -d':' -f1 | sed 's/\*\*//g' | sed 's/ - //g')
            URL=$(echo "$instruction" | cut -d':' -f2-)
            echo -e "  - ${BOLD}${LABEL}${NC}:${URL}"
        done

        echo ""
        echo -e "  ${BLUE}Note: Services are mapped to local ports starting at ${BOLD}8010${NC}${BLUE}.${NC}"
        echo ""
        ;;
    kill)
        kill_tunnels
        echo "🛑 Tunnel and proxy processes stopped."
        ;;
    *)
        echo "Usage: $0 {start|kill}"
        exit 1
        ;;
esac