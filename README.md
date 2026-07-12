# WildlifeVN - He thong tra cuu va nhan dien dong vat hoang da Viet Nam

WildlifeVN la do an tot nghiep xay dung he thong web ho tro tra cuu, nhan dien va hoi dap thong tin ve dong vat hoang da Viet Nam. He thong ket hop thu vien loai, mo-dun nhan dien anh bang BioCLIP va chatbot RAG tra loi cau hoi bao ton bang tieng Viet.

## 1. Muc tieu do an

- Xay dung website tra cuu thong tin cac loai dong vat hoang da.
- Ho tro tim kiem, loc, xem ho so khoa hoc va hinh anh tung loai.
- Tich hop chatbot hoi dap dua tren RAG de tra loi theo ngu canh loai.
- Tich hop AI nhan dien anh, tra ve danh sach loai ung vien de nguoi dung xac nhan.
- Xay dung pipeline du lieu, tien xu ly anh, huan luyen model va kiem thu he thong.

## 2. Dataset

Dataset va cac artifact lien quan duoc luu tai Google Drive:

[WildlifeVN Dataset - Google Drive](https://drive.google.com/drive/folders/1PHaVCa8SbIZ2O7-902vgzTk8xLh2VYq3?usp=sharing)

Dataset bao gom du lieu anh phuc vu huan luyen model nhan dien, du lieu loai da tien xu ly va cac artifact lien quan tuy theo tung phien ban dong goi.

## 3. Kien truc tong quan

```text
Frontend React/Vite
  -> wildlife-backend Spring Boot /api
       -> MongoDB wildlife_library
       -> wildlife-ai FastAPI /api/chatbot/*
            -> RAG runtime
            -> FAISS knowledge base
            -> BioCLIP image recognition
            -> Cerebras LLM API
```

Vai tro tung thanh phan:

- `frontend`: giao dien React cho thu vien loai, trang chi tiet va chatbot.
- `wildlife-backend`: REST API Spring Boot, truy van MongoDB va proxy request chatbot sang AI service.
- `wildlife-ai`: FastAPI service xu ly chatbot RAG, session hoi thoai va nhan dien anh.
- `RAG`: workspace build knowledge base, audit du lieu, tao FAISS index va chay eval chatbot.
- `Preprocessed`: script/notebook crawl va tien xu ly du lieu anh.
- `Training`: script/notebook huan luyen BioCLIP.
- `reports`: bao cao phan tich, kiem thu, deploy va dashboard kiem thu truc quan.

## 4. Cong nghe su dung

### Frontend

- React 19
- Vite 8
- React Router
- Axios
- React Markdown
- CSS tuy bien

### Backend

- Java 21
- Spring Boot 3.5
- Spring Web
- Spring Data MongoDB
- Jakarta Validation
- Spring Boot Actuator
- Springdoc OpenAPI
- JUnit, MockMvc, Mockito, Selenium

### AI service

- Python / FastAPI
- RAG pipeline
- FAISS
- Vietnamese-SBERT
- BioCLIP ViT-B/16
- Cerebras API
- MongoDB

## 5. Cau truc thu muc chinh

```text
DATN/
  frontend/                 # React/Vite frontend
  wildlife-backend/         # Spring Boot backend
  wildlife-ai/              # FastAPI AI service
  RAG/                      # Build/eval/audit knowledge base RAG
  Preprocessed/             # Crawl va tien xu ly du lieu anh
  Training/                 # Huan luyen model BioCLIP
  reports/                  # Bao cao, deploy guide, dashboard kiem thu
  tests/                    # Load test va cac script test
  training-preprocessing-final/
                            # Notebook preprocessing va training cuoi de chia se len GitHub
  docker-compose.prod.yml   # Docker compose demo/production
```

## 6. Notebook preprocessing va training cuoi

Thu muc `training-preprocessing-final/` chi chua 2 notebook cuoi cung lien quan den preprocessing va training:

```text
training-preprocessing-final/
  01_preprocessing_final.ipynb
  02_training_bioclip_final.ipynb
```

Trong do:

- `01_preprocessing_final.ipynb`: tien xu ly du lieu anh, loai trung lap, chia train/validation/test, kiem tra leakage va can bang du lieu.
- `02_training_bioclip_final.ipynb`: huan luyen model BioCLIP ViT-B/16 cho bai toan nhan dien dong vat hoang da.

Dataset va model weight lon khong nam trong GitHub, ma duoc chia se qua Google Drive o muc Dataset phia tren.

## 7. Chuan bi moi truong

Yeu cau khuyen nghi:

- Node.js `20.19+` hoac `22.12+`
- npm
- Java 21
- Python 3.11+ hoac moi hon
- MongoDB local hoac MongoDB Atlas
- Maven Wrapper co san trong `wildlife-backend`

Neu chay day du chatbot RAG va nhan dien anh, can them:

- model BioCLIP weights
- `class_mapping.json`
- FAISS index va metadata
- `CEREBRAS_API_KEY`

## 8. Cau hinh bien moi truong

### Backend

Backend doc cac bien moi truong:

```env
MONGODB_URI=mongodb://localhost:27017/wildlife_library
MONGODB_DATABASE=wildlife_library
AI_SERVER_BASE_URL=http://localhost:8001
```

Neu khong set, backend co default trong `wildlife-backend/src/main/resources/application.properties`.

### AI service

Trong `wildlife-ai`, tao file `.env` tu file mau:

```bash
cd wildlife-ai
cp .env.example .env
```

Mot so bien quan trong:

```env
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=wildlife_library
MONGODB_SPECIES_COLLECTION=species
MONGODB_SPECIES_RAW_COLLECTION=species_raw

CEREBRAS_API_KEY=
CEREBRAS_MODEL=qwen-3-235b-a22b-instruct-2507

RAG_PROJECT_DIR=app/rag_runtime
VISION_MODEL_WEIGHTS_PATH=model/bioclip/best_model.pth
VISION_CLASS_MAPPING_PATH=model/bioclip/class_mapping.json
VISION_TOP_K=6
```

### Frontend

Frontend goi backend qua:

```env
VITE_API_BASE_URL=http://localhost:8080/api
```

Neu deploy cung domain qua reverse proxy, build voi:

```bash
VITE_API_BASE_URL=/api npm run build
```

## 9. Chay local

Thu tu khoi dong khuyen nghi:

1. MongoDB
2. AI service FastAPI
3. Backend Spring Boot
4. Frontend React/Vite

### 8.1. Chay MongoDB

Neu dung MongoDB local:

```bash
mongod
```

Database mac dinh:

```text
wildlife_library
```

Can co cac collection chinh:

```text
species
species_raw
```

### 8.2. Chay AI service

```bash
cd wildlife-ai
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8001
```

Kiem tra:

```bash
curl http://localhost:8001/health
```

Swagger UI cua AI service:

```text
http://localhost:8001/docs
```

### 8.3. Chay backend

```bash
cd wildlife-backend
./mvnw spring-boot:run
```

Kiem tra backend:

```bash
curl http://localhost:8080/api/system/health
```

Swagger UI:

```text
http://localhost:8080/swagger-ui.html
```

OpenAPI JSON:

```text
http://localhost:8080/api-docs
```

### 8.4. Chay frontend

```bash
cd frontend
npm install
npm run dev
```

Mo trinh duyet:

```text
http://localhost:5173
```

## 10. Cac endpoint chinh

### Backend system

```text
GET /api/system/health
```

### Species API

```text
GET /api/species
GET /api/species/{speciesId}/summary
GET /api/species/{speciesId}/scientific-profile
GET /api/species/{speciesId}/media
```

Query params cua `/api/species`:

```text
keyword
sectorSlug
conservationStatus
page
size
```

### Chatbot API

```text
POST /api/chatbot/query
POST /api/chatbot/query-debug
POST /api/chatbot/confirm-species
POST /api/chatbot/clear-species
GET  /api/chatbot/rag-health?load=false
```

## 11. Chuc nang chinh

### Thu vien loai

- Hien thi danh sach loai theo nhom.
- Tim kiem theo ten tieng Viet hoac ten khoa hoc.
- Loc theo nhom va tinh trang bao ton.
- Xem tom tat va ho so khoa hoc cua tung loai.

### Chatbot RAG

- Hoi dap bang tieng Viet ve dong vat hoang da.
- Duy tri ngu canh loai trong session.
- Ho tro follow-up nhu "loai nay song o dau?" hoac "no co nguy cap khong?".
- Truy xuat tri thuc tu FAISS, MongoDB va chunks metadata.
- Uu tien tra loi tu du lieu co cau truc khi co the de giam hallucination.

### AI nhan dien anh

- Nguoi dung gui anh tu file, paste hoac keo tha.
- Frontend nen anh truoc khi gui.
- AI service dung BioCLIP de du doan top-k loai ung vien.
- Nguoi dung xac nhan loai truoc khi chatbot tra loi tiep theo ngu canh.

## 12. Du lieu va tien xu ly

### Du lieu loai

Du lieu loai duoc tong hop tu nhieu nguon, gom:

- iNaturalist: observation va media.
- GBIF: taxonomy, accepted name, rank.
- Wikipedia VI/EN: mo ta va thong tin ngu canh.
- IUCN Red List: tinh trang bao ton quoc te.
- CITES / Species+: thong tin phap ly va buon ban quoc te.
- Sach do Viet Nam / VAST va cac nguon bo sung khac.

Sau khi crawl, du lieu duoc chuan hoa thanh:

```text
species      # phuc vu frontend/backend
species_raw  # phuc vu RAG/chatbot/evidence
```

### Du lieu anh

Pipeline anh gom:

- Crawl anh theo loai.
- Kiem tra file loi.
- Chuan hoa label theo ten khoa hoc.
- Loai anh trung lap bang hash.
- Chia train/validation/test.
- Kiem tra leakage giua cac split.
- Can bang du lieu train bang augmentation.
- Huan luyen BioCLIP ViT-B/16.

## 13. Kiem thu

### Frontend

```bash
cd frontend
npm run lint
npm run build
```

### Backend

```bash
cd wildlife-backend
./mvnw test
```

### Selenium E2E

Can frontend dang chay truoc:

```bash
cd wildlife-backend
FRONTEND_BASE_URL=http://localhost:5173 ./mvnw -Pe2e verify
```

### k6 load test

```bash
API_BASE_URL=http://localhost:8080/api k6 run tests/load/wildlife-api.k6.js
```

### Dashboard kiem thu truc quan

Dashboard local nam tai:

```text
reports/quality-dashboard
```

Chay:

```bash
node reports/quality-dashboard/server.mjs
```

Mo:

```text
http://127.0.0.1:4177/admin/quality-dashboard
```

## 14. Build va deploy demo

Project co Dockerfile cho backend va AI service:

```text
wildlife-backend/Dockerfile
wildlife-ai/Dockerfile
```

Build image:

```bash
docker build --platform linux/amd64 -t wildlife-backend:local ./wildlife-backend
docker build --platform linux/amd64 -t wildlife-ai:local ./wildlife-ai
```

Chay docker compose production/demo:

```bash
docker compose --env-file .env.prod -f docker-compose.prod.yml up -d
```

Frontend production build:

```bash
cd frontend
VITE_API_BASE_URL=/api npm run build
```

Mo hinh deploy demo da dung:

```text
Caddy HTTPS
  -> frontend static files
  -> /api/* reverse proxy wildlife-backend:8080
       -> wildlife-ai:8001
       -> MongoDB Atlas
```

## 15. Ghi chu bao mat va gioi han

- Khong commit `.env`, `MONGODB_URI`, `CEREBRAS_API_KEY` hoac secret len GitHub.
- AI service khong nen public truc tiep; nen di qua backend.
- Endpoint debug nhu `/api/chatbot/query-debug` nen duoc bao ve neu public.
- Chatbot session hien co the luu in-memory o AI service, nen restart service co the mat ngu canh.
- Nen them rate limit cho chatbot neu mo public rong.

## 16. Ghi chu khi push len GitHub

Repo da co `.gitignore` de loai cac file khong nen dua len GitHub:

- secret va file moi truong `.env`
- virtual environment `.venv`
- `node_modules`, `dist`, `target`
- dataset anh va thu muc preprocess sinh ra
- model weight `.pth`, checkpoint, FAISS `.bin`
- archive Docker/image `.tar.gz`
- backup MongoDB/Atlas
- cache Python, Hugging Face, notebook checkpoints

Nhung thanh phan nen push:

- ma nguon frontend/backend/AI
- notebook cuoi trong `training-preprocessing-final`
- README va cac bao cao Markdown can chia se
- script test, load test va dashboard kiem thu nhe
- cau hinh mau `.env.example`

Truoc khi commit, nen kiem tra:

```bash
git status --short
```

Neu thay file model, dataset, backup `.bson`, archive `.tar.gz` hoac secret `.env` trong danh sach commit thi khong nen push.

## 17. Tai lieu lien quan trong repo

- `reports/kiem-thu-wildlifevn-2026-05-31.md`: bao cao kiem thu.
- `reports/deploy-wildlifevn.md`: huong dan deploy.
- `frontend/FRONTEND_ANALYSIS.md`: phan tich frontend.
- `wildlife-backend/BACKEND_DETAILED_ANALYSIS.md`: phan tich backend.
- `wildlife-ai/CHATBOT_AI_LATEST_ANALYSIS_2026-05-28.md`: phan tich chatbot AI/RAG.
- `Preprocessed/TRAINING_DATA_CRAWL_PREPROCESS_GUIDE.md`: huong dan crawl va tien xu ly du lieu training.

## 18. Tac gia

Do an tot nghiep: He thong tra cuu va nhan dien dong vat hoang da Viet Nam ket hop chatbot hoi dap thong tin bao ton bang tieng Viet.
