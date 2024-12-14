#!/bin/bash

# To create the Django Files Secret for storage in HashiCorp Vault, run the following commands in the folder
# where the Django Files are stored, then copy-paste the output into the `data` section of the Secret definition:
# sudo zip -j ./django-files.zip ./env_template.py ./local_settings.py
# sudo base64 -w 0 ./django-files.zip > ./django-files.zip.base64

# Install the HashiCorp Vault Secrets Operator
echo "Installing the HashiCorp Vault Secrets Operator..."
helm install vault-secrets-operator ./vault-secrets-operator \
     --namespace vault-secrets-operator-system \
     --create-namespace

# Create Secret for HashiCorp Cloud Platform (HCP) Service Principal credentials (these should already be set as environment variables)
echo "Creating Kubernetes Secret for HashiCorp Cloud Platform Service Principal credentials..."
kubectl create secret generic vso-sp \
    --namespace default \
    --from-literal=clientID=$HCP_CLIENT_ID \
    --from-literal=clientSecret=$HCP_CLIENT_SECRET

# Create HCPAuth resource for the HashiCorp Vault Secrets Operator
echo "Creating HCPAuth resource for the HashiCorp Vault Secrets Operator..."
kubectl create -f - <<EOF
---
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPAuth
metadata:
  name: default
  namespace: vault-secrets-operator-system
spec:
  organizationID: "a99eb120-dbe9-48b7-96c1-0286a81223ed"
  projectID: "be40e446-773e-4069-9913-803be758e6e8"
  servicePrincipal:
    secretRef: vso-sp
EOF

# Fetch required Secrets from HashiCorp Vault
kubectl create -f - <<EOF
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPVaultSecretsApp
metadata:
  name: whg-secret
  namespace: default
spec:
  appName: "WHG-PLACE"
  destination:
    create: true
    labels:
      hvs: "true"
    name: whg-secret
    transformation:
      excludes:
        - .*
      excludeRaw: true
      templates:
        ca_cert:
          text: >
            {{ get ((get .Secrets "Certificates") | fromJson) "ca-cert.pem" }}
        django_files:
          text: >
            {{ get .Secrets "Django_Files" }}
        id_rsa:
          text: >
            {{ get (get ((get .Secrets "Keys") | fromJson) "DO_Main") "id_rsa" }}
        id_rsa_whg:
          text: >
            {{ get (get ((get .Secrets "Keys") | fromJson) "DO_Tileserver") "id_rsa_whg" }}
        user-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "unix-password" }}
        secret-key:
          text: "Redundant? Included in Django_Variables"
        kubernetes-cluster-issuer:
          text: >
            {{ get (get ((get .Secrets "Digital_Ocean") | fromJson) "API Access") "Personal Access Token" }}
        db-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "django-postgres-password" }}
        plausible-admin-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "plausible-admin-password" }}
        plausible-user-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "plausible-user-password" }}
        plausible-replication-password:
          text: >
            {{ get ((get .Secrets "Server_Settings") | fromJson) "plausible-replication-password" }}
EOF

# Wait for creation of the Secret
until kubectl get secret whg-secret -n default; do
  echo "Waiting for whg-secret to be created..."
  sleep 2
done
echo "...whg-secret has been created."

# Ensure existence of `/whg-private` directory; create files from secrets
sudo mkdir -p "$SCRIPT_DIR/whg-private"
chmod 775 "$SCRIPT_DIR/whg-private"
kubectl get secret whg-secret -o jsonpath='{.data.ca_cert}' | base64 --decode > "$SCRIPT_DIR/whg-private/ca-cert.pem"
kubectl patch secret whg-secret -p '{"data": {"ca_cert": null}}'
kubectl get secret whg-secret -o jsonpath='{.data.django_files}' | base64 --decode > "$SCRIPT_DIR/whg-private/django-files.zip.base64"
kubectl patch secret whg-secret -p '{"data": {"django_files": null}}'
chmod 600 "$SCRIPT_DIR/whg-private/django-files.zip.base64"
base64 --decode "$SCRIPT_DIR/whg-private/django-files.zip.base64" > "$SCRIPT_DIR/whg-private/django-files.zip"
unzip -o "$SCRIPT_DIR/whg-private/django-files.zip" -d "$SCRIPT_DIR/whg-private"
sudo rm -f "$SCRIPT_DIR/whg-private/django-files.zip"
sudo rm -f "$SCRIPT_DIR/whg-private/django-files.zip.base64"
kubectl get secret whg-secret -o jsonpath='{.data.id_rsa}' | base64 --decode > "$SCRIPT_DIR/whg-private/id_rsa"
kubectl patch secret whg-secret -p '{"data": {"id_rsa": null}}'
kubectl get secret whg-secret -o jsonpath='{.data.id_rsa_whg}' | base64 --decode > "$SCRIPT_DIR/whg-private/id_rsa_whg"
kubectl patch secret whg-secret -p '{"data": {"id_rsa_whg": null}}'

chmod 644 "$SCRIPT_DIR/whg-private/ca-cert.pem"
chmod 600 "$SCRIPT_DIR/whg-private/id_rsa"
chmod 600 "$SCRIPT_DIR/whg-private/id_rsa_whg"
chmod 644 "$SCRIPT_DIR/whg-private/env_template.py"
chmod 644 "$SCRIPT_DIR/whg-private/local_settings.py"

echo "Secrets have been fetched and files stored in $SCRIPT_DIR/whg-private."
ls -l "$SCRIPT_DIR/whg-private"