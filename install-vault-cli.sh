#!/bin/bash

# Ensure the script exits on error
set -e

# Check if the script is run inside a virtual environment
if [ -z "$VIRTUAL_ENV" ]; then
  echo "Error: This script must be run inside a Python virtual environment."
  exit 1
fi

# Define the Vault version to install
VAULT_VERSION="1.18.2" # Replace with the latest version if needed
VAULT_URL="https://releases.hashicorp.com/vault/${VAULT_VERSION}/vault_${VAULT_VERSION}_linux_amd64.zip"
INSTALL_DIR="$VIRTUAL_ENV/bin"

# Download the Vault binary
echo "Downloading Vault CLI version $VAULT_VERSION..."
curl -o vault.zip "$VAULT_URL"

# Unzip the Vault binary into the virtual environment's bin directory
echo "Installing Vault CLI in $INSTALL_DIR..."
unzip vault.zip -d "$INSTALL_DIR"

# Make the Vault binary executable
chmod +x "$INSTALL_DIR/vault"

# Clean up the downloaded zip file
rm vault.zip

# Verify the installation
echo "Vault CLI installed successfully in $INSTALL_DIR."
"$INSTALL_DIR/vault" version

# Define the HCP CLI version to install
HCP_CLI_VERSION="0.8.0" # Replace with the latest version if needed
HCP_CLI_URL="https://releases.hashicorp.com/hcp/${HCP_CLI_VERSION}/hcp_${HCP_CLI_VERSION}_linux_amd64.zip"
INSTALL_DIR="$VIRTUAL_ENV/bin"

# Download the HCP CLI binary
echo "Downloading HCP CLI version $HCP_CLI_VERSION..."
curl -o hcp.zip "$HCP_CLI_URL"

# Unzip the HCP CLI binary into the virtual environment's bin directory
echo "Installing HCP CLI in $INSTALL_DIR..."
unzip hcp.zip -d "$INSTALL_DIR"

# Make the HCP binary executable
chmod +x "$INSTALL_DIR/hcp"

# Clean up the downloaded zip file
rm hcp.zip

# Verify the installation
echo "HCP CLI installed successfully in $INSTALL_DIR."
"$INSTALL_DIR/hcp" version