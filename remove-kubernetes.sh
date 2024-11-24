# Reset Kubernetes settings
sudo kubeadm reset -f
sudo systemctl stop kubelet
sudo systemctl stop containerd

# Remove the CNI configuration
sudo rm -rf /etc/cni/net.d

# Remove the kubelet and kubeadm packages
sudo apt-get purge -y kubeadm kubelet kubectl
sudo apt-get autoremove -y

# Clean up iptables or nftables
sudo iptables -F
sudo iptables -X
sudo nft flush ruleset

# Remove the Kubernetes directories and data
sudo rm -rf /etc/kubernetes
sudo rm -rf /var/lib/kubelet
sudo rm -rf /var/lib/etcd
sudo rm -rf /var/run/kubernetes

# Check if Kubernetes components are removed
sudo lsof -i :6443