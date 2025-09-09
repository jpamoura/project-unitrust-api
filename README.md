# Unitrust API - Underwriting & Returns Extractor

A robust, modular FastAPI application for extracting data from PDF underwriting and returns reports with advanced CSV comparison capabilities.

## Features

- **Underwriting Extraction**: `/extract` - Processes underwriting activity reports
- **Returns Extraction**: `/returns` - Processes returns/drafts reports
- **CSV Comparison**: `/compare/preview` and `/compare/confirm` - Compares CSV files
- **Multiple Parsers**: Support for different PDF formats with fallback strategies
- **Modular Architecture**: Clean, maintainable code structure
- **Background Processing**: Asynchronous file processing
- **File Caching**: Temporary file storage for preview/confirm workflow

## API Endpoints

### Health Check
- `GET /` - Root endpoint with service information
- `GET /healthz` - Application health status

### Underwriting Extraction
- `POST /extract` - Extracts data from underwriting reports
  - **Parameters:**
    - `pdf`: PDF file (required)
    - `document_type`: Document type (required)
    - `forward_url`: URL to forward data to (optional)
    - `bearer`: Bearer token for authentication (optional)
    - `basic`: Basic auth credentials (optional)
    - `return_text_sample`: "1" to return text sample (optional)
    - `custom_data`: JSON string with custom data (optional)

### Returns Extraction
- `POST /returns` - Extracts data from returns reports
  - **Parameters:**
    - `pdf`: PDF file (required)
    - `document_type`: Document type (required)
    - `forward_url`: URL to forward data to (optional)
    - `bearer`: Bearer token for authentication (optional)
    - `basic`: Basic auth credentials (optional)
    - `return_text_sample`: "1" to return text sample (optional)
    - `custom_data`: JSON string with custom data (optional)

### CSV Comparison
- `POST /compare/preview` - Preview comparison between CSV files
  - **Parameters:**
    - `csv_file`: CSV file (required)
    - `custom_data`: JSON string with custom data (optional)
    - `forward_url`: URL to forward data to (optional)
    - `bearer`: Bearer token for authentication (optional)
    - `basic`: Basic auth credentials (optional)

- `POST /compare/confirm` - Confirm CSV file upload
  - **Body:**
    - `upload_token`: Token from preview endpoint (required)
    - `custom_data`: JSON object with custom data (optional)
    - `forward_url`: URL to forward data to (optional)
    - `bearer`: Bearer token for authentication (optional)
    - `basic`: Basic auth credentials (optional)

## Project Structure

```
project-unitrust-api/
├── app/
│   ├── main.py                    # Main FastAPI application (19 lines)
│   ├── config.py                  # Configuration and constants
│   ├── models.py                  # Pydantic models and data structures
│   ├── utils.py                   # Utility functions and helpers
│   ├── parsers/                   # Document parsing modules
│   │   ├── __init__.py
│   │   ├── underwriting_parser.py # Underwriting report parser
│   │   ├── returns_parser.py      # Returns report parser
│   │   └── csv_parser.py          # CSV file parser and comparison
│   ├── services/                  # Business logic services
│   │   ├── __init__.py
│   │   ├── file_service.py        # File upload and caching
│   │   └── text_extraction_service.py # PDF text extraction
│   └── routes/                    # API route handlers
│       ├── __init__.py
│       ├── underwriting_routes.py # Underwriting endpoints
│       ├── returns_routes.py      # Returns endpoints
│       └── csv_routes.py          # CSV comparison endpoints
├── Dockerfile                     # Docker configuration
├── docker-compose.yml             # Docker Compose for development
├── requirements.txt               # Python dependencies
├── .gitignore                     # Git ignore rules
└── README.md                      # This file
```

## Architecture Overview

### Modular Design
The application follows a clean, modular architecture with clear separation of concerns:

- **Routes**: Handle HTTP requests and responses
- **Services**: Contain business logic and external integrations
- **Parsers**: Process different document types (PDF, CSV)
- **Models**: Define data structures and validation
- **Utils**: Provide common utility functions
- **Config**: Centralize configuration and constants

### Key Components

#### Parsers
- **Underwriting Parser**: Extracts policy data from underwriting reports
- **Returns Parser**: Processes return draft reports
- **CSV Parser**: Handles CSV file parsing and comparison logic

#### Services
- **File Service**: Manages file uploads, caching, and Back4App integration
- **Text Extraction Service**: Extracts text from PDFs using multiple fallback strategies

#### Routes
- **Underwriting Routes**: `/extract` endpoint for underwriting data
- **Returns Routes**: `/returns` endpoint for returns data
- **CSV Routes**: `/compare/*` endpoints for CSV comparison workflow

## Dependencies

- **FastAPI**: Modern and fast web framework
- **pdfplumber**: Primary PDF text extraction
- **PyMuPDF (fitz)**: Alternative PDF library for fallback
- **PyPDF2**: Additional PDF parser for compatibility
- **pandas**: CSV data manipulation and analysis
- **numpy**: Numerical operations
- **requests**: HTTP client for external API calls
- **pydantic**: Data validation and serialization
- **python-multipart**: File upload handling

## Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd project-unitrust-api
   ```

2. **Create virtual environment**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables**
   ```bash
   export BUBBLE_URL="your-bubble-url"
   export BUBBLE_TOKEN="your-bubble-token"
   export X_PARSE_APPLICATION_ID="your-parse-app-id"
   export X_PARSE_MASTER_KEY="your-parse-master-key"
   ```

## Usage

### Development Server
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker
```bash
docker-compose up --build
```

### API Documentation
Once running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## Configuration

The application uses environment variables for configuration. Copy `env.example` to `.env` and update the values:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Application environment (development/production) | development |
| `PROTECT_DOCS` | Enable documentation protection | false |
| `DOCS_USERNAME` | Username for docs authentication | admin |
| `DOCS_PASSWORD` | Password for docs authentication | dev123 |
| `BUBBLE_URL` | Bubble.io webhook URL | None |
| `BUBBLE_TOKEN` | Bubble.io authentication token | None |
| `X_PARSE_APPLICATION_ID` | Back4App application ID | Default value |
| `X_PARSE_MASTER_KEY` | Back4App master key | Default value |
| `BACK4APP_FILES_URL` | Back4App files endpoint | Default value |
| `BACK4APP_CSV_CLASS_URL` | Back4App CSV class endpoint | Default value |
| `MAX_UPLOAD_MB` | Maximum file upload size in MB | 20 |

### Documentation Protection

The API includes built-in documentation protection:

- **Development**: Documentation is open and accessible without authentication
- **Production**: Documentation requires HTTP Basic Authentication

**Accessing Protected Documentation:**
1. Navigate to `http://localhost:8000/docs` or `http://localhost:8000/redoc`
2. Enter credentials when prompted:
   - Username: `admin` (or value from `DOCS_USERNAME`)
   - Password: `dev123` (or value from `DOCS_PASSWORD`)
3. Browser will remember credentials for the session

## Development

### Code Structure
- **Modular Design**: Each component has a single responsibility
- **Type Hints**: Full type annotation for better IDE support
- **Error Handling**: Comprehensive error handling and validation
- **Background Tasks**: Asynchronous processing for heavy operations

### Adding New Features
1. **New Parser**: Add to `app/parsers/`
2. **New Service**: Add to `app/services/`
3. **New Route**: Add to `app/routes/` and include in `main.py`
4. **New Model**: Add to `app/models.py`

### Testing
```bash
# Run tests (when implemented)
pytest tests/

# Run with coverage
pytest --cov=app tests/
```

## Production Considerations

- **File Caching**: Replace in-memory cache with Redis for production
- **Error Monitoring**: Add logging and monitoring (e.g., Sentry)
- **Rate Limiting**: Implement rate limiting for API endpoints
- **Security**: Add authentication and authorization
- **Scaling**: Use multiple workers with Gunicorn

## License

This project is proprietary software. All rights reserved.
