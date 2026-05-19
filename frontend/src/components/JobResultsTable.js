import React, { useState, useMemo } from 'react';
import { CSVLink } from 'react-csv';

const JobResultsTable = ({ jobs }) => {
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage] = useState(10);
  const [sortField, setSortField] = useState('');
  const [sortDirection, setSortDirection] = useState('asc');
  const [expandedRows, setExpandedRows] = useState(new Set());

  // CSV headers
  const csvHeaders = [
    { label: 'Employer', key: 'employer' },
    { label: 'Job Title', key: 'job_title' },
    { label: 'Job ID', key: 'job_id' },
    { label: 'Location', key: 'location' },
    { label: 'Salary Range', key: 'salary_range' },
    { label: 'Application Deadline', key: 'application_deadline' },
    { label: 'Job Description', key: 'job_description' },
    { label: 'Key Responsibilities', key: 'key_responsibilities' },
    { label: 'Qualifications and Skills', key: 'qualifications_and_skills' },
    { label: 'Perks and Benefits', key: 'perks_and_benefits' },
    { label: 'Years of Experience', key: 'preferred_years_of_experience' },
    { label: 'Educational Level', key: 'educational_level' },
    { label: 'Certification Level', key: 'certification_level' },
    { label: 'Interview Format', key: 'interview_format' },
    { label: 'Image URL', key: 'image_url' }
  ];

  // Sort jobs
  const sortedJobs = useMemo(() => {
    if (!sortField) return jobs;

    return [...jobs].sort((a, b) => {
      const aValue = a[sortField] || '';
      const bValue = b[sortField] || '';
      
      if (sortDirection === 'asc') {
        return aValue.toString().localeCompare(bValue.toString());
      } else {
        return bValue.toString().localeCompare(aValue.toString());
      }
    });
  }, [jobs, sortField, sortDirection]);

  // Pagination
  const totalPages = Math.ceil(sortedJobs.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const currentJobs = sortedJobs.slice(startIndex, endIndex);

  const handleSort = (field) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const toggleRowExpansion = (index) => {
    const newExpandedRows = new Set(expandedRows);
    if (newExpandedRows.has(index)) {
      newExpandedRows.delete(index);
    } else {
      newExpandedRows.add(index);
    }
    setExpandedRows(newExpandedRows);
  };

  const truncateText = (text, maxLength = 100) => {
    if (!text) return 'N/A';
    if (text.length <= maxLength) return text;
    return text.substring(0, maxLength) + '...';
  };

  if (!jobs || jobs.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-gray-500">No jobs found.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with export button */}
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-medium text-gray-900">
          Job Results ({jobs.length} jobs found)
        </h2>
        <CSVLink
          data={jobs}
          headers={csvHeaders}
          filename={`job-scraping-results-${new Date().toISOString().split('T')[0]}.csv`}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
        >
          <svg className="-ml-1 mr-2 h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
          </svg>
          Export CSV
        </CSVLink>
      </div>

      {/* Table */}
      <div className="overflow-hidden shadow ring-1 ring-black ring-opacity-5 md:rounded-lg">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-300">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Actions
                </th>
                <th 
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('employer')}
                >
                  <div className="flex items-center">
                    Employer
                    {sortField === 'employer' && (
                      <span className="ml-1">
                        {sortDirection === 'asc' ? '↑' : '↓'}
                      </span>
                    )}
                  </div>
                </th>
                <th 
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('job_title')}
                >
                  <div className="flex items-center">
                    Job Title
                    {sortField === 'job_title' && (
                      <span className="ml-1">
                        {sortDirection === 'asc' ? '↑' : '↓'}
                      </span>
                    )}
                  </div>
                </th>
                <th 
                  className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"
                  onClick={() => handleSort('location')}
                >
                  <div className="flex items-center">
                    Location
                    {sortField === 'location' && (
                      <span className="ml-1">
                        {sortDirection === 'asc' ? '↑' : '↓'}
                      </span>
                    )}
                  </div>
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Salary Range
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                  Description
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {currentJobs.map((job, index) => {
                const globalIndex = startIndex + index;
                const isExpanded = expandedRows.has(globalIndex);
                
                return (
                  <React.Fragment key={globalIndex}>
                    <tr className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <button
                          onClick={() => toggleRowExpansion(globalIndex)}
                          className="text-indigo-600 hover:text-indigo-900"
                        >
                          {isExpanded ? '▼' : '▶'} Details
                        </button>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {job.employer || 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {job.job_title || 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {job.location || 'N/A'}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                        {job.salary_range || 'N/A'}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-900 max-w-xs">
                        {truncateText(job.job_description)}
                      </td>
                    </tr>
                    
                    {isExpanded && (
                      <tr>
                        <td colSpan="6" className="px-6 py-4 bg-gray-50">
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                            <div>
                              <strong>Job ID:</strong> {job.job_id || 'N/A'}
                            </div>
                            <div>
                              <strong>Application Deadline:</strong> {job.application_deadline || 'N/A'}
                            </div>
                            <div>
                              <strong>Years of Experience:</strong> {job.preferred_years_of_experience || 'N/A'}
                            </div>
                            <div>
                              <strong>Educational Level:</strong> {job.educational_level || 'N/A'}
                            </div>
                            <div>
                              <strong>Certification Level:</strong> {job.certification_level || 'N/A'}
                            </div>
                            <div>
                              <strong>Interview Format:</strong> {job.interview_format || 'N/A'}
                            </div>
                            <div className="md:col-span-2">
                              <strong>Key Responsibilities:</strong>
                              <p className="mt-1 text-gray-700">{job.key_responsibilities || 'N/A'}</p>
                            </div>
                            <div className="md:col-span-2">
                              <strong>Qualifications and Skills:</strong>
                              <p className="mt-1 text-gray-700">{job.qualifications_and_skills || 'N/A'}</p>
                            </div>
                            <div className="md:col-span-2">
                              <strong>Perks and Benefits:</strong>
                              <p className="mt-1 text-gray-700">{job.perks_and_benefits || 'N/A'}</p>
                            </div>
                            <div className="md:col-span-2">
                              <strong>Full Description:</strong>
                              <p className="mt-1 text-gray-700">{job.job_description || 'N/A'}</p>
                            </div>
                            {job.image_url && (
                              <div className="md:col-span-2">
                                <strong>Image:</strong>
                                <img src={job.image_url} alt="Job related" className="mt-1 max-w-xs h-auto rounded" />
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-gray-200 bg-white px-4 py-3 sm:px-6">
          <div className="flex flex-1 justify-between sm:hidden">
            <button
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
              className="relative inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <button
              onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
              disabled={currentPage === totalPages}
              className="relative ml-3 inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
          <div className="hidden sm:flex sm:flex-1 sm:items-center sm:justify-between">
            <div>
              <p className="text-sm text-gray-700">
                Showing <span className="font-medium">{startIndex + 1}</span> to{' '}
                <span className="font-medium">{Math.min(endIndex, sortedJobs.length)}</span> of{' '}
                <span className="font-medium">{sortedJobs.length}</span> results
              </p>
            </div>
            <div>
              <nav className="isolate inline-flex -space-x-px rounded-md shadow-sm" aria-label="Pagination">
                <button
                  onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
                  disabled={currentPage === 1}
                  className="relative inline-flex items-center rounded-l-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Previous
                </button>
                
                {/* Page numbers */}
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  const pageNumber = Math.max(1, Math.min(totalPages - 4, currentPage - 2)) + i;
                  if (pageNumber > totalPages) return null;
                  
                  return (
                    <button
                      key={pageNumber}
                      onClick={() => setCurrentPage(pageNumber)}
                      className={`relative inline-flex items-center px-4 py-2 text-sm font-semibold ${
                        currentPage === pageNumber
                          ? 'z-10 bg-indigo-600 text-white focus:z-20 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600'
                          : 'text-gray-900 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0'
                      }`}
                    >
                      {pageNumber}
                    </button>
                  );
                })}
                
                <button
                  onClick={() => setCurrentPage(Math.min(totalPages, currentPage + 1))}
                  disabled={currentPage === totalPages}
                  className="relative inline-flex items-center rounded-r-md px-2 py-2 text-gray-400 ring-1 ring-inset ring-gray-300 hover:bg-gray-50 focus:z-20 focus:outline-offset-0 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  Next
                </button>
              </nav>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default JobResultsTable;
