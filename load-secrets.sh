#!/bin/bash

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

# EXAMPLE of extracting values from a JSON value stored in a HashiCorp Secret to create a Kubernetes Secret
kubectl create -f - <<EOF
apiVersion: secrets.hashicorp.com/v1beta1
kind: HCPVaultSecretsApp
metadata:
  name: slack-secret
  namespace: default
spec:
  appName: "WHG-PLACE"
  destination:
    create: true
    labels:
      hvs: "true"
    name: slack-secret
    transformation:
      excludes:
        - .*
      excludeRaw: true
      templates:
        bot_oauth:
          text: >
            {{ get ((get .Secrets "Slack") | fromJson) "bot_oauth" }}
        contact_webhook:
          text: >
            {{ get ((get .Secrets "Slack") | fromJson) "contact_webhook" }}
        error_webhook:
          text: >
            {{ get ((get .Secrets "Slack") | fromJson) "error_webhook" }}
        notification_webhook:
          text: >
            {{ get ((get .Secrets "Slack") | fromJson) "notification_webhook" }}
EOF