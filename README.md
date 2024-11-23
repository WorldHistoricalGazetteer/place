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

To deploy the application with these configurations, follow these steps:

1. Clone this repository and navigate to the project root directory.
2. Acquire the necessary `secret.yaml` credentials file from the WHG team and place it in the root directory.
3. Run the `deploy.sh` script to deploy the application, specifying the role as `master` or `worker`. The master node
   sets up the entire application stack, including Vespa, Django, and related services. The worker nodes should be set
   up on separate machines, and replicate only Vespa components for horizontal scaling. Pass the role and, for workers,
   provide the Kubernetes join command.

### Master Node

```bash
sudo chmod +x ./*.sh && ROLE=master ./deploy.sh
```

### Worker Node

```bash
# You MUST replace <kubeadm-join-command> with the actual join command from the master node.
sudo chmod +x ./*.sh && ROLE=worker JOIN_COMMAND="<kubeadm-join-command>" ./deploy.sh
```
