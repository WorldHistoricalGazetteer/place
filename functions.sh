# functions.sh

identify_environment() {
    if [ -z "$HCP_CLIENT_SECRET" ]; then
        echo "HCP_CLIENT_SECRET is not set. Cannot proceed without it."
        exit 1
    fi

    K8S_ID=$(hostname)

    case "$K8S_ID" in
        PITT1)
            K8S_CONTROLLER=1
            K8S_ROLE="general"
            K8S_ENVIRONMENT="production"
            ;;
        PITT2)
            K8S_CONTROLLER=0
            K8S_ROLE="processing"
            K8S_ENVIRONMENT="production"
            ;;
        PITT3)
            K8S_CONTROLLER=1
            K8S_ROLE="all"
            K8S_ENVIRONMENT="staging"
            ;;
        AAU1)
            K8S_CONTROLLER=0
            K8S_ROLE="general"
            K8S_ENVIRONMENT="production"
            ;;
        AAU2)
            K8S_CONTROLLER=0
            K8S_ROLE="processing"
            K8S_ENVIRONMENT="production"
            ;;
        DO1)
            K8S_CONTROLLER=0
            K8S_ROLE="backup"
            K8S_ENVIRONMENT="production"
            ;;
        *)
            K8S_CONTROLLER=1
            K8S_ROLE="all"
            K8S_ENVIRONMENT="development"
            K8S_ID="LOCAL"
            ;;
    esac
    echo "$K8S_ID: CONTROLLER=$K8S_CONTROLLER, ROLE=$K8S_ROLE, ENVIRONMENT=$K8S_ENVIRONMENT"

    # Set the YQ_TLS variable based on the K8S_CONTROLLER value
    if [ "$K8S_CONTROLLER" != 1 ]; then
      YQ_TLS='del(.metadata.annotations["cert-manager.io/cluster-issuer"], .spec.tls)'  # Remove cert-manager and tls section
    else
      YQ_TLS='.'  # No changes to the file (pass it as is)
    fi

    # Export the variables
    export K8S_ID
    export K8S_CONTROLLER
    export K8S_ROLE
    export K8S_ENVIRONMENT
    export YQ_TLS
}

# Wait for the Kubernetes control-plane to be ready
wait_for_k8s() {
    echo "Waiting for Kubernetes control-plane to become ready..."
#    until kubectl version --short &>/dev/null; do sleep 5; done
    until kubectl get nodes | grep -q "Ready"; do sleep 5; done
    echo "Control-plane is ready!"
}

# Function to check if the kubelet is running
check_kubelet_status() {
    echo "Checking kubelet status..."
    systemctl is-active --quiet kubelet
    local status=$?

    if [ $status -ne 0 ]; then
        echo "Error: Kubelet service is not running."
    else
        echo "Kubelet service is running."
    fi
    return $status
}

# Wait for the kubelet to be active
wait_for_kubelet() {
    echo "Waiting for kubelet to be active..."
    while true; do
        if check_kubelet_status; then
            echo "Kubelet is active."
            break
        else
            echo "Kubelet is not active, retrying..."
            sleep 5
        fi
    done
}

remove_kubernetes() {
    echo "Removing pre-existing Kubernetes components..."

    # Check if Kubernetes cluster is accessible
    if kubectl cluster-info &>/dev/null; then
        # Uninstall all Helm releases
        echo "Uninstalling all Helm releases..."
        if command -v helm &> /dev/null; then
            # List Helm releases across all namespaces and extract the release name and namespace
            RELEASES=$(helm list --all-namespaces --output json)

            # Check if any releases are found
            if [[ -n "$RELEASES" && $(echo "$RELEASES" | jq -r 'length') -gt 0 ]]; then
                # Iterate through the releases in the JSON output
                for RELEASE in $(echo "$RELEASES" | jq -r '.[].name'); do
                    # Extract the namespace for the current release
                    NAMESPACE=$(echo "$RELEASES" | jq -r --arg RELEASE "$RELEASE" '.[] | select(.name == $RELEASE) | .namespace')

                    echo "Uninstalling Helm release: $RELEASE in namespace $NAMESPACE..."
                    if ! helm uninstall "$RELEASE" --namespace "$NAMESPACE"; then
                        echo "Failed to uninstall $RELEASE from namespace $NAMESPACE, skipping."
                    fi
                done
            else
                echo "No Helm releases found."
            fi
        else
          echo "Helm not found, skipping Helm release removal."
        fi
    else
        echo "Kubernetes cluster is not accessible. Skipping Helm release removal."
    fi

    # Reset Kubernetes settings, only if kubeadm is available
    if command -v kubeadm &> /dev/null; then
        echo "Running kubeadm reset..."
        sudo kubeadm reset -f
    else
        echo "kubeadm not found, skipping kubeadm reset."
    fi

    # Stop kubelet and containerd services if they exist
    sudo systemctl stop kubelet || echo "kubelet service not found."
    sudo systemctl stop containerd || echo "containerd service not found."

    # Remove the CNI configuration
    sudo rm -rf /etc/cni/net.d

    # Clean up iptables or nftables
    sudo iptables -F
    sudo iptables -X
    sudo nft flush ruleset

    # Remove the Kubernetes directories and data
    sudo rm -rf /etc/kubernetes
    sudo rm -rf /var/lib/kubelet
    sudo rm -rf /var/lib/etcd
    sudo rm -rf /var/run/kubernetes
    sudo rm -rf /root/.kube

    # Check if Kubernetes components are removed
    echo "Checking for remaining Kubernetes components on port 6443..."
    sudo lsof -i :6443 || echo "No process using port 6443 found."

    echo "Cleanup completed."
}
