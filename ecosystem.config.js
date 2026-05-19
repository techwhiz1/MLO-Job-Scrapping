module.exports = {
  apps: [{
    name: 'job-scraping-backend',
    script: 'backend/main.py',
    interpreter: 'python3',
    cwd: '/home/ubuntu/job_scraping',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      ENVIRONMENT: 'development',
      PYTHONPATH: '/home/ubuntu/job_scraping',
      PORT: 8888,
      HOST: '0.0.0.0'
    },
    env_production: {
      ENVIRONMENT: 'production',
      PYTHONPATH: '/home/ubuntu/job_scraping',
      PORT: 8888,
      HOST: '0.0.0.0'
    },
    error_file: './logs/err.log',
    out_file: './logs/out.log',
    log_file: './logs/combined.log',
    time: true
  }]
};
