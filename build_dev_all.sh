#!/bin/bash

# chmod +x deploy_dev_all.sh
#./build_dev_all.sh

# Define your namespace
NAMESPACE="dineflow-dev"

echo "Deploying all Dineflow services to $NAMESPACE..."

# 1. Auth Service
echo "--- Building & Deploying Auth Service ---"
docker build -t dineflow_backend-auth_service:latest ./authService && \
kubectl rollout restart deployment auth-service -n $NAMESPACE && \
kubectl rollout restart deployment auth-table-session-consumer -n $NAMESPACE && \
kubectl rollout status deployment/auth-service -n $NAMESPACE && \
kubectl rollout status deployment/auth-table-session-consumer -n $NAMESPACE && \
kubectl exec deployment/auth-service -n $NAMESPACE -- python manage.py migrate

# 2. Menu Service
echo "--- Building & Deploying Menu Service ---"
docker build -t dineflow_backend-menu_service:latest ./menuService && \
kubectl rollout restart deployment menu-service -n $NAMESPACE

# 3. Cart Service
echo "--- Building & Deploying Cart Service ---"
docker build -t dineflow/cart-service:latest ./cartService && \
kubectl rollout restart deployment cart-service -n $NAMESPACE && \
kubectl rollout restart deployment cart-menu-consumer -n $NAMESPACE

# 4. Order Service
echo "--- Building & Deploying Order Service & Celery ---"
docker build -t dineflow_backend-order_service ./orderService && \
kubectl rollout restart deployment order-service -n $NAMESPACE && \
kubectl rollout restart deployment order-menu-consumer -n $NAMESPACE && \
kubectl rollout status deployment/order-service -n $NAMESPACE && \
kubectl rollout restart deployment/order-celery-worker deployment/order-celery-beat -n $NAMESPACE && \
kubectl rollout status deployment/order-celery-worker -n $NAMESPACE && \
kubectl rollout status deployment/order-celery-beat -n $NAMESPACE

# 5. Kitchen Service
echo "--- Building & Deploying Kitchen Service ---"
docker build -t dineflow_backend-kitchen_service:latest ./kitchenService && \
kubectl rollout restart deployment kitchen-service -n $NAMESPACE && \
kubectl rollout restart deployment kitchen-order-consumer -n $NAMESPACE && \
kubectl rollout status deployment kitchen-service -n $NAMESPACE && \
kubectl rollout status deployment kitchen-order-consumer -n $NAMESPACE

# 6. Notification Service
echo "--- Building & Deploying Notification Service ---"
docker build --no-cache -t dineflow_backend-notification_service:latest ./notificationService && \
kubectl rollout restart deployment notification-service -n $NAMESPACE && \
kubectl rollout restart deployment notification-celery-worker -n $NAMESPACE && \
kubectl rollout status deployment notification-celery-worker -n $NAMESPACE

# 7. AI Service
echo "--- Building & Deploying AI Service ---"
docker build -t dineflow-ai-service:latest ./ai-service && \
kubectl rollout restart deployment/ai-service -n $NAMESPACE && \
kubectl rollout restart deployment/ai-kafka-consumer -n $NAMESPACE && \
kubectl rollout status deployment/ai-service -n $NAMESPACE && \
kubectl rollout status deployment/ai-kafka-consumer -n $NAMESPACE

echo "All services deployed successfully!"