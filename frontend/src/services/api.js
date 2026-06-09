import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8888';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const scrapeJobs = async (url) => {
  try {
    const response = await api.post('/scrape', {
      url,
      max_jobs: 3,
      include_html_content: true,
    });
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Server error occurred');
    } else if (error.code === 'ECONNABORTED') {
      throw new Error('Scraping timed out. Try a smaller job feed or run the backend scrape directly.');
    } else if (error.request) {
      throw new Error('No response from server. Please check if the backend is running.');
    } else {
      throw new Error('Request failed: ' + error.message);
    }
  }
};

export default api;
