#!/bin/bash

echo "🔄 Restarting MongoDB without authentication..."

# Stop the current MongoDB container
docker stop ju_bot_mongodb 2>/dev/null || echo "MongoDB container was not running"

# Remove the container
docker rm ju_bot_mongodb 2>/dev/null || echo "MongoDB container was not found"

# Start MongoDB again with the new configuration
cd "$(dirname "$0")/docker"
docker-compose up -d mongodb

echo "✅ MongoDB restarted successfully!"
echo "📊 You can now test the feedback system"

# Wait a moment for MongoDB to start
sleep 3

# Test MongoDB connection
if docker exec ju_bot_mongodb mongosh --eval "db.runCommand('ping')" >/dev/null 2>&1; then
    echo "✅ MongoDB is running and accessible"
else
    echo "⚠️  MongoDB might still be starting up. Please wait a moment and try again."
fi
