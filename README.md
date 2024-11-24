# World Historical Gazetteer: PLACE

This is the repository for **WHG PLACE** (Place Linkage, Alignment, and Concordance Engine).

It contains the Kubernetes server configuration files for deploying and managing the World Historical Gazetteer (WHG)
application. This repository is separate from the main Django application
code ([here](https://github.com/WorldHistoricalGazetteer/whg3)), providing a dedicated space for
configuring and orchestrating the server environment.

## Overview

This repository includes configuration files for deploying the following components:

##### Docker

A platform for packaging applications into portable containers.

##### kubeadm

A tool for bootstrapping Kubernetes clusters, providing easy and consistent cluster creation.

##### kubelet

The node agent running on each Kubernetes node, ensuring containers are running as expected.

##### kubectl

A command-line tool for interacting with Kubernetes clusters, allowing users to deploy and manage applications.

##### Helm

A Kubernetes package manager that simplifies the deployment and management of Kubernetes applications using Helm charts.

##### Flannel

A networking solution for Kubernetes that provides a virtual network to manage IP address assignments for containers and
nodes.

##### Contour

An ingress controller for Kubernetes that uses the Envoy Proxy to manage incoming HTTP and HTTPS requests, acting as a
reverse proxy and load balancer.

##### Vespa

A platform for serving scalable data and content, commonly used in search and recommendation systems.

##### Django

A high-level Python web framework used to build the WHG application, providing a structure for building web applications
quickly.

##### PostgreSQL

An open-source relational database system, storing the historical geographic data and other application-related
information.

##### Redis

An in-memory key-value store used for caching and as a message broker, supporting the speed and scalability of the
application.

##### Celery

A distributed task queue that allows the WHG application to handle asynchronous tasks efficiently, improving performance
by offloading long-running tasks.

##### Celery Beat

A scheduler that manages periodic tasks, automating the execution of routine operations like database cleanups or batch
jobs.

##### Tileserver-GL

A server used for serving vector map tiles, providing geographical visualizations for the WHG.

##### Tippecanoe

A tool that generates vector tiles from large collections of GeoJSON data, enabling efficient rendering of map layers.

## Setup

### Prepare the Server Environment

To deploy the application with these configurations to a remote server, you will need:

- A server running Ubuntu 20.04 LTS
- The server's IP address
- A user with sudo privileges
- SSH access
- A `secret.yaml` file containing the necessary credentials (contact the WHG team for this), which should be placed in
  the server's
  home directory

Once you have these, follow these steps:

#### Update repositories and install essential packages:

```bash
cd ~ # Change to the home directory
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git unzip htop ufw
git clone https://github.com/WorldHistoricalGazetteer/place.git
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

```bash
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

**_It is advisable to skip this step until the application is fully deployed and tested as it may interfere with the
Kubernetes setup._**

```bash
sudo ufw allow 6443/tcp     # Kubernetes API Server
sudo ufw allow 8472/udp     # Flannel VXLAN
sudo ufw allow 10250/tcp    # Kubelet
sudo ufw allow 10255/tcp    # Kubelet read-only
sudo ufw allow 30000:32767/tcp   # NodePort services
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp    # Allow HTTP traffic
sudo ufw allow 443/tcp   # Allow HTTPS traffic
sudo ufw enable
sudo ufw status
```

### Deploy the Application

Run the `deploy.sh` script to deploy the application, specifying the role as `master` or `worker`. The master node
sets up the entire application stack, including Vespa, Django, and related services. The worker nodes should be set
up on separate machines, and replicate only Vespa components for horizontal scaling. Pass the role and, for workers,
provide the Kubernetes join command.

> NOTE: If you have already run this script and need to re-run it, you will need to tear down the existing cluster. No
> reliable way to do this has been identified, other than rebooting the server. The script at `./remove-kubernetes.sh`
> follows official Kubernetes documentation, but does not release the ports as expected.

### Master Node

```bash
sudo chmod +x ./*.sh && ./deploy.sh master
```

### Worker Node

```bash
# You MUST replace <kubeadm-join-command> with the actual join command from the master node.
sudo chmod +x ./*.sh && ROLE=worker JOIN_COMMAND="<kubeadm-join-command>" ./deploy.sh
```

### Local Node (for development)

```bash
sudo chmod +x ./*.sh && ./deploy.sh local
```
