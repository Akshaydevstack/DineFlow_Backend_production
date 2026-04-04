#!/bin/bash
# to run chmod +x create-topics.sh
# ./create-topics.sh 
   
NAMESPACE="dineflow-production"

echo "🔍 Searching for Redpanda pod..."
# 🚀 Auto-detect the exact name of the running Redpanda pod
REDPANDA_POD_NAME=$(kubectl get pods -n $NAMESPACE | grep redpanda | awk '{print $1}' | head -n 1)

# Safety check: Did we actually find it?
if [ -z "$REDPANDA_POD_NAME" ]; then
  echo "❌ Error: Could not find any pod containing 'redpanda' in namespace $NAMESPACE!"
  exit 1
fi

echo "🎯 Found Redpanda pod: $REDPANDA_POD_NAME"
echo "🚀 Starting topic creation..."

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
  echo "Creating topic: $TOPIC"
  kubectl exec -it $REDPANDA_POD_NAME -n $NAMESPACE -- rpk topic create $TOPIC --partitions 1 --replicas 1
done

echo "✅ All topics created successfully on $REDPANDA_POD_NAME!"