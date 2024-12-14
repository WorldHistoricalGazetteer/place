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

- [x] **Wordpress**

  > A content management system used for the WHG blog, providing a platform for creating and managing blog posts.

### Monitoring and Analytics Components

- [x] **Prometheus**

  > A monitoring and alerting toolkit that collects metrics from the WHG application and its components, helping to
  ensure the system is running smoothly.

- [x] **Grafana**

  > A visualization tool that displays metrics collected by Prometheus, providing insights into the performance and
  health of the WHG application.

- [x] **Plausible**

  > An open-source analytics platform that tracks user interactions with the WHG website, providing insights into user
  behavior and engagement.

- [ ] **Glitchtip**

  > An error monitoring tool that collects and aggregates error reports from the WHG application, helping to identify
  and resolve issues quickly.

## Setup

### Prepare the Server Environment

#### Pre-requisites

To deploy the application with these configurations to a remote server, you will need:

- A server running Ubuntu 20.04 LTS
- The server's IP address
- A user with sudo privileges
- Credentials for fetching Secrets
  from <a href="https://portal.cloud.hashicorp.com/services/secrets/apps/WHG-PLACE/secrets?project_id=be40e446-773e-4069-9913-803be758e6e8" target="_blank">
  HashiCorp Vault</a>. These may be permanently added to the server's environment variables (
  `sudo nano /etc/environment`, followed by a reboot).

#### Set the K8S_ID environment variable

The server will be configured in a role dependent on the value of the `K8S_ID` environment variable, a unique identifier
for the server, which should be set before running the deployment script. Valid values can be seen in the `functions.sh`
script. For example:

```bash
export K8S_ID=LOCAL
```

#### Set the KUBECONFIG environment variable permanently

```bash
grep -qxF 'export KUBECONFIG=/etc/kubernetes/admin.conf' ~/.bashrc || echo 'export KUBECONFIG=/etc/kubernetes/admin.conf' >> ~/.bashrc
source ~/.bashrc
```

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

### Deploy the Application

Run the `deploy.sh` script to deploy the application, including the join command for worker nodes. **Correct functioning
of control nodes is dependent on DNS having been set up to point various subdomains to the server's IP address.**

The script will create and populate the necessary persistent volumes, which are determined by the `K8S_ID` environment
variable. The most recent backup of the WHG database will be cloned if necessary, and the Django app's `media` and
`static` directories synchronised with the original WHG server.

#### Set HashiCorp Credentials

_Ideally, these should have been added already to the server's environment variables (`sudo nano /etc/environment`,
followed by a reboot)._

```bash
export HCP_CLIENT_ID=<HashiCorp Client ID>
export HCP_CLIENT_SECRET=<HashiCorp Client Secret>
```

#### Prevent Database Cloning (optional)

Set this environment variable only if the database has already been cloned by a previous deployment:

```bash
export SKIP_DB_CLONE=true
```

#### Control & Development Nodes

```bash
sudo chmod +x ./*.sh && sudo -E ./deploy.sh
```

##### Expose services (local development only)

```bash
sudo kubectl port-forward svc/django-service 8000:8000 &
sudo kubectl --namespace monitoring port-forward svc/prometheus-k8s 9090 &
sudo kubectl --namespace monitoring port-forward svc/grafana 3000:3000 &
sudo kubectl --namespace monitoring port-forward svc/alertmanager-main 9093 &
sudo kubectl port-forward svc/plausible-analytics 8020:80 &
```

- WHG: <a href="http://localhost:8000" target="_blank">http://localhost:8000</a>
- Tileserver: <a href="http://localhost:30080" target="_blank">http://localhost:30080</a>
- Prometheus: <a href="http://localhost:9090" target="_blank">http://localhost:9090</a>
- Grafana: <a href="http://localhost:3000" target="_blank">http://localhost:3000</a> (initial credentials: admin|admin)
- Alertmanager: <a href="http://localhost:9093" target="_blank">http://localhost:9093</a>
- Plausible: <a href="http://localhost:8020" target="_blank">http://localhost:8020</a>

##### Re-deploy Services

To re-deploy services on a Control or Development node after making changes to their configuration files, run the
`deploy-services.sh` script:

```bash
sudo chmod +x ./*.sh && sudo -E ./deploy-services.sh
```

#### Worker Nodes

```bash
# You MUST replace <kubeadm-join-command> with the actual join command from the master node.
sudo chmod +x ./*.sh && sudo -E ./deploy.sh "<kubeadm-join-command>"
```
