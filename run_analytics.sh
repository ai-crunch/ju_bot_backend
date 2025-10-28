#!/bin/bash

# JU Bot Feedback Analytics Runner
# This script runs the feedback analytics with different options

echo "🎯 JU Bot Feedback Analytics Runner"
echo "=================================="
echo ""

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    exit 1
fi

# Check if MongoDB is running
if ! nc -z localhost 27017 2>/dev/null; then
    echo "⚠️  MongoDB doesn't seem to be running on localhost:27017"
    echo "   Please start MongoDB using: docker-compose up -d"
    echo ""
fi

# Get the directory of this script
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

echo "Select an option:"
echo "1. Run basic analytics report"
echo "2. Run analytics and export to JSON"
echo "3. Run analytics and export to CSV"
echo "4. Exit"
echo ""

read -p "Enter your choice (1-4): " choice

case $choice in
    1)
        echo "📊 Running basic analytics report..."
        python3 "$DIR/feedback_analytics.py"
        ;;
    2)
        echo "📊 Running analytics with JSON export..."
        python3 "$DIR/feedback_analytics.py" --export --format json
        ;;
    3)
        echo "📊 Running analytics with CSV export..."
        python3 "$DIR/feedback_analytics.py" --export --format csv
        ;;
    4)
        echo "👋 Goodbye!"
        exit 0
        ;;
    *)
        echo "❌ Invalid choice. Please run the script again."
        exit 1
        ;;
esac

echo ""
echo "✅ Analytics completed!"
