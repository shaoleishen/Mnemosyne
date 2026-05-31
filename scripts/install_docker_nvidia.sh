#!/bin/bash
set -e

echo "=== Starting Docker & NVIDIA Container Toolkit installation for WSL (Ubuntu 22.04) ==="

# 1. Update and install basic dependencies
echo "Updating package lists..."
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg lsb-release

# 2. Install Docker official repository and packages
echo "Installing Docker..."
# Add GPG key
sudo mkdir -m 0755 -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor --yes -o /etc/apt/keyrings/docker.gpg
# Add Repo
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Start Docker service
echo "Starting Docker service..."
sudo systemctl start docker || sudo service docker start
sudo systemctl enable docker || true

# 4. Add GPG and Repo for NVIDIA Container Toolkit
echo "Configuring NVIDIA Container Toolkit repository..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# 5. Install NVIDIA Container Toolkit
echo "Installing NVIDIA Container Toolkit..."
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 6. Configure NVIDIA Container Toolkit in Docker config
echo "Configuring Docker runtime for NVIDIA Container Toolkit..."
sudo nvidia-ctk runtime configure --runtime=docker
echo "Restarting Docker service to apply changes..."
sudo systemctl restart docker || sudo service docker restart

# 7. Add current WSL user to Docker group
echo "Adding user '$USER' to the docker group..."
sudo usermod -aG docker $USER

echo "=========================================================="
echo " Installation completed successfully!"
echo " IMPORTANT: Please restart your WSL terminal or run:"
echo "   newgrp docker"
echo " to apply group membership changes without logging out."
echo "=========================================================="
