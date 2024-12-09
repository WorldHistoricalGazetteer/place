#!/bin/bash

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

# Function to delete all Pods
clean_pods() {
  echo "Deleting all Pods..."
  if ! sudo kubectl delete pod --all; then
    echo "Failed to delete Pods"
  fi
}

# Function to delete all Deployments
clean_deployments() {
  echo "Deleting all Deployments..."
  if ! sudo kubectl delete deployment --all; then
    echo "Failed to delete Deployments"
  fi
}

# Function to delete all ReplicaSets
clean_replicasets() {
  echo "Deleting all ReplicaSets..."
  if ! sudo kubectl delete replicaset --all; then
    echo "Failed to delete ReplicaSets"
  fi
}

# Function to delete all Services
clean_services() {
  echo "Deleting all Services..."
  if ! sudo kubectl delete service --all; then
    echo "Failed to delete Services"
  fi
}

# Function to delete all StatefulSets
clean_statefulsets() {
  echo "Deleting all StatefulSets..."
  if ! sudo kubectl delete statefulset --all; then
    echo "Failed to delete StatefulSets"
  fi
}

# Function to delete all Jobs
clean_jobs() {
  echo "Deleting all Jobs..."
  if ! sudo kubectl delete job --all; then
    echo "Failed to delete Jobs"
  fi
}

# Function to delete all CronJobs
clean_cronjobs() {
  echo "Deleting all CronJobs..."
  if ! sudo kubectl delete cronjob --all; then
    echo "Failed to delete CronJobs"
  fi
}

# Optionally, delete namespaces if needed
clean_namespaces() {
  echo "Deleting all namespaces..."
  if ! sudo kubectl delete ns --all; then
    echo "Failed to delete namespaces"
  fi
}

# Function to kill kubectl port-forward processes with retry
kill_port_forward_processes() {
  echo "Killing any running kubectl port-forward processes..."

  # Loop for multiple attempts if new processes spawn
  for attempt in {1..5}; do
    pids=$(sudo pgrep -f "kubectl port-forward")
    if [ -n "$pids" ]; then
      echo "Found running kubectl port-forward processes with PIDs: $pids"
      for pid in $pids; do
        if sudo kill "$pid"; then
          echo "Successfully killed process $pid"
        else
          echo "Failed to kill process $pid. Trying SIGKILL..."
          sudo kill -9 "$pid" && echo "Successfully killed process $pid with SIGKILL"
        fi
      done
    else
      echo "No kubectl port-forward processes found."
      break
    fi
    sleep 1  # Wait before retrying
  done
}

# Execute the cleanup functions
helm uninstall wordpress

clean_pvcs
clean_pvs
clean_pods
clean_deployments
clean_replicasets
clean_services
clean_statefulsets
clean_jobs
clean_cronjobs
# Uncomment if you want to delete namespaces too
# clean_namespaces
kill_port_forward_processes

echo "Cleanup completed."
