# Moodle RAG Assistant — Backend Phase 2

Local development backend for Moodle 5.3 using FastAPI, ChromaDB, and Ollama.

## Features
- Index PDF, DOCX, PPTX, TXT, and Markdown.
- Extract PDF pages and PowerPoint slide numbers.
- Chunk text, generate Ollama embeddings, and persist vectors in ChromaDB.
- Retrieve by course ID, visibility, and owner ID.
- Generate answers using qwen3:1.7b with source markers.
- Require `X-RAG-API-Key` on document and chat endpoints.

Scanned PDF OCR, asynchronous indexing, Moodle PHP integration, and conversation history are not included yet.

## 1. Prepare Ollama
Install and run Ollama, then:
```powershell
ollama pull nomic-embed-text
ollama pull qwen3:1.7b
ollama list
```

## 2. Install backend
Extract this folder outside Moodle's public web directory, for example `C:\laragon\www\ragassistant-backend`.

```powershell
cd C:\laragon\www\ragassistant-backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env`. Generate a key:
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```
Put the generated value in `RAG_API_KEY` in `.env`. Keep the key private.

## 3. Run
```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open `http://127.0.0.1:8000/health`, `/ready`, or `/docs`.

Request activity is written to the console at `DEBUG` level. Each request logs its
method, path, client address, response status, and duration. Headers and request
bodies are not logged. Set `LOG_LEVEL=INFO` in `.env` to hide these debug entries.

Configure the reverse proxy in front of this service with a request body limit
at or below the backend upload limit (for example, Nginx:
`client_max_body_size 20m;`). Starlette buffers the request body before the
application can apply its own upload-size check.

## 4. Index a test document
In PowerShell, replace the API key and use a real local file:
```powershell
$headers = @{ "X-RAG-API-Key" = "00" }
$form = @{
  file = Get-Item ".\sample.pdf"
  document_id = "demo-doc-001"
  course_id = "2"
  owner_id = "5"
  visibility = "course"
}
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/documents/index" -Method Post -Headers $headers -Form $form
```
`course_id` and `owner_id` here are test values. Use real Moodle IDs when integrating.

## 5. Ask a question
```powershell
$headers = @{
  "X-RAG-API-Key" = "YOUR_SECRET_HERE"
  "Content-Type" = "application/json"
}
$body = @{
  question = "Summarise the main ideas in this document."
  course_id = 2
  user_id = 5
  include_course_documents = $true
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/chat" -Method Post -Headers $headers -Body $body
```

## 6. Delete vectors for a document
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/documents/demo-doc-001?course_id=2" -Method Delete -Headers $headers
```
This removes indexed vectors, not the original Moodle file.

## Security warning
The shared API key authenticates the Moodle server to FastAPI; it does not independently verify the Moodle user's identity. Until Moodle integration is complete, a caller with the API key can submit arbitrary course/user IDs. This is a local prototype only. Before enabling it for users, the PHP plugin must check Moodle enrolment/capabilities, keep the API key server-side, and send requests only to this trusted local service. Course-wide visibility must only be granted by authorized Moodle users. Add stronger signed authorization, rate limits, and cross-course isolation tests before deployment.

## Known limitations
- Scanned PDFs need OCR.
- Tables and complex layouts may extract imperfectly.
- Chunking uses character windows.
- Indexing runs synchronously.
- Similarity retrieval has no calibrated confidence threshold yet.


## Phase 4 conversation context

The chat endpoint accepts an optional `history` array containing up to 12 `{role, content}` messages. Moodle can pass recent turns so follow-up questions can resolve references such as “explain that more”. Prior assistant messages are not treated as authoritative evidence; the current answer must still be grounded in retrieved course passages.


## Modular prompt system (integrated)

The backend now keeps shared prompt components in `app/prompts/core/` and one task prompt per tool in `app/prompts/tools/`. `app/prompt_registry.py` is the source of truth for supported tool IDs, slash commands, descriptions, and retrieval-mode labels.

### Routing behavior
- `/exam Create 10 questions` selects `exam_generation`.
- `/notes ...` selects revision-note generation.
- `/summarize ...`, `/flashcards ...`, `/explain ...`, `/quiz ...`, `/studyguide ...`, and `/extract ...` select their corresponding task prompts.
- Plain-language requests use lightweight rule-based routing.
- Requests not matched by a rule use normal course Q&A.
- No second LLM classifier call is made, so routing does not add a separate Ollama inference.

### Chat API
The existing `POST /api/v1/chat` endpoint accepts an optional `tool_id`:
```json
{
  "question": "Create 10 exam questions about neural networks",
  "course_id": 2,
  "user_id": 5,
  "include_course_documents": true,
  "tool_id": "exam_generation"
}
```
Omit `tool_id` to let the backend route the request automatically. The slash command may also be included at the start of `question`.

A `GET /api/v1/chat/tools` endpoint returns tool IDs, slash commands, labels, and descriptions for a UI autocomplete menu. It uses the same API-key dependency as the chat endpoint.

### Important current limitation
The current ChromaDB metadata stores course ID, owner, visibility, filename, page, and retrieval-enabled state, but it does not classify documents as lecture slides versus past exam papers. Exam generation currently uses the same course-scoped retrieval path as other tools. The prompt has a past-paper-reference slot, but it remains empty until document-type metadata and a separate authorized retrieval path are implemented. Do not assume past papers are being retrieved separately yet.

### Prompt maintenance
Prompt files are read once per process per file and cached in memory. Restart FastAPI after editing prompt files. Keep shared core files short and put task-specific requirements only in the selected tool prompt.
