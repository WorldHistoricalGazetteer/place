# Reset Kubernetes settings
sudo kubeadm reset -f
sudo systemctl stop kubelet
sudo systemctl stop containerd

# Remove the CNI configuration
sudo rm -rf /etc/cni/net.d

# Remove the kubelet and kubeadm packages
sudo apt-get purge -y kubeadm kubelet kubectl
sudo apt-get autoremove -y

# Wait to ensure that package removal is complete
echo "Waiting for package removal to complete..."
sleep 5  # Adjust the sleep time if needed

# Clean up iptables or nftables
sudo iptables -F
sudo iptables -X
sudo nft flush ruleset

# Remove the Kubernetes directories and data
sudo rm -rf /etc/kubernetes
sudo rm -rf /var/lib/kubelet
sudo rm -rf /var/lib/etcd
sudo rm -rf /var/run/kubernetes
sudo rm -rf ~/.kube

# Check if Kubernetes components are removed
echo "Checking for remaining Kubernetes components on port 6443..."
sudo lsof -i :6443 || echo "No process using port 6443 found."

echo "Cleanup completed."