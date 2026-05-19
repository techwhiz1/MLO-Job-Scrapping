import React, { useState } from 'react';

const JobScraperForm = ({ onScrape, loading }) => {
  const [url, setUrl] = useState('');
  const [urlError, setUrlError] = useState('');
  
  // Debug: Log state changes
  console.log('JobScraperForm rendered with url:', url, 'loading:', loading);

  const validateUrl = (url) => {
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    if (!url.trim()) {
      setUrlError('Please enter a job site URL');
      return;
    }

    if (!validateUrl(url)) {
      setUrlError('Please enter a valid URL (e.g., https://example.com/jobs)');
      return;
    }

    setUrlError('');
    onScrape(url);
  };

  const handleUrlChange = (e) => {
    console.log('Input changed to:', e.target.value);
    setUrl(e.target.value);
    if (urlError) {
      setUrlError('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div>
        <label htmlFor="job-url" className="block text-sm font-medium text-gray-700">
          Job Site URL
        </label>
        <div className="mt-1">
          <input
            type="text"
            id="job-url"
            name="job-url"
            value={url}
            onChange={handleUrlChange}
            placeholder="https://example.com/jobs"
            className="border border-gray-300 rounded px-3 py-2 w-full"
            disabled={loading}
            style={{ fontSize: '16px', color: '#000' }}
          />
          <div style={{ marginTop: '5px', fontSize: '12px', color: '#666' }}>
            Debug - Current value: "{url}" (length: {url.length})
          </div>
        </div>
        {urlError && (
          <p className="mt-2 text-sm text-red-600">{urlError}</p>
        )}
        <p className="mt-2 text-sm text-gray-500">
          Enter the URL of a job site page that contains job listings. The tool will automatically handle pagination to scrape all available jobs.
        </p>
      </div>

      <div className="flex items-center justify-between">
        <button
          type="submit"
          disabled={loading || !url.trim()}
          className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
            loading || !url.trim()
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500'
          }`}
        >
          {loading ? (
            <>
              <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              Scraping Jobs...
            </>
          ) : (
            <>
              <svg className="-ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
              Start Scraping
            </>
          )}
        </button>

        {loading && (
          <div className="text-sm text-gray-600">
            This may take several minutes depending on the number of jobs...
          </div>
        )}
      </div>
    </form>
  );
};

export default JobScraperForm;
