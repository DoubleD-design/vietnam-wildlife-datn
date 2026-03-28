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

## Image Recognition Integration

The chatbot image flow can run your BioCLIP checkpoint and propose species candidates.

1. Ensure model artifacts exist:

- `../Training/bioclip_model/best_model.pth`
- `../Training/bioclip_model/class_mapping.json`

2. Configure env values in `.env` if paths differ:

- `VISION_BACKBONE`
- `VISION_MODEL_WEIGHTS_PATH`
- `VISION_CLASS_MAPPING_PATH`
- `VISION_TOP_K`
- `VISION_MIN_CONFIDENCE`

3. Call image query endpoint:

```bash
curl -X POST http://localhost:8001/api/chatbot/query \
	-H "Content-Type: application/json" \
	-d '{
		"sessionId": "demo-session",
		"imageUrl": "https://.../sample.jpg",
		"question": "Loài này có nguy cấp không?"
	}'
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
