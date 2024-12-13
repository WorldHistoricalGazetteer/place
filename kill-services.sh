#!/bin/bash

# Function to delete resources that do not have the critical=true label
delete_non_critical_resources() {
  RESOURCES=( "cronjobs" "jobs" "statefulsets" "deployments" "replicasets" "daemonsets" "pods" "services" "configmaps" "secrets")

  for RESOURCE in "${RESOURCES[@]}"; do
    echo "Deleting $RESOURCE that are not labeled critical=true..."
    if ! sudo kubectl delete "$RESOURCE" --selector 'critical!=true' --all-namespaces; then
      echo "Failed to delete $RESOURCE"
    fi
  done
}

# Function to dissociate PVs from PVCs and delete PVs
clean_pvs() {
  echo "Cleaning up orphaned PVs..."

  # Handle Released PVs
  for pv in $(sudo kubectl get pv --no-headers | awk '{if ($5 == "Released") print $1}'); do
    echo "Removing claimRef for PV: $pv"
    if ! sudo kubectl patch pv "$pv" --type=json -p='[{"op": "remove", "path": "/spec/claimRef"}]'; then
      echo "Failed to remove claimRef for $pv"
    fi
    echo "Deleting PV: $pv"
    if ! sudo kubectl delete pv "$pv"; then
      echo "Failed to delete PV: $pv"
    fi
  done

  # Force delete Terminating PVs
  for pv in $(sudo kubectl get pv --no-headers | awk '{if ($5 == "Terminating") print $1}'); do
    echo "Force-deleting Terminating PV: $pv"
    if ! sudo kubectl patch pv "$pv" --type=json -p='[{"op": "remove", "path": "/metadata/finalizers"}]'; then
      echo "Failed to remove finalizers for $pv"
    fi
    if ! sudo kubectl delete pv "$pv" --force --grace-period=0; then
      echo "Failed to force-delete PV: $pv"
    fi
  done
}

# Function to delete PVCs
clean_pvcs() {
  echo "Cleaning up PVCs..."
  for pvc in $(sudo kubectl get pvc --no-headers | awk '{print $1}'); do
    echo "Deleting PVC: $pvc"
    if ! sudo kubectl delete pvc "$pvc"; then
      echo "Failed to delete PVC: $pvc"
    fi
  done
}

# Function to kill kubectl port-forward processes for specific services with retry
kill_port_forward_processes() {
  echo "Killing any running kubectl port-forward processes for specific services..."

  # Define the specific services and ports to target
  services=("django-service:8000" "prometheus-k8s:9090" "grafana:3000" "alertmanager-main:9093")

  # Loop through the services and ports
  for service in "${services[@]}"; do
    # Extract service name and port
    service_name=$(echo $service | cut -d: -f1)
    port=$(echo $service | cut -d: -f2)

    echo "Checking for kubectl port-forward process for $service_name on port $port..."

    # Loop for multiple attempts if new processes spawn
    for attempt in {1..5}; do
      pids=$(sudo pgrep -f "kubectl port-forward .*${service_name}.*${port}")
      if [ -n "$pids" ]; then
        echo "Found running kubectl port-forward processes for $service_name:$port with PIDs: $pids"
        for pid in $pids; do
          if sudo kill "$pid"; then
            echo "Successfully killed process $pid for $service_name:$port"
          else
            echo "Failed to kill process $pid for $service_name:$port. Trying SIGKILL..."
            sudo kill -9 "$pid" && echo "Successfully killed process $pid for $service_name:$port with SIGKILL"
          fi
        done
      else
        echo "No kubectl port-forward process found for $service_name:$port."
        break
      fi
      sleep 1  # Wait before retrying
    done
  done
}

# Execute the cleanup functions
helm uninstall wordpress

delete_non_critical_resources
clean_pvcs
clean_pvs
kill_port_forward_processes

echo "Cleanup completed."
