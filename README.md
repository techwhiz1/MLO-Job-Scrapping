# Job Scraping Tool

A comprehensive job scraping tool that extracts job data from job sites using Crawl4AI and OpenAI for structured data parsing. The tool includes both a FastAPI backend and a React frontend with CSV export functionality.

## Features

- **Intelligent Job Scraping**: Uses Crawl4AI to crawl job sites with automatic pagination handling
- **AI-Powered Data Extraction**: Leverages OpenAI GPT-3.5 to extract structured job data from HTML content
- **Comprehensive Data Fields**: Extracts 15+ job fields including employer, title, description, salary, requirements, and more
- **Modern Web Interface**: React frontend with responsive design and real-time scraping progress
- **CSV Export**: Export scraped job data to CSV format for further analysis
- **Pagination Support**: Automatically handles multi-page job listings
- **Error Handling**: Robust error handling and user feedback

## Extracted Job Fields

The tool extracts the following fields from each job posting:

- Employer
- Job Title
- Job ID
- Job Description
- Location
- Salary Range
- Application Deadline
- Image URL
- Key Responsibilities
- Qualifications and Skills
- Perks and Benefits
- Preferred Years of Experience
- Educational Level
- Certification Level
- Interview Format

## Prerequisites

- Python 3.8+
- Node.js 16+
- npm or yarn
- OpenAI API key

## Installation

### Backend Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Set your OpenAI API key:
The API key is already configured in the code, but you can also set it as an environment variable:
```bash
export OPENAI_API_KEY=your_openai_api_key_here
```

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install Node.js dependencies:
```bash
npm install
```

## Running the Application

### Start the Backend

From the project root directory:
```bash
cd backend
python main.py
```

The backend will start on `http://localhost:8000`

### Start the Frontend

In a new terminal, from the project root directory:
```bash
cd frontend
npm start
```

The frontend will start on `http://localhost:3000`

## Usage

1. Open your browser and navigate to `http://localhost:3000`
2. Enter a job site URL in the input field (e.g., `https://example.com/jobs`)
3. Click "Start Scraping" to begin the job extraction process
4. Wait for the scraping to complete (this may take several minutes depending on the number of jobs)
5. View the results in the table format
6. Click "Export CSV" to download the results as a CSV file
7. Use the "Details" button to expand each row and see all extracted fields

## API Endpoints

### POST /scrape

Scrapes jobs from a given URL.

**Request Body:**
```json
{
  "url": "https://example.com/jobs",
  "max_jobs": 3,
  "include_html_content": false
}
```

**Response:**
```json
{
  "success": true,
  "message": "Successfully scraped 25 jobs",
  "jobs": [...],
  "total_jobs": 25
}
```

## Technical Architecture

### Backend (FastAPI)
- **FastAPI**: Modern Python web framework for building APIs
- **Crawl4AI**: Advanced web crawling with JavaScript support
- **OpenAI API**: AI-powered content extraction and structuring
- **BeautifulSoup**: HTML parsing and link extraction
- **Pydantic**: Data validation and serialization

### Frontend (React)
- **React 18**: Modern React with hooks and functional components
- **Tailwind CSS**: Utility-first CSS framework for styling
- **Axios**: HTTP client for API communication
- **React-CSV**: CSV export functionality
- **Responsive Design**: Mobile-friendly interface

## Configuration

### Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (already set in the code)
- `REACT_APP_API_URL`: Backend API URL (defaults to `http://localhost:8000`)
- `SELENIUM_HTTP_READ_TIMEOUT`: Chromedriver command timeout. Fast API mode defaults to `60`; deep mode defaults to `120`.
- `SKIP_MAIN_DOCUMENT_SCROLL`: Set to `true` to skip slow parent-page scrolling. API fast mode does this by default while still processing iframes/listings.
- `SCROLL_DETAIL_BEFORE_HTML`: Set to `true` only when a job detail page lazy-loads content after scrolling; defaults to `false` for faster accurate styled HTML extraction.

### Customization

You can customize the job extraction logic by modifying:
- `backend/job_scraper.py`: Adjust scraping logic and selectors
- `frontend/src/components/JobResultsTable.js`: Modify the display fields and table layout

## Troubleshooting

### Common Issues

1. **Backend not starting**: Make sure all Python dependencies are installed and the port 8000 is available
2. **Frontend not connecting to backend**: Ensure the backend is running on port 8000
3. **Scraping fails**: Check if the target website allows scraping and has the expected HTML structure
4. **OpenAI API errors**: Verify your API key is correct and you have sufficient credits

### Performance Tips

- The tool is designed to handle pagination automatically but limits to 10 pages to prevent infinite loops
- Large job sites may take several minutes to scrape completely
- The tool includes rate limiting to be respectful to target websites

## License

This project is licensed under the MIT License.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues and questions, please create an issue in the repository.
