#!/bin/bash

# Build the Alchemi Studio Console Admin UI
# This script is called during Docker build to compile the Next.js dashboard

set -e

echo "=============================================="
echo "Building Alchemi Studio Console Admin UI..."
echo "=============================================="
echo "Current directory: $(pwd)"

# Navigate to UI directory
cd ui/litellm-dashboard

# Install dependencies
echo "Installing npm dependencies..."
npm ci --prefer-offline --no-audit 2>/dev/null || npm install --legacy-peer-deps

# Build the Next.js static export
echo "Building Next.js application..."
npm run build

# Copy built files to the proxy's static directory
destination_dir="../../litellm/proxy/_experimental/out"
echo "Copying built files to $destination_dir..."

# Ensure destination directory exists
mkdir -p "$destination_dir"

# Remove existing files and copy new ones
rm -rf "$destination_dir"/*
cp -r ./out/* "$destination_dir"

# Cleanup to reduce image size
rm -rf ./out
rm -rf node_modules

echo "=============================================="
echo "Admin UI build completed successfully!"
echo "=============================================="

# Return to root directory
cd ../..
