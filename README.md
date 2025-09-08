# Unitrust API - Underwriting & Returns Extractor

A robust FastAPI API for extracting data from PDF underwriting and returns reports.

## Features

- **Underwriting Extraction**: `/extract` - Processes underwriting activity reports
- **Returns Extraction**: `/returns` - Processes returns/drafts reports
- **CSV Comparison**: `/compare/preview` and `/compare/confirm` - Compares CSV files
- **Multiple Parsers**: Support for different PDF formats
- **Robust Fallbacks**: Multiple text extraction strategies

## Endpoints

### Health Check
- `GET /healthz` - Application status

### Underwriting Extraction
- `POST /extract` - Extracts data from underwriting reports
  - Parameters:
    - `pdf`: PDF file (required)
    - `document_type`: Document type (required)
    - `forward_url`: URL to forward data to (optional)
    - `return_text_sample`: "1" to return text sample (optional)

### Returns Extraction
- `POST /returns` - Extracts data from returns reports
  - Parameters:
    - `pdf`: PDF file (required)
    - `document_type`: Document type (required)
    - `forward_url`: URL to forward data to (optional)
    - `return_text_sample`: "1" to return text sample (optional)

### CSV Comparison
- `POST /compare/preview` - Preview comparison between CSV files
- `POST /compare/confirm` - Confirm CSV file upload

## Project Structure

```
project-unitrust-api/
├── app/
│   └── main.py          # Main FastAPI application
├── Dockerfile           # Docker configuration
├── docker-compose.yml   # Docker Compose for development
├── requirements.txt     # Python dependencies
└── README.md           # This file
```

## Dependencies

- **FastAPI**: Modern and fast web framework
- **pdfplumber**: PDF text extraction
- **PyMuPDF**: Alternative PDF library
- **PyPDF2**: Additional PDF parser
- **pandas**: CSV data manipulation
- **numpy**: Numerical operations
- **requests**: HTTP client
