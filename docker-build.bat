@echo off
REM Script para build e deploy da aplicação Docker no Windows

echo 🐳 Building Unitrust API Docker Image...

REM Build da imagem
docker build -t unitrust-api:latest .

if %ERRORLEVEL% neq 0 (
    echo ❌ Failed to build Docker image
    exit /b 1
)

echo ✅ Docker image built successfully!

REM Verificar se a imagem foi criada
docker images | findstr "unitrust-api" >nul
if %ERRORLEVEL% neq 0 (
    echo ❌ Failed to create Docker image
    exit /b 1
)

echo 📦 Image 'unitrust-api:latest' created successfully

REM Opção para executar o container
if "%1"=="run" (
    echo 🚀 Starting container...
    docker run -d ^
        --name unitrust-api ^
        -p 8000:8000 ^
        -e ENVIRONMENT=production ^
        -e PROTECT_DOCS=true ^
        -e DOCS_USERNAME=admin ^
        -e DOCS_PASSWORD=dev123 ^
        -v %cd%\logs:/app/logs ^
        unitrust-api:latest
    
    if %ERRORLEVEL% neq 0 (
        echo ❌ Failed to start container
        exit /b 1
    )
    
    echo ✅ Container started successfully!
    echo 🌐 API available at: http://localhost:8000
    echo 📖 Documentation at: http://localhost:8000/docs
    echo 📊 Logs dashboard at: http://localhost:8000/logs/
)

echo 🎉 Build completed successfully!
