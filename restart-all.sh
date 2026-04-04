#!/bin/bash
# To run ->  chmod +x restart-all.sh   
# ./restart-all.sh  

NAMESPACE="dineflow-production"

echo "=========================================="
echo "🚀 DINEFLOW DEPLOY & RESTART MENU"
echo "=========================================="
echo "1) 🌐 Restart APIs & Gateway (Services only)"
echo "2) 🎧 Restart Kafka Consumers only"
echo "3) ⚙️ Restart Celery Workers & Beats only"
echo "4) 🚀 Restart ALL Apps (Safely EXCLUDES Redpanda)"
echo "5) 📄 APPLY All YAMLs (k8s/production/) & RESTART ALL"
echo "6) ❌ Cancel"
echo "=========================================="
read -p "Select an option (1-6): " CHOICE

if [ "$CHOICE" == "6" ]; then
    echo "🛑 Canceled."
    exit 0
fi

# Handle the Apply option before filtering restarts
if [ "$CHOICE" == "5" ]; then
    echo "📄 Applying all Kubernetes YAMLs recursively..."
    # The -R flag tells it to dig into all your subfolders (ai-service, auth-service, etc.)
    kubectl apply -f k8s/production/ -R -n $NAMESPACE
    echo "✅ YAML Apply complete!"
    echo "🔄 Now proceeding to restart all apps to pick up changes..."
    # Set CHOICE to 4 so it cascades into restarting everything (except redpanda)
    CHOICE="4"
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
echo "✅ All selected actions are complete!"
echo "⏳ Watch them live: kubectl get pods -n $NAMESPACE -w"