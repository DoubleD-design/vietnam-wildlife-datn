# Phan tich moi nhat tinh nang Chatbot AI / RAG

Ngay cap nhat: 2026-05-28  
Vi tri tai lieu: `wildlife-ai/CHATBOT_AI_LATEST_ANALYSIS_2026-05-28.md`  
Muc dich: ban phan tich dat trong AI service de dung cho kiem thu, deploy va viet bao cao sau nay.

Tai lieu nay la ban copy dieu chinh tu `RAG/CHATBOT_AI_LATEST_ANALYSIS_2026-05-28.md`. Noi dung chi tap trung vao cap nhat moi nhat, khong thay the cac ban phan tich cu.

## 1. Tom tat dieu hanh

Tinh nang chatbot hien da duoc tich hop end-to-end theo luong:

```text
frontend/src/pages/ChatbotPage.jsx
  -> wildlife-backend /api/chatbot/*
  -> wildlife-ai /api/chatbot/*
  -> RagPipelineService
  -> wildlife-ai/app/rag_runtime/rag_pipeline.py
  -> FAISS + chunks_metadata + MongoDB species/species_raw + Cerebras
```

Diem quan trong nhat cua trang thai hien tai:

- `wildlife-ai/app/rag_runtime/rag_pipeline.py` moi la runtime RAG chinh dang duoc FastAPI import qua `RagPipelineService`.
- `RAG/rag_pipeline.py` van ton tai nhung cu hon nhieu: 578 dong so voi 1.924 dong cua runtime dang chay. Khong nen xem file nay la source runtime hien hanh.
- `RAG/knowledge_base` va `wildlife-ai/app/rag_runtime/knowledge_base` dang dong bo dung cung mot FAISS index va metadata: `chunks_metadata.json` va `faiss_index.bin` giong nhau.
- Runtime KB hien co 5.000 chunks cho 570 loai. Nguon chunk chinh: `cites_species_plus_official` 3.906, `wikipedia_vi` 1.071, `cites_gaur_gallery` 8, `birdlife_datazone` 8, `cites_appendices` 7.
- Chatbot da co nhieu luong tra loi khong phu thuoc LLM generation: `species_structured`, `source_evidence`, `data_quality`, `safety_legal`, `general_metadata`, `multi_species_structured`.
- Diem nghen lon hien khong nam o routing chatbot nua, ma nam o chat luong/coverage du lieu: Sach do Viet Nam chua match VAST cho nhieu loai, exact legal match Viet Nam con thieu, va nhieu truong hanh vi chi tiet chua co du lieu cau truc.

## 2. Snapshot so lieu moi nhat

| Hang muc | Ket qua moi nhat | Nguon doi chieu |
| --- | ---: | --- |
| Runtime KB chunks | 5.000 | `wildlife-ai/app/rag_runtime/knowledge_base/chunks_metadata.json` |
| So loai trong chunks | 570 | `chunks_metadata.json` |
| FAISS/metadata runtime va workspace | Giong nhau | `RAG/knowledge_base/*` vs `wildlife-ai/app/rag_runtime/knowledge_base/*` |
| Chatbot question suite | 65 QA records: PASS 53 / WARN 12 | `RAG/chatbot_runs/chatbot_eval_20260522_212959.jsonl` |
| Nhom WARN cua question suite | 12/12 la `coverage_gap` | `chatbot_eval_20260522_212959.jsonl` |
| Gold eval v1 | 60 cases: PASS 57 / WARN 3, avg 99.625 | `RAG/chatbot_runs/gold_eval_20260522_213017.md/jsonl` |
| Gold eval safety/legal v2 | 15 cases: PASS 13 / WARN 2, avg 98.83 | `RAG/chatbot_runs/gold_eval_20260522_213043.md/jsonl` |
| Data audit | 570 raw profiles + 570 species docs | `RAG/chatbot_runs/data_audit_20260522_212744.md` |
| Media audit | 570 species co thumbnail; 2.850 assets co `thumbnail_url` va `medium_url` | `RAG/chatbot_runs/media_audit_20260528_130902.md` |
| Media variants | 2.830 medium variants, 2.264 thumbnail variants, 566 docs updated | `RAG/chatbot_runs/media_variants_20260528_123124.md` |

Data audit moi nhat ghi nhan cac van de lap lai:

- `derived_safety_guidance_available`: 570.
- `legal_precaution_available`: 570.
- `missing_vn_legal_exact_match`: 570.
- `vietnam_red_not_matched_vast`: 503.
- `iucn_population_trend_unknown_official`: 99.
- `iucn_true_coverage_gap`: 27.

Dieu nay cho thay chatbot da biet noi ro gioi han du lieu, nhung kho du lieu van chua du sau cho mot so nhom cau hoi chi tiet.

## 3. Kien truc va luong xu ly

### 3.1. Frontend

File chinh: `frontend/src/pages/ChatbotPage.jsx`, `frontend/src/services/chatbotService.js`, `frontend/src/components/SpeciesCandidateModal.jsx`.

Frontend giu `sessionId` trong `localStorage` voi key `chatbot-session-id`. Neu nguoi dung vao tu trang chi tiet loai qua query `speciesId` va `speciesName`, trang chat goi `confirmSpecies` de set active species tren AI server.

Luong gui cau hoi:

1. Nguoi dung nhap text, chon anh, keo tha anh, hoac paste anh tu clipboard.
2. Neu co anh, frontend nen anh ve JPEG data URL kich thuoc toi da 1.280 px, quality 0.82.
3. Goi `POST /chatbot/query` qua service axios, mac dinh base URL `http://localhost:8080/api`.
4. Bot response duoc render bang `ReactMarkdown` + `remark-gfm`.
5. Neu response status la `NEED_SPECIES_CONFIRM`, frontend mo modal chon toi da 6 ung vien.
6. Khi nguoi dung chon loai, frontend goi `POST /chatbot/confirm-species`; neu truoc do co pending question thi AI server tu tra loi cau hoi do sau khi xac nhan loai.

Modal ung vien co hover preview anh. Khi hover, modal goi `fetchSpeciesSummary` de lay them media va cho phep chuyen thumbnail trong popup.

Nhan xet:

- UX anh da kha day du: paste, drag-drop, picker, preview, loading text.
- Frontend public chua render rieng `evidence`, `source_quality`, `retrievalWarnings`, `coverageWarnings`; cac truong nay chi co o debug/eval.
- `clearSpecies` service co san nhung UI hien tai khong con banner nut clear co dinh; viec clear dang duoc xu ly bang cau lenh text nhu "xoa loai hien tai".

### 3.2. Backend Spring Boot

File chinh: `wildlife-backend/src/main/java/com/wildlifevn/backend/controller/ChatbotController.java`, `service/ChatbotService.java`, `client/AiServerClient.java`.

Backend expose cac endpoint:

- `POST /api/chatbot/query`
- `POST /api/chatbot/query-debug`
- `POST /api/chatbot/confirm-species`
- `POST /api/chatbot/clear-species`
- `GET /api/chatbot/rag-health?load=false|true`

Backend hien dong vai tro proxy sang AI server `http://localhost:8001` theo property `ai.server.base-url`. Neu AI server loi hoac khong phan hoi, backend tra fallback:

- status `AI_SERVER_ERROR`
- message `AI server hien chua phan hoi. Vui long thu lai sau it phut.`

Nhan xet:

- Proxy don gian, de debug va tach duoc frontend khoi FastAPI.
- `query-debug` va `rag-health` rat huu ich cho eval suite.
- Backend khong lam business logic RAG; logic nam o `wildlife-ai`.

### 3.3. AI server FastAPI

File chinh: `wildlife-ai/app/main.py`, `routers/chatbot.py`, `services/chatbot_service.py`, `services/rag_pipeline_service.py`, `services/species_service.py`, `services/image_recognition_service.py`, `models/schemas.py`.

FastAPI mount router voi prefix `/api`, trong do chatbot router co prefix `/chatbot`.

`ChatbotService` la orchestration layer:

- Quan ly session in-memory bang dict `sessionId -> ChatSessionState`.
- Luu `current_species_id`, `current_species_name`, `pending_question`, `pending_candidates`, `recent_multi_species_entities`.
- Phan tach image flow va text flow.
- Phan tich intent bang `_analyze_question` de tao `question_plan` dua vao RAG runtime.
- Goi `RagPipelineService.answer_result(...)` khi can RAG.

Luong image:

1. Neu `imageRejected=true`, tra `UNKNOWN_SPECIES`.
2. Goi `ImageRecognitionService.predict(...)` voi top K theo `VISION_TOP_K`.
3. Map class du doan ve MongoDB species bang scientific name.
4. Bo sung fallback candidates tu `top_candidates` neu chua du 6.
5. Tra `NEED_SPECIES_CONFIRM` va luu pending question neu co cau hoi kem anh.

Luong text:

- Greeting/help: tra huong dan su dung.
- Clear command: xoa active species va pending context.
- Control help: tra loi cach gui anh khac/nhan dien lai.
- Multi-species comparison: tach label sau "so sanh", resolve entity trong MongoDB, tra loi bang metadata.
- General/facet query: danh sach loai theo IUCN, ho, sinh canh, thuc an, vung phan bo, top nguy cap.
- Mentioned species: neu cau hoi co ten loai, set active species va tra loi theo loai do.
- Follow-up pronoun: neu khong co ten loai nhung session co active species, dung loai hien tai.
- Neu thieu active species, tra `NEED_SPECIES_CONTEXT`.

Nhan xet:

- Session hien dang in-memory, mat khi restart AI server va khong scale tot neu co nhieu instance.
- `SpeciesService.find_species_mentioned` scan tat ca docs va substring match; voi 570 loai van chap nhan duoc, nhung neu data tang lon nen can index/search tot hon.
- `ImageRecognitionService` lazy-load model, co the ton RAM/latency lan dau. Neu import dependency thieu, image flow bat exception va fallback ve candidates/top docs thay vi crash.

## 4. RAG runtime hien hanh

Runtime chinh: `wildlife-ai/app/rag_runtime/rag_pipeline.py`.

`RagPipelineService` import runtime bang cach:

1. Mirror settings vao `os.environ`.
2. Resolve `RAG_PROJECT_DIR`, default `app/rag_runtime`.
3. Chen runtime dir vao `sys.path`.
4. Tam thoi `chdir` vao runtime dir de import `rag_pipeline`.
5. Cache function `rag_query` o class-level de tranh import lai moi request.

Health endpoint kiem tra:

- RAG dir ton tai.
- `knowledge_base/faiss_index.bin` ton tai.
- `knowledge_base/chunks_metadata.json` ton tai.
- So chunk metadata.
- Load error va last query error.
- Config model/API key co duoc set hay khong, nhung khong expose secret.

### 4.1. Retrieval

Runtime load:

- `SentenceTransformer("keepitreal/vietnamese-sbert")`
- FAISS index `knowledge_base/faiss_index.bin`
- Metadata `knowledge_base/chunks_metadata.json`
- MongoDB collection `species_raw`
- Cerebras client neu co API key duoc cau hinh trong moi truong

Retrieval gom:

- Exact species boost: neu co `species_name`, lay truc tiep chunk dung scientific name truoc.
- Vector search FAISS cho query.
- Lexical score tren token normalized.
- Hybrid score: `alpha * semantic + (1 - alpha) * lexical`.
- `ALPHA_ENTITY` default 0.5 cho entity query.
- `ALPHA_FACET` default 0.3 cho facet/general query.
- Filter noise khi dang hoi loai cu the: chunk co `sci_name` khac target bi bo qua.
- Rerank boost theo species match, intent keyword, lexical overlap.

### 4.2. Structured direct answers

Day la diem nang cap lon so voi ban RAG cu. Runtime uu tien tra loi truc tiep tu `species_raw.raw_profile` cho cac intent co cau truc:

- name / scientific_name / taxonomy / group
- occurrence / distribution
- diet / habitat / altitude / activity_time
- conservation / threats / population_trend
- safety / legal
- source
- data_quality

Neu structured answer tao duoc cau tra loi, runtime khong can goi Cerebras. Flow debug co the la:

- `species_structured`
- `source_evidence`
- `data_quality`
- `safety_legal`

Neu khong tao duoc structured answer va co chunks, runtime moi build prompt va goi Cerebras. Neu Cerebras loi, thieu key, quota/rate-limit, hoac timeout, runtime tra fallback answer tu top chunks thay vi lam service crash.

### 4.3. Evidence va source quality

Runtime tra ve payload debug gom:

- `sources`
- `source_quality`
- `chunks`
- `evidence`
- `retrieval_warnings`
- `coverage_warnings`
- `data_warnings`
- `timings_ms`
- `fallback`
- `direct_answer`
- `generation_error`

Source quality duoc phan loai:

- `official`
- `biodiversity_db`
- `community`
- `generated`
- `unknown`

Theo data audit, source quality aggregate trong raw profiles:

- official: 2.894
- biodiversity_db: 1.071
- community: 774

Nhan xet:

- Evidence-first da co o debug/eval nhung chua co UI public rieng.
- Mot so evidence preview trong eval co the lay chunk it lien quan hoac bi cat ky tu la, vi evidence dang duoc tao tu top chunk va provenance, chua map claim-level that chat cho tung cau tra loi public.

## 5. Thu muc `RAG/` va vai tro hien tai

`RAG/` hien la workspace du lieu, build index, audit, patch va evaluation. No khong phai runtime truc tiep cua FastAPI, tru khi file/artifact duoc sync sang `wildlife-ai/app/rag_runtime`.

Nhom thu muc quan trong:

- `RAG/knowledge_base/raw`: 570 raw JSON records dang o dang text/prose cu.
- `RAG/knowledge_base/v2_all`: 570 structured profiles voi schema moi: `accepted_name`, `taxonomy`, `distribution`, `ecology`, `conservation`, `media_assets`, `provenance`, `quality`.
- `RAG/knowledge_base/mongodb`: NDJSON export cho MongoDB.
- `RAG/knowledge_base/chunks_metadata.json` va `faiss_index.bin`: artifacts RAG da dong bo voi runtime.
- `RAG/data_patches`: patch verified cho `species_raw`, gom IUCN, Vietnam Red Data, safety/legal policy, label normalization.
- `RAG/chatbot_runs`: report eval, audit, media audit, gold eval, backup truoc patch.
- `RAG/gold`: bo gold test `chatbot_gold_v1.json` va `chatbot_gold_safety_legal_v2.json`.
- `RAG/legal_sources`: registry nguon policy/legal.

Nhom script chinh:

- Build index: `build_faiss.py`, `build_hybrid_index_v2_all.py`.
- Audit data: `audit_rag_data_quality.py`, `audit_media_assets.py`, `validate_species_raw_patch.py`.
- Patch data: `apply_species_raw_patch.py`, `build_*_patch.py`, `resolve_*_patch.py`.
- Eval chatbot: `run_chatbot_question_suite.py`, `run_gold_chatbot_eval.py`.
- Media: `build_media_variants.py`, `upload_media_assets_to_azure_blob.py`, `enrich_v2_all_media_from_inaturalist.py`.
- Metadata sync: `sync_species_metadata_from_raw.py`, `normalize_species_metadata_labels.py`.

Nhan xet:

- `RAG/` da co pipeline du lieu kha day du va nhieu report theo timestamp.
- `RAG/rag_pipeline.py` bi lech voi runtime moi; can tranh sua file nay khi muc tieu la thay doi chatbot dang chay.
- Build artifacts moi nhat da duoc sync sang runtime knowledge base.

## 6. Nhung diem da cai thien so voi ban phan tich cu

So voi `RAG/CHATBOT_RAG_ANALYSIS.md` ngay 2026-05-18, trang thai hien tai da tot hon o cac diem:

- Question suite mo rong tu 20 step len 70 step trong Markdown report, 65 QA record trong JSONL.
- WARN trong suite moi khong con chu yeu la IUCN year / Vietnam Red Data year nhu ban cu, ma chuyen sang `coverage_gap` cho cac cau hoi can du lieu hanh vi/sinh thai chi tiet.
- Gold eval da tach bo `chatbot_gold_v1` va `chatbot_gold_safety_legal_v2`.
- Runtime co them cac flow structured/direct: `safety_legal`, `data_quality`, `source_evidence`.
- Safety/legal policy da duoc them vao data va duoc test rieng; ket qua safety/legal v2 dat 13 PASS / 2 WARN.
- Media variants da duoc build: tat ca 570 species trong collection co top-level thumbnail; 2.850 media assets co thumbnail va medium URL.

## 7. Rui ro va van de con lai

### 7.1. Lech phien ban runtime

Rui ro cao ve bao tri: `RAG/rag_pipeline.py` cu hon nhieu so voi `wildlife-ai/app/rag_runtime/rag_pipeline.py`. Neu sua nham `RAG/rag_pipeline.py`, chatbot chay trong FastAPI se khong doi.

Khuyen nghi: chot mot source-of-truth cho runtime, hoac them script sync co kiem tra diff truoc/sau.

### 7.2. `RagService` cu con ton tai

`wildlife-ai/app/services/rag_service.py` la luong RAG cu dung Mongo text-search + Cerebras prompt don gian. `ChatbotService` hien khoi tao `RagPipelineService`, nen `RagService` khong phai duong chay chinh.

Rui ro: dev moi co the doc nham service cu va sua sai noi.

Khuyen nghi: danh dau deprecated hoac xoa neu khong con dung.

### 7.3. Coverage gap trong du lieu

Eval moi nhat cho thay 12 WARN cua question suite deu la `coverage_gap`. Cac cau hoi bi canh bao thuong hoi ve:

- do cao phan bo
- hoat dong ngay/dem
- thuc an con non
- ke thu tu nhien
- mua sinh san
- so trung/con moi lua
- tuoi tho
- phan biet loai de nham
- dau hieu nhan biet nhanh
- khac biet duc/cai
- di cu
- tieng keu

Day la gap du lieu dung nghia, khong phai loi routing.

### 7.4. Legal/Vietnam Red Data chua du exact match

Data audit ghi:

- 503 loai `vietnam_red_not_matched_vast`.
- 570 loai `missing_vn_legal_exact_match`.
- 570 loai co guidance/legal precaution dang derived.

Chatbot da tra loi than trong va khong xem la tu van phap ly, nhung neu dung cho bao cao/ra quyet dinh bao ton thi can doi chieu van ban moi nhat va exact legal appendix.

### 7.5. Evidence chua duoc hien thi tren UI public

Debug/eval co `evidence` va `source_quality`, nhung ChatbotPage chi hien `answer/message`. Nguoi dung cuoi chua xem duoc danh sach nguon theo section.

Khuyen nghi: them panel "Nguon tham chieu" co the mo/thu, lay tu response public neu API contract duoc mo rong.

### 7.6. Session in-memory

`ChatbotService.sessions` la dict trong process. Neu AI server restart, session mat. Neu deploy nhieu instance, active species co the khong nhat quan.

Khuyen nghi: neu can production-like deployment, dua session state vao Redis/Mongo hoac de backend quan ly sticky session.

### 7.7. Port 8001 dang bi chiem trong log

`wildlife-ai/app.log` hien co loi:

```text
ERROR: [Errno 48] Address already in use
```

Day la dau hieu da co process khac chiem port khi start uvicorn. Khong phai loi RAG logic, nhung co the gay nham la AI server khong len.

## 8. Checklist kiem thu va deploy

Dung checklist nay khi chuan bi demo, deploy, hoac viet bao cao:

1. Kiem tra `GET /api/chatbot/rag-health?load=true` qua backend tra `status=ok`, `loaded=true`, `chunksMetadataCount=5000`.
2. Dam bao `RAG_PROJECT_DIR=app/rag_runtime` hoac gia tri tuong duong tro dung runtime trong `wildlife-ai`.
3. Kiem tra `wildlife-ai/app/rag_runtime/knowledge_base/faiss_index.bin` va `chunks_metadata.json` ton tai.
4. Kiem tra MongoDB co collection `species` va `species_raw`, moi collection co 570 docs neu dung bo du lieu hien tai.
5. Chay smoke test query:
   - "Xin chao, ban co the giup gi?"
   - "Cong luc song o dau?"
   - "Thong tin ve Cong luc lay tu nguon nao?"
   - "Viec buon ban Cong luc co hop phap khong?"
   - "Nhung loai nao co muc IUCN CR?"
6. Neu image recognition duoc demo, kiem tra duong dan model va class mapping trong env cua `wildlife-ai`.
7. Neu port 8001 bi chiem, dung port khac cho uvicorn hoac dung lai process cu truoc khi start AI server.

## 9. Uu tien tiep theo

1. Chot source-of-truth cho RAG runtime va lam ro `RAG/rag_pipeline.py` la legacy hay build-time script.
2. Dua evidence/source quality ra public API/UI neu muc tieu la chatbot co kha nang giai thich nguon.
3. Bo sung du lieu cho cac nhom coverage gap trong U11-U33: altitude, activity, reproduction, lifespan, identification, sexual dimorphism, migration, vocalization.
4. Tang exact match cho Vietnam Red Data / legal status Viet Nam, tach ro "khong match" voi "khong duoc liet ke".
5. Deprecate hoac xoa `RagService` cu de giam nham lan.
6. Neu se demo/on thi them huong dan xu ly port 8001 va health preflight truoc khi chay frontend.

## 10. Ket luan

Tinh nang chatbot AI/RAG hien da co kien truc hoan chinh va kha on dinh ve routing: text, image, active species session, general metadata query, source query, data quality query, multi-species comparison va safety/legal deu co luong rieng. Ket qua eval moi nhat cho thay loi nghiem trong gan nhu khong nam o API flow, ma nam o do sau va do chinh xac cua du lieu cau truc.

Neu muc tieu tiep theo la nang chat luong that cua chatbot, nen uu tien du lieu va citation UI hon la prompt tuning: them fact-level evidence vao response public, dong bo source-of-truth runtime, va lap day cac coverage gap sinh thai/hanh vi/phap ly dang duoc eval canh bao.
