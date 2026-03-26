# wildlife-ai (FastAPI)

FastAPI service for species and chatbot APIs with session context (no full reset required).

## Run

1. Create and activate virtual environment
2. Install deps

```bash
pip install -r requirements.txt
```

3. Configure environment

```bash
cp .env.example .env
```

4. Start server

```bash
uvicorn app.main:app --reload --port 8001
```

## Endpoints

- `GET /health`
- `GET /api/species`
- `GET /api/species/{species_id}/summary`
- `GET /api/species/{species_id}/scientific-profile`
- `POST /api/chatbot/query`
- `POST /api/chatbot/confirm-species`
- `POST /api/chatbot/clear-species`

Swagger UI: `http://localhost:8001/docs`
