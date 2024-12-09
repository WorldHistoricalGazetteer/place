![img.png](img.png)

# World Historical Gazetteer: PLACE

### This is the repository for the **WHG PLACE** (Place Linkage, Alignment, and Concordance Engine).

It contains the Kubernetes server configuration files for deploying and managing the World Historical Gazetteer (WHG)
application. This repository is separate from the main Django application
code ([here](https://github.com/WorldHistoricalGazetteer/whg3)), and provides a dedicated space for
configuring and orchestrating the server environment.

## Overview

This repository includes configuration files for deploying the following components:

### System Components

- ##### kubeadm

  > A tool for bootstrapping Kubernetes clusters, providing easy and consistent cluster creation.

- ##### kubelet

  > The node agent running on each Kubernetes node, ensuring containers are running as expected.

- ##### kubectl

  > A command-line tool for interacting with Kubernetes clusters, allowing users to deploy and manage applications.

- ##### Helm

  > A Kubernetes package manager that simplifies the deployment and management of Kubernetes applications using Helm
  charts.

- ##### Flannel

  > A networking solution for Kubernetes that provides a virtual network to manage IP address assignments for containers
  and nodes.

- ##### Contour

  > An ingress controller for Kubernetes that uses the Envoy Proxy to manage incoming HTTP and HTTPS requests, acting as
  a reverse proxy and load balancer.

### Application Components

- [x] **Django**

  > A high-level Python web framework used to build the WHG application, providing a structure for building web
  applications quickly.

- [x] **PostgreSQL (with PostGIS)**

  > An open-source relational database system, storing the historical geographic data and other application-related
  information.

- [x] **pgBackRest**

  > A backup and restore tool for PostgreSQL, providing efficient and reliable backups of the WHG database.

- [x] **Redis**

  > An in-memory key-value store used for caching and as a message broker, supporting the speed and scalability of the
  application.

- [x] **Celery**

  > A distributed task queue that allows the WHG application to handle asynchronous tasks efficiently, improving
  performance by offloading long-running tasks.

- [x] **Celery Beat**

  > A scheduler that manages periodic tasks, automating the execution of routine operations like database cleanups or
  batch jobs.

- [x] **Celery Flower**

  > A monitoring tool for Celery, providing insights into the status and performance of Celery workers and tasks.

- [x] **Tileserver-GL**

  > A server used for serving vector and raster map tiles, providing geographical visualisations for the WHG.

- [x] **Tippecanoe**

  > A tool that generates vector tiles from large collections of GeoJSON data, enabling efficient rendering of map
  layers.

- [ ] **Vespa**

  > A platform for serving scalable data and content, commonly used in search and recommendation systems.

- [ ] **Wordpress**

  > A content management system used for the WHG blog, providing a platform for creating and managing blog posts.

### Monitoring and Analytics Components

- [ ] **Prometheus**

  > A monitoring and alerting toolkit that collects metrics from the WHG application and its components, helping to
  ensure the system is running smoothly.

- [ ] **Grafana**

  > A visualization tool that displays metrics collected by Prometheus, providing insights into the performance and
  health of the WHG application.

- [ ] **Plausible**

  > An open-source analytics platform that tracks user interactions with the WHG website, providing insights into user
  behavior and engagement.

- [ ] **Glitchtip**

  > An error monitoring tool that collects and aggregates error reports from the WHG application, helping to identify
  and resolve issues quickly.

## Setup

### Prepare the Server Environment

To deploy the application with these configurations to a remote server, you will need:

- A server running Ubuntu 20.04 LTS
- The server's IP address
- A user with sudo privileges
- A set of private files containing the necessary credentials for the application. These should be placed in a directory
  named `whg-private` in the project root directory. The files include:
    - ca-cert.pem (for Kubernetes)
    - env_template.py (for Django settings)
    - id_rsa_whg (for SSH access to original WHG server)
    - local_settings.py (for Django settings)
    - secret.yaml (for Kubernetes secrets)

Once you have these, follow these steps:

#### Update repositories and install essential packages:

```bash
cd ~ # Change to the home directory
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git unzip htop ufw
git clone https://github.com/WorldHistoricalGazetteer/place.git
```

#### Configure Networking

- Flannel's vxlan backend requires the br_netfilter kernel module for proper network filtering in bridged networks.
- The required networking parameters should persist across reboots to ensure consistent network behavior.

```bash
# Load br_netfilter module and ensure that it reloads on boot
sudo modprobe br_netfilter
echo "br_netfilter" | sudo tee /etc/modules-load.d/br_netfilter.conf

# Enable IPv4 packet forwarding and bridge-nf-call-iptables
sudo tee /etc/sysctl.d/k8s.conf <<EOF
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF

# Apply sysctl params without reboot
sudo sysctl --system
```

#### SSH Keys

```bash
ssh-keygen -t rsa -b 4096 -C "no.reply.whgazetteer@gmail.com"
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_rsa
ssh-copy-id <sudo-user@server-IP>
```

Edit the /etc/ssh/sshd_config file to enhance security:

```bash
sudo nano /etc/ssh/sshd_config
```

Change the following settings:

```plaintext
# Disable root login
PermitRootLogin no

# Change default SSH port (optional - pick a port number in the range 1024-49151)
Port <nnnn>

# Restrict user access
AllowUsers <users>
AllowGroups <groups>

# Enable public key authentication and disable password authentication
PubkeyAuthentication yes
PasswordAuthentication no

# Configure idle timeout
ClientAliveInterval 300
ClientAliveCountMax 2

# Limit authentication attempts
MaxAuthTries 3
```

Restart the SSH service:

```bash
sudo systemctl restart sshd
```

#### Firewall

Ensure that `ufw` is disabled (firewall rules are managed by the Kubernetes cluster using IPTables directly):

```bash
sudo ufw disable
sudo systemctl disable ufw
```

### Set the K8S_ID environment variable

The server will be configured in a role dependent on the value of the `K8S_ID` environment variable, a unique identifier
for the server, which should be set before running the deployment script. Valid values can be seen in the `functions.sh`
script. For example:

```bash
export K8S_ID=LOCAL
```

### Create and Populate Persistent Volumes

Before deploying the application, you will need to create and populate the necessary persistent volumes, which are
determined by the `K8S_ID` environment variable. The most recent backup of the WHG database will be cloned if necessary,
and the Django app's `media` and `static` directories synchronised with the original WHG server.

```bash
sudo chmod +x ./*.sh && sudo -E ./create-persistent-volumes.sh
```

### Deploy the Application

Run the `deploy.sh` script to deploy the application, specifying the role as `master`, `worker`, or `local`. The master
and local options set up the entire application stack, including Vespa, Django, and related services. The worker nodes
should be set up on separate machines, and replicate only Vespa components for horizontal scaling. Pass the role and,
for workers, provide the Kubernetes join command. The master option is dependent on DNS having been set up to point
various subdomains to the server's IP address.

#### Control & Development Nodes

```bash
sudo chmod +x ./*.sh && sudo ./deploy.sh
```

#### Worker Nodes

```bash
# You MUST replace <kubeadm-join-command> with the actual join command from the master node.
sudo chmod +x ./*.sh && sudo ./deploy.sh "<kubeadm-join-command>"
```

#### Access the Application (Development)

Local deployments can be accessed in a browser
at <a href="http://localhost:8000" target="_blank">http://localhost:8000</a>.
Local map tileserver can be accessed in a browser
at <a href="http://localhost:30080/" target="_blank">http://localhost:30080/</a>.

### Re-deploy Services

To re-deploy services on a Control or Development node after making changes to their configuration files, run the
`deploy-services.sh` script:

```bash
sudo chmod +x ./*.sh && sudo ./deploy-services.sh
```
