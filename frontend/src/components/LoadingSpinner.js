import React from 'react';

const LoadingSpinner = () => {
  return (
    <div className="bg-white shadow rounded-lg mb-8">
      <div className="px-4 py-8 sm:p-8">
        <div className="flex flex-col items-center justify-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mb-4"></div>
          <h3 className="text-lg font-medium text-gray-900 mb-2">Scraping Jobs...</h3>
          <p className="text-sm text-gray-500 text-center max-w-md">
            We're analyzing the job site and extracting a small batch of job postings.
          </p>
          <div className="mt-4 w-full max-w-md">
            <div className="bg-gray-200 rounded-full h-2">
              <div className="bg-indigo-600 h-2 rounded-full animate-pulse" style={{ width: '45%' }}></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoadingSpinner;
