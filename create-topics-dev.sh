#!/bin/bash
# To run ->  chmod +x create-topics-dev.sh
# ./create-topics-dev.sh 

CONTAINER_NAME="redpanda"

echo "=========================================="
echo "🎧 DINEFLOW [DEV] KAFKA TOPIC CREATOR"
echo "=========================================="
echo "🔍 Checking for Redpanda Docker container..."

# Safety check: Is the Docker container actually running?
if ! docker ps --format '{{.Names}}' | grep -Eq "^${CONTAINER_NAME}\$"; then
  echo "❌ Error: Could not find a running Docker container named '$CONTAINER_NAME'!"
  echo "Make sure your Redpanda container is running in Docker Desktop."
  exit 1
fi

echo "🎯 Found Redpanda container: $CONTAINER_NAME"
echo "🚀 Starting topic creation..."
echo "------------------------------------------"

# List of all your topics
TOPICS=(
  "ai.service.dlq"
  "cart.menu.dlq"
  "kitchen.order.dlq"
  "kitchen.ticket.accepted"
  "kitchen.ticket.cancelled"
  "kitchen.ticket.created"
  "kitchen.ticket.preparing"
  "kitchen.ticket.ready"
  "menu.item.created"
  "menu.item.deleted"
  "menu.item.updated"
  "notification.dlq"
  "orders.created"
  "order.kitchen.dlq"
  "order.menu.dlq"
  "order.table.dlq"
  "orders.cancelled"
  "orders.placed"
  "restaurant.created"
  "restaurant.table.upsert"
  "restaurant.updated"
  "table-session.dlq"
  "table.session.closed"
  "table.session.dlq"
  "table.session.started"
  "user.created"
  "user.updated"
)

for TOPIC in "${TOPICS[@]}"
do
  echo "   Creating topic: $TOPIC"
  # Using docker exec instead of kubectl exec
  docker exec -it $CONTAINER_NAME rpk topic create $TOPIC --partitions 1 --replicas 1
done

echo "------------------------------------------"
echo "✅ All topics created successfully inside Docker container '$CONTAINER_NAME'!"