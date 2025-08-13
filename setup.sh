#!/bin/bash

echo "Setting up Attendee Company Reconciliation..."

# Check if Python is available
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo "Error: Python not found. Please install Python 3.8+ first."
    exit 1
fi

echo "Using Python command: $PYTHON_CMD"

# Install dependencies
echo "Installing dependencies..."
$PYTHON_CMD -m pip install -r requirements.txt

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "Creating .env file from template..."
    cp .env.example .env
    echo "Please edit .env file and add your Gemini API key:"
    echo "GEMINI_API_KEY=your_actual_key_here"
else
    echo ".env file already exists"
fi

# Create output directory if it doesn't exist
mkdir -p output

echo "Setup complete!"
echo "Next steps:"
echo "1. Edit .env file and add your Gemini API key"
echo "2. Run: $PYTHON_CMD reconcile.py"