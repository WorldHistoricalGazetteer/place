## SSH Key

Here's how to generate an SSH key, copy it to a remote server, and log in without relying on `PubkeyAuthentication`
during the initial setup.

**1. Generate an SSH Key:**

* Open your terminal.
* Run the following command, replacing `"your_email@example.com"` with your email address and `/path/to/your/key` with
  the desired path and filename for your key (e.g., `~/.ssh/pitt`):

  ```bash
  ssh-keygen -t ed25519 -C "your_email@example.com" -f /path/to/your/key
  ```

* You'll be prompted to enter a passphrase. You can leave it blank for no passphrase (not recommended for production).
* This will create two files: `/path/to/your/key` (private key) and `/path/to/your/key.pub` (public key).

**2. Copy the Public Key to the Remote Server:**

* Use the `ssh-copy-id` command with the `-o PubkeyAuthentication=no` option to force password-based authentication
  during the key copy process. Replace `username` and `remote_host` with the appropriate values, and
  `/path/to/your/key.pub` with the path to your public key:

  ```bash
  ssh-copy-id -i /path/to/your/key.pub -o PubkeyAuthentication=no username@gazetteer.crcd.pitt.edu
  ```

* You'll be prompted for the remote server's password.
* This command adds your public key to the `~/.ssh/authorized_keys` file on the remote server.

**3. Log in to the Remote Server:**

* Once the key is copied, you can log in using the following command, replacing `username` and `remote_host` with your
  values. The inclusion of `-o PubkeyAuthentication=no` is not needed for subsequent logins, only for the ssh-copy-id
  command.

    ```bash
    ssh username@gazetteer.crcd.pitt.edu
    ```

* If you set a passphrase, you'll be prompted to enter it. Otherwise, you'll be logged in directly.
* If you encounter a prompt regarding RedHat insights, that is normal, and is related to the operating system of the
  remote server.

**4. Automatically Switch to the `gazetteer` Account (Using vi):**

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

**5. Check Kubernetes Nodes:**

* After logging in and being switched to the `gazetteer` account, run the following command to check the status of your
  Kubernetes nodes:

  ```bash
  kubectl get nodes
  ```

* This will display a list of nodes and their status. A `Ready` status indicates that the node is functioning correctly.

## Enabling Kubernetes Dashboard and other Addons

* **Enable the required Minikube addons:** First, log in to the VM and run the following commands to enable the
  metrics-server, Kubernetes dashboard, and other components:
     ```bash
     for addon in csi-hostpath-driver dashboard metallb metrics-server volumesnapshots; do
       minikube addons enable "$addon"
     done
     ```

* **Start the kubectl proxy in the background:** Run the following command to start the Kubernetes proxy. Use `nohup` to
  keep it running even after you log out:
     ```bash
     nohup kubectl proxy --address=0.0.0.0 --port=8001 --disable-filter=true > kubectl_proxy.log 2>&1 &
     ```

* **Forward the proxy port to your local machine:** After starting the proxy, exit the VM and establish an SSH tunnel
  from your local machine to forward the proxy port:
     ```bash
     ssh -L 8001:127.0.0.1:8001 <username>@gazetteer.crcd.pitt.edu
     ```

* Access the Kubernetes dashboard by visiting
  `http://localhost:8001/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/#/workloads?namespace=_all`
  in your browser.

## HashiCorp Secrets Management

* Passwords and certificates for the Gazetteer services are stored in HashiCorp Vault. These are retrieved automatically
  during the deployment process, but the access keys for the HCP Client (discoverable by logging in to
  portal.cloud.hashicorp.com) must first be set as environment variables. Log in to the `gazetteer` service account on
  the VM, and add the variables to the `~/.bashrc` file:

  ```bash
  export HCP_CLIENT_ID=*** HCP_CLIENT_SECRET=***
  ```

## Storage Allocation & Repository Cloning

* Storage is primarily managed through the `csi-hostpath-driver`, which creates persistent volumes and claims for the
  required storage. However, the World Historical Gazetteer PLACE repository must first be cloned manually as it
  contains the Helm charts needed for further configuration and deployment.

```bash
## Create the repository directory within the mounted `/ix3` storage
#mkdir -p /ix3/gazetteer/repo
#chown -R gazetteer:gazetteer /ix3/gazetteer
#chmod 755 /ix3/gazetteer
#
## Clone the World Historical Gazetteer PLACE repository into the `/ix3/gazetteer/repo` directory
#git clone https://github.com/WorldHistoricalGazetteer/place /ix3/gazetteer/repo
```

```bash
# Create the repository directory within the mounted `~/` storage
mkdir -p ~/repo
chmod 755 ~/repo

# Clone the World Historical Gazetteer PLACE repository into the `~/repo` directory
git clone https://github.com/WorldHistoricalGazetteer/place ~/repo
```

## Deploy Services

* Helm is not installed on the VM, so the first step is to set up a management pod to deploy the services. This pod will
  have Helm installed and will be used to deploy the Gazetteer services.

```bash
# Create the management namespace
kubectl create namespace management
# Create a Secret to pass the kubeconfig to the management pod
kubectl create secret generic kubeconfig --from-file=config=/home/gazetteer/.kube/config -n management
# Create a Secret to pass the HashiCorp credentials to the management pod
kubectl create secret generic hcp-credentials --from-literal=HCP_CLIENT_ID="$HCP_CLIENT_ID" --from-literal=HCP_CLIENT_SECRET="$HCP_CLIENT_SECRET" -n management
# Create the management pod
kubectl apply -f ~/repo/deployment/management-pod.yaml
```