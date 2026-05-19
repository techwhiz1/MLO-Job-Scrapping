#!/bin/bash

# Script to run the cron job scraper
# This script should be added to crontab to run daily

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# Activate virtual environment if it exists
if [ -d "$PROJECT_DIR/venv" ]; then
    source "$PROJECT_DIR/venv/bin/activate"
fi

# Change to project directory
cd "$PROJECT_DIR"

# Load environment variables from .env file
if [ -f "$PROJECT_DIR/.env" ]; then
    set -a
    source "$PROJECT_DIR/.env"
    set +a
fi

# Run the cron job scraper
python3 "$SCRIPT_DIR/cron_job_scraper.py" 2>&1 | tee -a "$PROJECT_DIR/logs/cron_job.log"

# Deactivate virtual environment if it was activated
if [ -n "$VIRTUAL_ENV" ]; then
    deactivate
fi

