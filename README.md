# Underwriting Extractor API

API FastAPI para extração de dados de relatórios PDF de underwriting e returns.

## Funcionalidades

- **Extração de Underwriting**: `/extract` - Processa relatórios de atividade de underwriting
- **Extração de Returns**: `/returns` - Processa relatórios de returns/drafts
- **Múltiplos parsers**: Suporte para diferentes formatos de PDF
- **Fallbacks robustos**: Múltiplas estratégias de extração de texto


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

