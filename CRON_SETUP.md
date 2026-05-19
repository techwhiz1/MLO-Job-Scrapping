# Cron Job Setup Instructions

This document explains how to set up the daily cron job for job scraping.

## Overview

The cron job script (`cron_job_scraper.py`) performs the following tasks:
1. Connects to the PostgreSQL database
2. Fetches all records from the `CareerFeedConfig` table
3. For each config:
   - Extracts `micrositeId` and feed URLs
   - Scrapes jobs from feed URLs
   - Filters jobs by location (Canada/US) if location field is enabled in the feed config
   - Only scrapes maximum 5 new jobs (not already scraped, checked via `source_url`)
   - Saves scraped jobs to the `JobPost` table

## Prerequisites

1. Ensure all dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```

2. Ensure the database connection is configured:
   - Create a `.env` file in the project root (copy from `.env.example`)
   - Set the `DATABASE_URL` and `OPENAI_API_KEY` variables in the `.env` file

3. The `source_url` column will be automatically added to the `JobPost` table if it doesn't exist.

## Setting Up the Cron Job

### Option 1: Using the shell script (Recommended)

1. Make sure the shell script is executable:
   ```bash
   chmod +x backend/run_cron_job.sh
   ```

2. Add to crontab to run daily at a specific time (e.g., 2:00 AM):
   ```bash
   crontab -e
   ```

3. Add the following line (adjust the path and time as needed):
   ```bash
   0 2 * * * /home/ubuntu/job_scraping/backend/run_cron_job.sh
   ```

### Option 2: Direct Python execution

1. Add to crontab:
   ```bash
   crontab -e
   ```

2. Add the following line (adjust paths and time as needed):
   ```bash
   0 2 * * * cd /home/ubuntu/job_scraping && /home/ubuntu/job_scraping/venv/bin/python3 backend/cron_job_scraper.py >> logs/cron_job.log 2>&1
   ```

## Cron Schedule Examples

- Run daily at 2:00 AM: `0 2 * * *`
- Run daily at midnight: `0 0 * * *`
- Run daily at 3:30 AM: `30 3 * * *`
- Run every 12 hours: `0 */12 * * *`
- Run every 6 hours: `0 */6 * * *`

## Logging

The cron job creates a log file `cron_job_scraper.log` in the current directory. Make sure the script has write permissions to create this file.

Logs are also written to stdout, which can be captured by crontab if you redirect output in your cron entry.

## Testing the Cron Job

Before setting up the cron job, test it manually:

```bash
cd /home/ubuntu/job_scraping
python3 backend/cron_job_scraper.py
```

Or using the shell script:

```bash
/home/ubuntu/job_scraping/backend/run_cron_job.sh
```

## Troubleshooting

1. **Permission denied**: Make sure the script has execute permissions and the user has access to the project directory.

2. **Module not found**: Ensure you're using the correct Python interpreter (the one from your virtual environment if you're using one).

3. **Database connection error**: Check that the `DATABASE_URL` is correct and the database is accessible.

4. **No jobs scraped**: Check the logs to see if:
   - Feed URLs are accessible
   - Location filtering is working correctly
   - Jobs are being filtered out as already scraped

## Notes

- The script automatically adds the `source_url` column to the `JobPost` table if it doesn't exist.
- Only jobs with locations matching Canada or US will be scraped when the location field is enabled in the feed config.
- Maximum 10 new jobs per feed will be scraped per run.
- The script checks existing `source_url` values in the database to avoid duplicate scraping.

