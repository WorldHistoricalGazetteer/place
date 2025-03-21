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

## Deploy Services

```bash
bash <(curl -s "https://raw.githubusercontent.com/WorldHistoricalGazetteer/place/main/deployment/deploy.sh")
```




```bash
# Create the management namespace (idempotent method)
kubectl apply -f - <<EOF
apiVersion: v1
kind: Namespace
metadata:
  name: management
EOF

# Create a Secret to pass the kubeconfig to the management pod
CA_CERT=$(base64 -w0 /home/gazetteer/.minikube/ca.crt)
CLIENT_CERT=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.crt)
CLIENT_KEY=$(base64 -w0 /home/gazetteer/.minikube/profiles/minikube/client.key)
cp /home/gazetteer/.kube/config /tmp/kubeconfig
sed -i "s|certificate-authority: .*|certificate-authority-data: $CA_CERT|" /tmp/kubeconfig
sed -i "s|client-certificate: .*|client-certificate-data: $CLIENT_CERT|" /tmp/kubeconfig
sed -i "s|client-key: .*|client-key-data: $CLIENT_KEY|" /tmp/kubeconfig
minikube_ip=$(minikube ip)
sed -i "s|server: https://127.0.0.1:[0-9]*|server: https://$minikube_ip:8443|" /tmp/kubeconfig
kubectl create secret generic kubeconfig --from-file=config=/tmp/kubeconfig -n management --dry-run=client -o yaml | kubectl apply -f -
unset CA_CERT CLIENT_CERT CLIENT_KEY
shred -u /tmp/kubeconfig

# Create a Secret with the HashiCorp credentials
kubectl create secret generic hcp-credentials \
  --from-literal=HCP_CLIENT_ID="$HCP_CLIENT_ID" \
  --from-literal=HCP_CLIENT_SECRET="$HCP_CLIENT_SECRET" \
  -n management \
  --dry-run=client -o yaml | kubectl apply -f -
  
# Create the management deployment
echo 'apiVersion: apps/v1
kind: Deployment
metadata:
  name: management-deployment
  namespace: management
  labels:
    app: gazetteer-management
spec:
  replicas: 1
  selector:
    matchLabels:
      app: gazetteer-management
  template:
    metadata:
      labels:
        app: gazetteer-management
    spec:
      initContainers:
      - name: git-clone
        image: alpine/git:latest
        command: ["git", "clone", "https://github.com/WorldHistoricalGazetteer/place", "/apps/repository"]
        volumeMounts:
          - name: empty-dir-volume
            mountPath: /apps/repository
      containers:
      - name: helm
        image: dtzar/helm-kubectl:latest
        command: ["/bin/sh", "-c", "export KUBECONFIG=/root/.kube/config && cd /apps/repository && chmod +x *.sh && ./load-secrets.sh && sleep infinity"]
        command:
          - "/bin/sh"
          - "-c"
          - |
            apk add --no-cache python3 py3-pip &&
            pip install fastapi uvicorn &&
            export KUBECONFIG=/root/.kube/config &&
            cd /apps/repository &&
            chmod +x *.sh &&
            ./load-secrets.sh &&
            python /app/api.py
        volumeMounts:
          - name: kubeconfig-volume
            mountPath: /root/.kube
          - name: empty-dir-volume
            mountPath: /apps/repository
        envFrom:
          - secretRef:
              name: hcp-credentials
      volumes:
      - name: kubeconfig-volume
        secret:
          secretName: kubeconfig
      - name: empty-dir-volume
        emptyDir:
          sizeLimit: 1Gi' | kubectl apply -f -
```

* To force redeployment of the management pod, delete the existing pod:

```bash
kubectl delete pod $MANAGEMENT_POD -n management
```

* To log in to the management pod after it has been created:

```bash
# Wait for the Pod to be ready
MANAGEMENT_POD=$(kubectl get pods -n management -l app=gazetteer-management -o jsonpath='{.items[0].metadata.name}')
kubectl wait --for=condition=containersready pod/"$MANAGEMENT_POD" -n management --timeout=60s
# Connect to the management pod
kubectl exec -it "$MANAGEMENT_POD" -n management -c helm -- /bin/sh -c "cd /apps/repository && ls -l && /bin/sh"
```
