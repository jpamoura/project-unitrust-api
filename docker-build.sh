#!/bin/bash

# Script para build e deploy da aplicação Docker

set -e

echo "🐳 Building Unitrust API Docker Image..."

# Build da imagem
docker build -t unitrust-api:latest .

echo "✅ Docker image built successfully!"

# Verificar se a imagem foi criada
if docker images | grep -q "unitrust-api"; then
    echo "📦 Image 'unitrust-api:latest' created successfully"
else
    echo "❌ Failed to create Docker image"
    exit 1
fi

# Opção para executar o container
if [ "$1" = "run" ]; then
    echo "🚀 Starting container..."
    docker run -d \
        --name unitrust-api \
        -p 8000:8000 \
        -e ENVIRONMENT=production \
        -e PROTECT_DOCS=true \
        -e DOCS_USERNAME=admin \
        -e DOCS_PASSWORD=dev123 \
        -v $(pwd)/logs:/app/logs \
        unitrust-api:latest
    
    echo "✅ Container started successfully!"
    echo "🌐 API available at: http://localhost:8000"
    echo "📖 Documentation at: http://localhost:8000/docs"
    echo "📊 Logs dashboard at: http://localhost:8000/logs/"
fi

echo "🎉 Build completed successfully!"
