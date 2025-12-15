#!/bin/bash
# Script to copy Greek texts to the backend data folder for Docker builds
#
# This script should be run before building the production Docker image.
# For docker-compose development, the data is mounted as a volume instead.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$BACKEND_DIR")"
SOURCE_DIR="$PROJECT_ROOT/canonical-greekLit"
TARGET_DIR="$BACKEND_DIR/data/canonical-greekLit"

echo "=== Copying Greek Texts for Docker Build ==="
echo "Source: $SOURCE_DIR"
echo "Target: $TARGET_DIR"

# Check if source directory exists
if [ ! -d "$SOURCE_DIR" ]; then
    echo "ERROR: Source directory not found: $SOURCE_DIR"
    echo "Please ensure the canonical-greekLit repository is present."
    exit 1
fi

# Create target directory
mkdir -p "$TARGET_DIR"

# Copy the data directory (contains the XML files)
if [ -d "$SOURCE_DIR/data" ]; then
    echo "Copying data directory..."
    cp -r "$SOURCE_DIR/data" "$TARGET_DIR/"
    
    # Count XML files copied
    XML_COUNT=$(find "$TARGET_DIR/data" -name "*.xml" -type f | wc -l | tr -d ' ')
    echo "Copied $XML_COUNT XML files"
else
    echo "ERROR: Data directory not found in canonical-greekLit"
    exit 1
fi

echo ""
echo "=== Copy Complete ==="
echo "The Greek texts are now ready for Docker build."
echo ""
echo "To build the Docker image:"
echo "  cd $BACKEND_DIR"
echo "  docker build -t helios-backend ."
