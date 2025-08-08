REPO_DIR="$HOME/deployment-repo"
cd $REPO_DIR/deployment

if ! conda info --envs | grep -q "^whg"; then
    conda env create -f environment.yml
else
    echo "Environment 'whg' already exists. Updating..."
    conda env update --file environment.yml --prune
fi

conda activate whg

cd $HOME

# Install Go-based yq (mikefarah/yq) if outdated or not already present
YQ_VERSION="4.44.1"
YQ_DEST="$HOME/.local/bin"
YQ_BIN="$YQ_DEST/yq"

mkdir -p "$YQ_DEST"

need_install=true
if [[ -x "$YQ_BIN" ]]; then
  installed_version=$("$YQ_BIN" --version | awk '{print $3}' | sed 's/^v//')
  if [[ "$installed_version" == "$YQ_VERSION" ]]; then
    echo "yq version $YQ_VERSION already installed at $YQ_BIN"
    need_install=false
  else
    echo "yq version mismatch: installed $installed_version, required $YQ_VERSION"
  fi
else
  echo "yq not found at $YQ_BIN"
fi

if $need_install; then
  echo "Installing yq version $YQ_VERSION..."
  curl -L "https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/yq_linux_amd64" -o "$YQ_BIN"
  chmod +x "$YQ_BIN"
  echo "yq installed at $YQ_BIN"
fi
