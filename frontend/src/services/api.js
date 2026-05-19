import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8888';

const api = axios.create({
  baseURL: API_BASE_URL,
  // timeout: 300000, // 5 minutes timeout for scraping
  headers: {
    'Content-Type': 'application/json',
  },
});

export const scrapeJobs = async (url) => {
  try {
    const response = await api.post('/scrape', { url });
    return response.data;
  } catch (error) {
    if (error.response) {
      throw new Error(error.response.data.detail || 'Server error occurred');
    } else if (error.request) {
      throw new Error('No response from server. Please check if the backend is running.');
    } else {
      throw new Error('Request failed: ' + error.message);
    }
  }
};

export default api;
