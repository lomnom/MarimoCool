#!/bin/bash

echo "Please run this INSIDE THE SYSTEMD DIRECTORY!"
echo "Press enter if you it is true."
read

echo "Sudo may be needed."

echo "Stopping service if previously running"
sudo systemctl stop marimo.service 

echo "Ensuring run.bash is executable"
chmod +x run.bash

echo "Writing service file..."
MARIMO_USER=$(whoami)
export PWD
export MARIMO_USER
envsubst < template.service | sudo tee /etc/systemd/system/marimo.service > /dev/null

echo "Updating and enabling service..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload
sudo systemctl enable marimo.service

echo "Starting service..."
sudo systemctl start marimo.service # Start it too