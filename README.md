Underwriting Extractor API
A FastAPI API for extracting data from PDF underwriting and returns reports.

Features
Underwriting Extraction: /extract - Processes underwriting activity reports

Returns Extraction: /returns - Processes returns/drafts reports

Multiple Parsers: Support for different PDF formats

Robust Fallbacks: Multiple text extraction strategies

Deploy on Back4App
Endpoints
Health Check
GET /healthz - Application status

Underwriting Extraction
POST /extract - Extracts data from underwriting reports
  - Parameters:
    - pdf: PDF file (required)
    - forward_url: URL to forward data to (optional)
    - return_text_sample: "1" to return a text sample (optional)

Returns Extraction
POST /returns - Extracts data from returns reports
  - Parameters:
    - pdf: PDF file (required)
    - forward_url: URL to forward data to (optional)
    - return_text_sample: "1" to return a text sample (optional)
    - bearer: Bearer Token for authentication (optional)
    - basic: Basic Auth credentials (optional)

Project Structure
project-unitrust-api/
├── app/
│   ├── main.py          # Main FastAPI application
│   └── returns.py       # Returns module (integrated)
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose for development
├── requirements.txt     # Python dependencies
└── README.md           # This file
Deployment
Check logs on the dashboard

<<<<<<< HEAD
Test locally with Docker Compose
=======
Test locally with Docker Compose
>>>>>>> e91faa8097921b667009a57cac3ed57d0faeef84
