"""
Cron job script for daily job scraping
This script:
1. Fetches all CareerFeedConfig records from the database
2. For each config, scrapes jobs from the feed URLs
3. Filters jobs by location (Canada/US) if location field is enabled
4. Only scrapes max 10 new jobs (not already scraped)
5. Saves scraped jobs to JobPost table
"""
import asyncio
import os
import sys
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Add the backend directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import Database
from job_scraper import JobScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('cron_job_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Database URL
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")


async def add_source_url_column_if_needed(db: Database):
    """Add source_url column to JobPost table if it doesn't exist"""
    try:
        async with db.pool.acquire() as conn:
            # Check if column exists
            result = await conn.fetchval("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='JobPost' AND column_name='source_url'
            """)
            
            if not result:
                logger.info("Adding source_url column to JobPost table...")
                await conn.execute("""
                    ALTER TABLE "JobPost" 
                    ADD COLUMN IF NOT EXISTS source_url TEXT
                """)
                logger.info("source_url column added successfully")
            else:
                logger.info("source_url column already exists")
    except Exception as e:
        logger.error(f"Error adding source_url column: {str(e)}")
        raise


async def process_career_feed_config(db: Database, config: Dict[str, Any]) -> int:
    """
    Process a single CareerFeedConfig record
    Returns the number of jobs successfully scraped and saved
    """
    import json
    
    # Ensure config is a dictionary
    if not isinstance(config, dict):
        logger.error(f"Config is not a dictionary: {type(config)} - {config}")
        return 0
    
    microsite_id = config.get('micrositeId')
    config_data = config.get('config', {})
    
    # Parse config_data if it's a string
    if isinstance(config_data, str):
        try:
            config_data = json.loads(config_data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse config_data JSON: {str(e)}")
            return 0
    
    # Ensure config_data is a dictionary
    if not isinstance(config_data, dict):
        logger.error(f"config_data is not a dictionary: {type(config_data)} - {config_data}")
        logger.error(f"Full config object: {config}")
        return 0
    
    feeds = config_data.get('feeds', [])
    
    if not feeds:
        logger.warning(f"No feeds found in config_data for micrositeId: {microsite_id}")
        logger.debug(f"config_data keys: {config_data.keys() if isinstance(config_data, dict) else 'N/A'}")
    
    if not microsite_id:
        logger.warning(f"Skipping config with ID {config.get('id')} - no micrositeId found")
        return 0
    
    logger.info(f"Processing config for micrositeId: {microsite_id}")
    
    # Get userId from Microsite table
    user_id = await db.get_user_id_from_microsite(microsite_id)
    if not user_id:
        logger.warning(f"No userId found for micrositeId '{microsite_id}'. Using default postedById.")
        user_id = '35eac158-cf81-4ec0-a523-a061b72eeb5f'  # Fallback to default
    
    total_scraped = 0
    
    # Get already scraped source URLs
    scraped_urls = await db.get_scraped_source_urls()
    logger.info(f"Found {len(scraped_urls)} already scraped URLs")
    
    for feed in feeds:
        feed_url = feed.get('url')
        if not feed_url:
            logger.warning(f"Skipping feed - no URL found")
            continue
        
        logger.info(f"Processing feed URL: {feed_url}")
        
        # Check if location field is enabled
        fields = feed.get('fields', {})
        location_enabled = fields.get('location', False)
        
        # Initialize scraper with location filtering if needed
        scraper = JobScraper(filter_location=location_enabled)
        
        try:
            # Scrape jobs from the feed URL
            jobs = await scraper.scrape_jobs(feed_url)
            logger.info(f"Scraped {len(jobs)} jobs from {feed_url}")
            
            # Filter out already scraped jobs
            new_jobs = []
            for job in jobs:
                source_url = job.get('source_url', '')
                if source_url and source_url not in scraped_urls:
                    new_jobs.append(job)
                else:
                    logger.debug(f"Skipping already scraped job: {source_url}")
            
            logger.info(f"Found {len(new_jobs)} new jobs (not already scraped)")
            
            # Limit to max 10 new jobs
            new_jobs = new_jobs[:10]
            logger.info(f"Processing {len(new_jobs)} new jobs (limited to max 10)")
            
            # Save jobs to database
            saved_count = 0
            for job in new_jobs:
                try:
                    # Add micrositeId and postedById to job data
                    job['micrositeId'] = microsite_id
                    job['siteId'] = microsite_id
                    job['postedById'] = user_id  # Use userId from Microsite table
                    
                    # Save to database
                    await db.insert_job_post(job)
                    saved_count += 1
                    
                    # Add to scraped URLs set to avoid duplicates in this run
                    source_url = job.get('source_url', '')
                    if source_url:
                        scraped_urls.add(source_url)
                    
                    logger.info(f"✅ Saved job: {job.get('job_title', 'Unknown')} - {source_url}")
                except Exception as e:
                    logger.error(f"❌ Error saving job {job.get('source_url', 'Unknown')}: {str(e)}")
                    continue
            
            total_scraped += saved_count
            logger.info(f"Saved {saved_count} jobs from feed {feed_url}")
            
        except Exception as e:
            logger.error(f"Error processing feed {feed_url}: {str(e)}")
            continue
    
    logger.info(f"Completed processing micrositeId {microsite_id}: {total_scraped} jobs saved")
    return total_scraped


async def main():
    """Main function to run the cron job"""
    logger.info("=" * 80)
    logger.info("Starting cron job scraper")
    logger.info(f"Timestamp: {datetime.now().isoformat()}")
    logger.info("=" * 80)
    
    db = Database(DATABASE_URL)
    
    try:
        # Connect to database
        await db.connect()
        logger.info("Connected to database successfully")
        
        # Add source_url column if it doesn't exist
        await add_source_url_column_if_needed(db)
        
        # Fetch all CareerFeedConfig records
        logger.info("Fetching CareerFeedConfig records...")
        configs = await db.fetch_career_feed_configs()
        logger.info(f"Found {len(configs)} CareerFeedConfig records")
        
        if not configs:
            logger.warning("No CareerFeedConfig records found. Exiting.")
            return
        
        # Process each config
        total_jobs_saved = 0
        for i, config in enumerate(configs, 1):
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Processing config {i}/{len(configs)}")
            logger.info(f"{'=' * 80}")
            try:
                # Debug: log config type and keys
                logger.debug(f"Config type: {type(config)}")
                if isinstance(config, dict):
                    logger.debug(f"Config keys: {list(config.keys())}")
                else:
                    logger.error(f"Config is not a dict! Type: {type(config)}, Value: {config}")
                    continue
                
                jobs_saved = await process_career_feed_config(db, config)
                total_jobs_saved += jobs_saved
            except Exception as e:
                logger.error(f"Error processing config {i}: {str(e)}", exc_info=True)
                continue
        
        logger.info("\n" + "=" * 80)
        logger.info(f"Cron job completed successfully!")
        logger.info(f"Total jobs saved: {total_jobs_saved}")
        logger.info(f"Timestamp: {datetime.now().isoformat()}")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Fatal error in cron job: {str(e)}", exc_info=True)
        sys.exit(1)
    finally:
        # Close database connection
        await db.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    # Run the async main function
    asyncio.run(main())
