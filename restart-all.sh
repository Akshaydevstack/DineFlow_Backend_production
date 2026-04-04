#!/bin/bash
# to run chmod +x restart-all.sh   
# ./restart-all.sh  

NAMESPACE="dineflow-production"

echo "=========================================="
echo "🚀 DINEFLOW SAFTEY RESTART MENU"
echo "=========================================="
echo "1) 🌐 APIs & Gateway (Services only)"
echo "2) 🎧 Kafka Consumers only"
echo "3) ⚙️ Celery Workers & Beats only"
echo "4) 🚀 ALL Apps (Safely EXCLUDES Redpanda)"
echo "5) ❌ Cancel"
echo "=========================================="
read -p "Select an option (1-5): " CHOICE

if [ "$CHOICE" == "5" ]; then
    echo "🛑 Canceled."
    exit 0
fi

echo "🔍 Fetching deployments in $NAMESPACE..."
# Grab all deployments
ALL_DEPS=$(kubectl get deployments -n $NAMESPACE -o custom-columns=":metadata.name" --no-headers)

# Filter targets based on your selection using grep
case $CHOICE in
    1)
        TARGETS=$(echo "$ALL_DEPS" | grep "\-service")
        ;;
    2)
        TARGETS=$(echo "$ALL_DEPS" | grep "\-consumer")
        ;;
    3)
        TARGETS=$(echo "$ALL_DEPS" | grep "celery")
        ;;
    4)
        # 🚀 The magic line: Grabs everything EXCEPT Redpanda
        TARGETS=$(echo "$ALL_DEPS" | grep -v "redpanda")
        ;;
    *)
        echo "❌ Invalid choice! Exiting."
        exit 1
        ;;
esac

echo "🔄 Initiating rolling restarts..."
echo "------------------------------------------"

for DEPLOYMENT in $TARGETS; do
  echo "   Restarting: $DEPLOYMENT"
  kubectl rollout restart deployment/$DEPLOYMENT -n $NAMESPACE
done

echo "------------------------------------------"
echo "✅ All selected deployments are restarting!"
echo "⏳ Watch them live: kubectl get pods -n $NAMESPACE -w"