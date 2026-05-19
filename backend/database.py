"""
Database utility module for PostgreSQL operations
"""
import asyncpg
import os
from typing import List, Dict, Optional, Any
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set")


class Database:
    """Database connection and operations handler"""
    
    def __init__(self, database_url: str = DATABASE_URL):
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Create a connection pool"""
        try:
            self.pool = await asyncpg.create_pool(
                self.database_url,
                min_size=1,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create database connection pool: {str(e)}")
            raise
    
    async def close(self):
        """Close the connection pool"""
        if self.pool:
            await self.pool.close()
            logger.info("Database connection pool closed")
    
    async def fetch_career_feed_configs(self) -> List[Dict[str, Any]]:
        """Fetch all records from CareerFeedConfig table"""
        import json
        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch("SELECT * FROM \"CareerFeedConfig\"")
                configs = []
                for row in rows:
                    # Convert asyncpg Record to dictionary
                    # Records support dict() conversion, but we can also use row.keys()
                    try:
                        config_dict = {key: row[key] for key in row.keys()}
                    except (AttributeError, TypeError):
                        # Fallback to dict() conversion
                        config_dict = dict(row)
                    
                    # Parse JSON/JSONB columns if they are strings
                    if 'config' in config_dict:
                        config_value = config_dict['config']
                        if isinstance(config_value, str):
                            try:
                                config_dict['config'] = json.loads(config_value)
                            except (json.JSONDecodeError, TypeError) as e:
                                logger.warning(f"Failed to parse config JSON for record {config_dict.get('id', 'unknown')}: {str(e)}")
                        # If it's already a dict/list, keep it as is (asyncpg auto-parses JSONB)
                    
                    configs.append(config_dict)
                logger.info(f"Fetched {len(configs)} CareerFeedConfig records")
                return configs
        except Exception as e:
            logger.error(f"Error fetching CareerFeedConfig records: {str(e)}", exc_info=True)
            raise
    
    async def get_user_id_from_microsite(self, microsite_id: str) -> Optional[str]:
        """Get userId from Microsite table by micrositeId (id field)"""
        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    'SELECT "userId" FROM "Microsite" WHERE id = $1',
                    microsite_id
                )
                if row:
                    user_id = row.get('userId')
                    logger.info(f"Found userId '{user_id}' for micrositeId '{microsite_id}'")
                    return user_id
                else:
                    logger.warning(f"No Microsite found with id '{microsite_id}'")
                    return None
        except Exception as e:
            logger.error(f"Error fetching userId from Microsite table: {str(e)}")
            return None
    
    async def get_scraped_source_urls(self, limit: Optional[int] = None) -> set:
        """Get all source_urls from JobPost table that have been scraped"""
        try:
            async with self.pool.acquire() as conn:
                query = "SELECT DISTINCT source_url FROM \"JobPost\" WHERE source_url IS NOT NULL"
                if limit:
                    query += f" LIMIT {limit}"
                rows = await conn.fetch(query)
                source_urls = {row['source_url'] for row in rows if row['source_url']}
                logger.info(f"Found {len(source_urls)} scraped source URLs")
                return source_urls
        except Exception as e:
            logger.error(f"Error fetching scraped source URLs: {str(e)}")
            # If source_url column doesn't exist, return empty set
            if "column \"source_url\" does not exist" in str(e).lower():
                logger.warning("source_url column does not exist in JobPost table. Returning empty set.")
                return set()
            raise
    
    async def insert_job_post(self, job_data: Dict[str, Any]) -> str:
        """
        Insert a new job post into the JobPost table
        Returns the generated job ID
        """
        import uuid
        from datetime import datetime
        
        try:
            # Generate a unique job ID
            job_id = str(uuid.uuid4())
            
            # Prepare the data for insertion
            job_id_field = job_data.get('jobId') or job_id
            employer_name = job_data.get('employer', '') or job_data.get('employerName', '')
            job_title = job_data.get('job_title', '') or job_data.get('jobTitle', '')
            description = job_data.get('job_description', '') or job_data.get('description', '')
            location = job_data.get('location', '')
            salary_range = job_data.get('salary_range', '') or job_data.get('salaryRange', '')
            application_deadline = job_data.get('application_deadline') or job_data.get('applicationDeadline')
            image = job_data.get('image_url', '') or job_data.get('image', '')
            key_responsibilities = job_data.get('key_responsibilities', '') or job_data.get('keyResponsibilities', '')
            qualifications = job_data.get('qualifications_and_skills', '') or job_data.get('qualifications', '')
            perks_benefits = job_data.get('perks_and_benefits', '') or job_data.get('perksBenefits', '')
            
            # Convert preferred_years_of_experience to integer
            preferred_experience = job_data.get('preferred_years_of_experience', '') or job_data.get('preferredExperience', '')
            if isinstance(preferred_experience, str):
                # Try to extract number from string
                import re
                numbers = re.findall(r'\d+', preferred_experience)
                preferred_experience = int(numbers[0]) if numbers else 0
            elif not isinstance(preferred_experience, int):
                preferred_experience = 0
            
            education_level = job_data.get('educational_level', '') or job_data.get('educationLevel', '')
            certification_level = job_data.get('certification_level', '') or job_data.get('certificationLevel', '')
            interview_format = job_data.get('interview_format', '') or job_data.get('interviewFormat', '')
            required_experience = job_data.get('required_experience', '') or job_data.get('requiredExperience', '')
            # Use postedById from job_data, fallback to default if not provided
            posted_by_id = job_data.get('postedById') or '35eac158-cf81-4ec0-a523-a061b72eeb5f'
            site_id = job_data.get('siteId', '') or job_data.get('micrositeId', '')
            source_url = job_data.get('source_url', '')
            html_content = job_data.get('html_content', '')
            is_scrapped = True
            active = True
            
            # Parse application_deadline if it's a string
            deadline_timestamp = None
            if application_deadline:
                try:
                    if isinstance(application_deadline, str):
                        # Try to parse the date string
                        from dateutil import parser
                        deadline_timestamp = parser.parse(application_deadline)
                    else:
                        deadline_timestamp = application_deadline
                except Exception as e:
                    logger.warning(f"Failed to parse application_deadline: {str(e)}")
                    # Set a default deadline (30 days from now)
                    from datetime import timedelta
                    deadline_timestamp = datetime.now() + timedelta(days=30)
            
            if not deadline_timestamp:
                from datetime import timedelta
                deadline_timestamp = datetime.now() + timedelta(days=30)
            
            now = datetime.now()
            
            async with self.pool.acquire() as conn:
                # Add html_content column if it doesn't exist
                try:
                    await conn.execute("""
                        ALTER TABLE "JobPost" 
                        ADD COLUMN IF NOT EXISTS htmlContent TEXT
                    """)
                except Exception as e:
                    logger.debug(f"htmlContent column check: {str(e)}")
                try:
                    await conn.execute("""
                        ALTER TABLE "JobPost" 
                        ADD COLUMN IF NOT EXISTS "requiredExperience" TEXT
                    """)
                except Exception as e:
                    logger.debug(f"requiredExperience column check: {str(e)}")
                
                # Generate a unique ID for the job post
                post_id = str(uuid.uuid4())
                
                # Insert the job post
                await conn.execute("""
                    INSERT INTO "JobPost" (
                        id, "employerName", "hideEmployer", "jobTitle", "jobId", 
                        description, location, "salaryRange", "applicationDeadline", 
                        image, "keyResponsibilities", qualifications, "perksBenefits", 
                        "preferredExperience", "educationLevel", "certificationLevel", 
                        "interviewFormat", "postedById", channels, "siteId", 
                        "isScrapped", active, "createdAt", "updatedAt", "source_url", htmlContent,
                        "requiredExperience"
                    ) VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, 
                        $14, $15, $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27
                    )
                """,
                    post_id,  # id
                    employer_name,  # employerName
                    False,  # hideEmployer
                    job_title,  # jobTitle
                    job_id_field,  # jobId
                    description,  # description
                    location,  # location
                    salary_range,  # salaryRange
                    deadline_timestamp,  # applicationDeadline
                    image,  # image
                    key_responsibilities,  # keyResponsibilities
                    qualifications,  # qualifications
                    perks_benefits,  # perksBenefits
                    preferred_experience,  # preferredExperience
                    education_level,  # educationLevel
                    certification_level,  # certificationLevel
                    interview_format,  # interviewFormat
                    posted_by_id,  # postedById
                    None,  # channels (JSONB, can be null)
                    site_id,  # siteId
                    is_scrapped,  # isScrapped
                    active,  # active
                    now,  # createdAt
                    now,  # updatedAt
                    source_url,  # source_url
                    html_content,  # html_content
                    required_experience  # requiredExperience
                )
                
                logger.info(f"Successfully inserted job post with ID: {post_id}")
                return post_id
                
        except Exception as e:
            logger.error(f"Error inserting job post: {str(e)}")
            raise

