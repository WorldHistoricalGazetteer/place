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
    ssh -i /path/to/your/key username@gazetteer.crcd.pitt.edu
    ```

* The `-i /path/to/your/key` can be omitted if you have only a few keys in your `~/.ssh` directory.
* If you set a passphrase, you'll be prompted to enter it. Otherwise, you'll be logged in directly.
* If you encounter a prompt regarding RedHat insights, that is normal, and is related to the operating system of the
  remote server.
* You can simplify login by adding the following to your `~/.ssh/config` file, following which you can log in with just
  `ssh pitt`:

  ```plaintext
  Host pitt
      User username
      IdentityFile /path/to/your/key
      IdentitiesOnly yes
  ```

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

* If no nodes are listed, you may need to start Minikube first. You can do this by running:

  ```bash
  minikube start --nodes=4 --driver=podman --container-runtime=containerd --cpus=2 --memory=6144 --disk-size=8g --mount-string='/ix1/whcdh:/minikube-whcdh' --mount
  ````

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

* **Forward the proxy port to your local machine:** After starting the proxy, **exit the VM and establish an SSH tunnel
  from your local machine** to forward the proxy port:
     ```bash
     ssh -L 8010:127.0.0.1:8001 <username>@gazetteer.crcd.pitt.edu
     ```

* Access the Kubernetes dashboard by visiting
  `http://localhost:8010/api/v1/namespaces/kubernetes-dashboard/services/http:kubernetes-dashboard:/proxy/#/workloads?namespace=_all`
  in your browser.

## Secrets Management

* Passwords and certificates for the Gazetteer services are stored in the private WHG `secrets` GitHub repository. These
  are retrieved automatically during the deployment process, but a GitHub **Personal Access Token** must first be set as
  an environment variable.
  See [here](https://github.com/WorldHistoricalGazetteer/secrets?tab=readme-ov-file#setting-up-remote-programmatic-access)
  for instructions (you must be a member of the _World Historical Gazetteer_ GitHub repository organization to do
  this).
* Log in to the `gazetteer` service account on the VM, and add your **Personal Access Token** to the `~/.bashrc` file:

  ```bash
  export GITHUB_TOKEN=<github-pat>
  ```

* After adding the token, run the following command to apply the changes:

  ```bash
    source ~/.bashrc
    ```

* A script will be run during the deployment process to bundle the variable into a Kubernetes secret, which will be
  used by the management pod to access the private repository.

## Deploy Management Pod

```bash
bash <(curl -s "https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/main/deployment/deploy.sh")
```

* To force redeployment of the management pod, delete the existing pod:

```bash
MANAGEMENT_POD=$(kubectl get pods -n management -l app=gazetteer-management -o jsonpath='{.items[0].metadata.name}')
kubectl delete pod $MANAGEMENT_POD -n management
```

## Prepare Storage using `create-sync-storage.sh`

> ### **Note:** This is to be deprecated in favour of a per-Deployment method in management pod API.

The script prepares persistent storage on the Pitt VM under the `/ix1/whcdh/` root directory, ensuring correct
directory structure, ownership, and permissions expected by the Kubernetes pods. Anticipating future provision of
additional nodes, it selectively includes only those directories relevant to the current environment (`K8S_ID=PITT`).

If remote syncing is enabled via environment variables (`CLONE_DB`, `CLONE_TILES`), the script uses SSH keys stored in
the `whg-secret` to fetch selected files and directories — including the latest PostgreSQL backup, static/media files,
and map tiles — from the legacy DigitalOcean hosts.

The host-mounted base directory used for persistent storage at `/ix1/whcdh` is expected to be:

- **Physically attached** or otherwise reliably accessible on the VM.
- **Writable by Minikube and Kubernetes** via a hostPath volume mount.
- **Backed up externally**.

Each subdirectory under `/ix1/whcdh` corresponds to a Kubernetes volume mount for a specific service, such as:

- postgres/ for database files
- django-media/ for user-uploaded content
- tiles/ and tileserver/ for map tiles
- vespa-config/ and vespa-ingestion/ for Vespa deployment files

Run this script after logging in to the `gazetteer` service account on the Pitt VM:

```bash
# Wait for the Pod to be ready
MANAGEMENT_POD=$(kubectl get pods -n management -l app=gazetteer-management -o jsonpath='{.items[0].metadata.name}')
kubectl wait --for=condition=containersready pod/"$MANAGEMENT_POD" -n management --timeout=60s

# Connect to the management pod and make create-sync-storage.sh executable, then run it
kubectl exec -it "$MANAGEMENT_POD" -n management -c helm -- /bin/sh -c "
  cd /apps/repository/deployment &&
  ls -l &&
  chmod +x create-sync-storage.sh &&
  ./create-sync-storage.sh --clone-db true --clone-tiles true"
```

## Deploy Services

* Access the management API service by visiting
  `http://localhost:8010/api/v1/namespaces/management/services/http:management-chart-service:8000/proxy/`
  in your browser.

* To use the helm installation API, visit
  `http://localhost:8010/api/v1/namespaces/management/services/http:management-chart-service:8000/proxy/install/<chart-name>`
  in your browser.