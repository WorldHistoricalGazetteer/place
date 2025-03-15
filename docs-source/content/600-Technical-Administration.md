## Generating and Using an SSH Key (Without PubkeyAuthentication)

Here's how to generate an SSH key, copy it to a remote server, and log in without relying on `PubkeyAuthentication` during the initial setup.

**1. Generate an SSH Key:**

   * Open your terminal.
   * Run the following command, replacing `"your_email@example.com"` with your email address and `/path/to/your/key` with the desired path and filename for your key (e.g., `~/.ssh/pitt`):

     ```bash
     ssh-keygen -t ed25519 -C "your_email@example.com" -f /path/to/your/key
     ```

   * You'll be prompted to enter a passphrase. You can leave it blank for no passphrase (not recommended for production).
   * This will create two files: `/path/to/your/key` (private key) and `/path/to/your/key.pub` (public key).

**2. Copy the Public Key to the Remote Server:**

   * Use the `ssh-copy-id` command with the `-o PubkeyAuthentication=no` option to force password-based authentication during the key copy process. Replace `username` and `remote_host` with the appropriate values, and `/path/to/your/key.pub` with the path to your public key:

     ```bash
     ssh-copy-id -i /path/to/your/key.pub -o PubkeyAuthentication=no username@gazetteer.crcd.pitt.edu
     ```

   * You'll be prompted for the remote server's password.
   * This command adds your public key to the `~/.ssh/authorized_keys` file on the remote server.

**3. Log in to the Remote Server:**

* Once the key is copied, you can log in using the following command, replacing `username` and `remote_host` with your values. The inclusion of `-o PubkeyAuthentication=no` is not needed for subsequent logins, only for the ssh-copy-id command.

    ```bash
    ssh username@gazetteer.crcd.pitt.edu
    ```

* If you set a passphrase, you'll be prompted to enter it. Otherwise, you'll be logged in directly.
* If you encounter a prompt regarding RedHat insights, that is normal, and is related to the operating system of the remote server.


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
         exec sudo su - gazetteer
     fi
     ```

   * **Exit insert mode:** Press `Esc`.
   * **Save and exit:** Type `:wq` and press Enter.

   * The next time you log in, you will be automatically switched to the `gazetteer` account.

**5. Check Kubernetes Nodes:**

   * After logging in and being switched to the `gazetteer` account, run the following command to check the status of your Kubernetes nodes:

     ```bash
     kubectl get nodes
     ```

   * This will display a list of nodes and their status. A `Ready` status indicates that the node is functioning correctly.