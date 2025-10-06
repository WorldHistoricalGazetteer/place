## SSH Key Setup

Here's how to generate an SSH key, copy it to a remote server, and log in without relying on `PubkeyAuthentication` during the initial setup.

### 1. Generate an SSH Key

* Open your terminal.
* Run the following command, replacing `"your_email@example.com"` with your email address and `/path/to/your/key` with the desired path and filename for your key (e.g., `~/.ssh/pitt`):

  ```bash
  ssh-keygen -t ed25519 -C "your_email@example.com" -f /path/to/your/key
  ```

* You'll be prompted to enter a passphrase. You can leave it blank for no passphrase (not recommended for production).
* This will create two files: `/path/to/your/key` (private key) and `/path/to/your/key.pub` (public key).

### 2. Copy the Public Key to the Remote Server

* Use the `ssh-copy-id` command with the `-o PubkeyAuthentication=no` option to force password-based authentication during the key copy process. Replace `username` and `remote_host` with the appropriate values, and `/path/to/your/key.pub` with the path to your public key:

  ```bash
  ssh-copy-id -i /path/to/your/key.pub -o PubkeyAuthentication=no username@gazetteer.crcd.pitt.edu
  ```

* You'll be prompted for the remote server's password.
* This command adds your public key to the `~/.ssh/authorized_keys` file on the remote server.

### 3. Log in to the Remote Server

* Once the key is copied, you can log in using the following command, replacing `username` and `remote_host` with your values. The inclusion of `-o PubkeyAuthentication=no` is not needed for subsequent logins, only for the ssh-copy-id command.

    ```bash
    ssh -i /path/to/your/key username@gazetteer.crcd.pitt.edu
    ```

* The `-i /path/to/your/key` can be omitted if you have only a few keys in your `~/.ssh` directory.
* If you set a passphrase, you'll be prompted to enter it. Otherwise, you'll be logged in directly.
* If you encounter a prompt regarding RedHat insights, that is normal, and is related to the operating system of the remote server.
* You can simplify login by adding the following to your `~/.ssh/config` file, following which you can log in with just `ssh pitt`:

  ```plaintext
  Host pitt
      User username
      IdentityFile /path/to/your/key
      IdentitiesOnly yes
  ```

### 4. Automatically Switch to the `gazetteer` Account

* After logging in, edit your `.bashrc` file using `vi`:

  ```bash
  vi ~/.bashrc
  ```

* **Navigate to the end of the file:** Press `G` (capital G).
* **Navigate up one line:** Press `k`. This ensures the new lines are inserted right before `unset rc`.
* **Enter insert mode:** Press `o` (lowercase o) to insert a new line below the current line.
* **Add the following lines:** Replace `username` with your actual username on the remote server.

  ```bash
  # Automatically switch to the gazetteer account on login
  if [[ $USER == "username" && $- == *i* ]]; then
      sudo su - gazetteer
  fi
  ```

* **Exit insert mode:** Press `Esc`.
* **Save and exit:** Type `:wq` and press Enter.

* The next time you log in, you will be automatically switched to the `gazetteer` account.

### 5. Check Kubernetes Nodes

* After logging in and being switched to the `gazetteer` account, run the following command to check the status of your Kubernetes nodes:

  ```bash
  kubectl get nodes
  ```

* This will display a list of nodes and their status. A `Ready` status indicates that the node is functioning correctly.
* If Minikube is not running, the deployment script will automatically start it with the appropriate configuration (4 nodes, podman driver, etc.).

## Secrets Management

* Passwords and certificates for the Gazetteer services are stored in the private WHG `secrets` GitHub repository. These are retrieved automatically during the deployment process, but a GitHub **Personal Access Token** must first be set as an environment variable. See [here](https://github.com/WorldHistoricalGazetteer/secrets?tab=readme-ov-file#setting-up-remote-programmatic-access) for instructions (you must be a member of the _World Historical Gazetteer_ GitHub repository organization to do this).

* Log in to the `gazetteer` service account on the VM, and add your **Personal Access Token** to the `~/.bashrc` file:

  ```bash
  export GITHUB_TOKEN=<github-pat>
  ```

* After adding the token, run the following command to apply the changes:

  ```bash
  source ~/.bashrc
  ```

* A script will be run during the deployment process to bundle the variable into a Kubernetes secret, which will be used by the management pod to access the private repository.

## Deploying the Management Pod

The deployment script handles all setup automatically, including:
- Starting/verifying Minikube
- Enabling required addons (dashboard, metrics-server)
- Creating necessary secrets
- Deploying the management Helm chart

Run the deployment script:

```bash
bash <(curl -s "https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/main/deployment/deploy.sh")
```

The script may safely be re-run to update the deployment or apply any changes.

## Accessing Kubernetes Dashboard and Services Locally

Download the tunnel setup script for forwarding the necessary ports to your local machine:

```bash
curl -s -o k8s-tunnel.sh "https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/main/deployment/k8s-tunnel.sh" && chmod +x k8s-tunnel.sh
```

Run the script to set up the kubectl proxy and SSH tunnel:

```bash
./k8s-tunnel.sh start
```

The script will:
- Request your remote SSH user name
- Print a local port forwarding command which you will need to run in a separate LOCAL terminal window
- List the services available and their local URLs, including the Kubernetes dashboard at http://localhost:8010/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/#/workloads?namespace=whg

When you have finished, you can stop the proxy and tunnel on the remote machine by running:

```bash
./k8s-tunnel.sh kill
```

To terminate the local port forwarding on your local machine, run:

```bash
pkill -f "ssh -fN -L"
```

## Deploying Services

* Access the management API service by visiting `http://localhost:8010/api/v1/namespaces/whg/services/http:management-chart-service:8000/proxy/` in your browser.

* To use the helm installation API, visit `http://localhost:8010/api/v1/namespaces/whg/services/http:management-chart-service:8000/proxy/install/<chart-name>` in your browser.