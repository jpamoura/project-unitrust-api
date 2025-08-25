# Underwriting Extractor API

API FastAPI para extração de dados de relatórios PDF de underwriting e returns.

## Funcionalidades

- **Extração de Underwriting**: `/extract` - Processa relatórios de atividade de underwriting
- **Extração de Returns**: `/returns` - Processa relatórios de returns/drafts
- **Múltiplos parsers**: Suporte para diferentes formatos de PDF
- **Fallbacks robustos**: Múltiplas estratégias de extração de texto

## Deploy no Back4App

### Pré-requisitos

1. Conta no [Back4App](https://www.back4app.com/)
2. Docker instalado localmente (para testes)
3. Git configurado

### Passo a Passo

#### 1. Preparar o Repositório

```bash
# Certifique-se de que todos os arquivos estão commitados
git add .
git commit -m "Preparando para deploy no Back4App"
git push origin main
```

#### 2. No Back4App Dashboard

1. **Criar Nova App**:
   - Acesse [Back4App Dashboard](https://www.back4app.com/dashboard)
   - Clique em "Create New App"
   - Escolha "Backend as a Service"

2. **Configurar App**:
   - Nome: `unitrust-api` (ou nome de sua preferência)
   - Escolha o plano desejado

3. **Configurar Deploy**:
   - Vá para "App Settings" > "Deploy"
   - Escolha "Docker" como método de deploy
   - Configure as seguintes variáveis de ambiente:

#### 3. Variáveis de Ambiente (Opcional)

```bash
# No Back4App Dashboard > App Settings > Environment Variables
PYTHONPATH=/app
PORT=8000
```

#### 4. Deploy

1. **Conectar Repositório**:
   - Vá para "App Settings" > "Deploy" > "Git"
   - Conecte seu repositório GitHub/GitLab
   - Selecione a branch `main`

2. **Configurar Build**:
   - Build Command: `docker build -t unitrust-api .`
   - Start Command: `docker run -p 8000:8000 unitrust-api`

3. **Deploy Automático**:
   - Ative o deploy automático
   - A cada push para `main`, o Back4App fará o rebuild

#### 5. Verificar Deploy

Após o deploy, sua API estará disponível em:
- **URL Base**: `https://seu-app.back4app.io`
- **Health Check**: `https://seu-app.back4app.io/healthz`
- **Documentação**: `https://seu-app.back4app.io/docs`

## Desenvolvimento Local

### Com Docker Compose

```bash
# Build e executar
docker-compose up --build

# Acessar a API
curl http://localhost:8000/healthz
```

### Sem Docker

```bash
# Instalar dependências
pip install -r requirements.txt

# Executar
cd app
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Endpoints

### Health Check
- `GET /healthz` - Status da aplicação

### Underwriting Extraction
- `POST /extract` - Extrai dados de relatórios de underwriting
  - Parâmetros:
    - `pdf`: Arquivo PDF (obrigatório)
    - `forward_url`: URL para encaminhar dados (opcional)
    - `return_text_sample`: "1" para retornar amostra do texto (opcional)

### Returns Extraction
- `POST /returns` - Extrai dados de relatórios de returns
  - Parâmetros:
    - `pdf`: Arquivo PDF (obrigatório)
    - `forward_url`: URL para encaminhar dados (opcional)
    - `return_text_sample`: "1" para retornar amostra do texto (opcional)
    - `bearer`: Token Bearer para autenticação (opcional)
    - `basic`: Credenciais Basic Auth (opcional)

## Estrutura do Projeto

```
project-unitrust-api/
├── app/
│   ├── main.py          # Aplicação principal FastAPI
│   └── returns.py       # Módulo de returns (integrado)
├── Dockerfile           # Configuração Docker
├── docker-compose.yml   # Docker Compose para desenvolvimento
├── requirements.txt     # Dependências Python
└── README.md           # Este arquivo
```

## Troubleshooting

### Problemas Comuns

1. **Porta 8000 não disponível**:
   - Verifique se a porta está configurada corretamente no Back4App
   - Use a variável de ambiente `PORT` se necessário

2. **Dependências não encontradas**:
   - Verifique se o `requirements.txt` está atualizado
   - Force um rebuild no Back4App

3. **Erro de permissão**:
   - Verifique as configurações de segurança do Back4App
   - Certifique-se de que o Dockerfile está correto

### Logs

No Back4App Dashboard:
- Vá para "App Settings" > "Logs"
- Verifique os logs de build e runtime

## Suporte

Para problemas específicos do Back4App:
- [Back4App Documentation](https://docs.back4app.com/)
- [Back4App Support](https://www.back4app.com/support)

Para problemas da aplicação:
- Verifique os logs no dashboard
- Teste localmente com Docker Compose
