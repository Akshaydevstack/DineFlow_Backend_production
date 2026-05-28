#!/bin/bash

# Array of your service directories
SERVICES=(
    "ai-service"
    "authService"
    "cartService"
    "kitchenService"
    "menuService"
    "notificationService"
    "orderService"
    "nginx"
)

echo "Starting local Docker builds for DineFlow..."

for SERVICE in "${SERVICES[@]}"; do
    echo "----------------------------------------"
    echo "Building image for: $SERVICE"
    echo "----------------------------------------"

    # Build the image and tag it with 'latest'
    # Assuming each folder has its own Dockerfile
    docker build -t "dineflow-${SERVICE,,}:latest" "./$SERVICE"

    if [ $? -ne 0 ]; then
        echo "❌ Error building $SERVICE. Exiting."
        exit 1
    fi
done

echo "✅ All local images built successfully!"