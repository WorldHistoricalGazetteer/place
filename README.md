# World Historical Gazetteer: PLACE

This is the repository for **WHG PLACE** (Place Linkage, Alignment, and Concordance Engine).

It contains the Kubernetes server configuration files for deploying and managing the World Historical Gazetteer (WHG)
application. This repository is separate from the main Django application code ([here](https://github.com/WorldHistoricalGazetteer/whg3)), providing a dedicated space for
configuring and orchestrating the server environment.

## Overview

This repository includes configuration files for deploying the following components:

##### Docker

A platform that enables developers to package applications into containers for easier deployment across different environments.

##### kubeadm
A tool for bootstrapping Kubernetes clusters, providing easy and consistent cluster creation.

##### kubelet
The node agent running on each Kubernetes node, ensuring containers are running as expected.

##### kubectl
A command-line tool for interacting with Kubernetes clusters, allowing users to deploy and manage applications.

##### Helm
A Kubernetes package manager that simplifies the deployment and management of Kubernetes applications using Helm charts.

##### Flannel
A networking solution for Kubernetes that provides a virtual network to manage IP address assignments for containers and nodes.

##### Contour
An ingress controller for Kubernetes that uses the Envoy Proxy to manage incoming HTTP and HTTPS requests, acting as a reverse proxy and load balancer.

##### Vespa
A platform for serving scalable data and content, commonly used in search and recommendation systems.

##### Django
A high-level Python web framework used to build the WHG application, providing a structure for building web applications quickly.

##### PostgreSQL
An open-source relational database system, storing the historical geographic data and other application-related information.

##### Redis
An in-memory key-value store used for caching and as a message broker, supporting the speed and scalability of the application.

##### Celery
A distributed task queue that allows the WHG application to handle asynchronous tasks efficiently, improving performance by offloading long-running tasks.

##### Celery Beat
A scheduler that manages periodic tasks, automating the execution of routine operations like database cleanups or batch jobs.

##### Tileserver-GL
A server used for serving vector map tiles, providing geographical visualizations for the WHG.

##### Tippecanoe
A tool that generates vector tiles from large collections of GeoJSON data, enabling efficient rendering of map layers.

## Setup

To deploy the application with these configurations, follow these steps:

1. Clone this repository and navigate to the project directory.
2. Acquire the necessary `secret.yaml` credentials file from the WHG team and place it in the root directory.
3. Run `deploy.sh`:

```bash
SCRIPT_DIR="./server-configuration"
chmod +x $SCRIPT_DIR/*.sh
sudo $SCRIPT_DIR/deploy.sh
```
