#!/bin/bash

set -e  # Exit on error
set -o pipefail  # Catch errors in pipes

NAMESPACE_VAULT="vault-secrets-operator-system"
NAMESPACE_DEFAULT="default"

resource_exists() {
  local kind="$1"
  local name="$2"
  local namespace="$3"
  echo "Checking if $kind $name exists in namespace $namespace..."
  kubectl get "$kind" "$name" -n "$namespace" >/dev/null 2>&1
}

delete_resource() {
  local kind="$1"
  local name="$2"
  local namespace="$3"

  if resource_exists "$kind" "$name" "$namespace"; then
    echo "Deleting $kind $name in namespace $namespace..."
    if ! kubectl delete "$kind" "$name" -n "$namespace" --ignore-not-found=true; then
      echo "Error deleting $kind $name in namespace $namespace."
      return 1 # Indicate failure
    fi

    # Wait for the resource to be deleted
    if ! kubectl wait --for=delete "$kind/$name" -n "$namespace" --timeout=60s; then
      echo "Timeout waiting for $kind $name to be deleted in namespace $namespace."
      return 1 # Indicate failure
    fi
  fi
}

helm_release_exists() {
  helm list -n "$2" | grep -q "^$1\s"
}

delete_helm_release() {
  local release="$1"
  local namespace="$2"

  if helm_release_exists "$release" "$namespace"; then
    echo "Deleting Helm release $release in namespace $namespace..."
    if ! helm delete "$release" -n "$namespace"; then
      echo "Error deleting Helm release $release in namespace $namespace."
      return 1 # Indicate failure
    fi

    # Wait until Helm release is removed (with a timeout)
    local timeout=60 # seconds
    local start_time=$(date +%s)
    while helm_release_exists "$release" "$namespace"; do
      local current_time=$(date +%s)
      if (( current_time - start_time > timeout )); then
        echo "Timeout waiting for Helm release $release to be deleted in namespace $namespace."
        return 1 # Indicate failure
      fi
      echo "Waiting for Helm release $release to be deleted..."
      sleep 2
    done
  fi
}

delete_resource "HCPVaultSecretsApp" "whg-secret" "$NAMESPACE_DEFAULT"
delete_resource "HCPAuth" "default" "$NAMESPACE_VAULT"
if kubectl get hcpvaultsecretsapp whg-secret -n "$NAMESPACE_DEFAULT" &>/dev/null; then
  kubectl patch hcpvaultsecretsapp whg-secret -p '{"metadata":{"finalizers":[]}}' --type=merge
fi
delete_resource "Secret" "vso-sp" "$NAMESPACE_DEFAULT"
delete_resource "Secret" "hcp-credentials" "$NAMESPACE_VAULT"
delete_resource "Secret" "vso-cc-storage-hmac-key" "$NAMESPACE_VAULT"
for namespace in $(kubectl get secrets --all-namespaces -o jsonpath='{.items[?(@.metadata.name=="whg-secret")].metadata.namespace}'); do
  echo "Deleting whg-secret in namespace $namespace..."
  kubectl delete secret whg-secret -n "$namespace"
done
delete_helm_release "vault-secrets-operator" "$NAMESPACE_VAULT"
crds=$(kubectl get crds | grep "secrets.hashicorp.com" | awk '{print $1}')
if [ -n "$crds" ]; then
  echo "$crds" | xargs kubectl delete crd
fi

echo "Secrets have been removed."