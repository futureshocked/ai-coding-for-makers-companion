# Datasheet Q&A Tool — Specification

## 1. Task

A local desktop application that lets a single user upload PDF datasheets for electronic components and ask natural-language questions about them. The application extracts text from each PDF, indexes it for semantic search, retrieves relevant passages in response to a question, and uses an LLM to synthesise an answer grounded in those passages. Every answer cites the source datasheet and page number so the user can verify the response against the original document.

Representative questions the tool must handle:
- Parametric lookup ("What is the maximum supply voltage for component XYZ?")
- Configuration guidance ("How should I configure the SPI interface for this sensor?")
- Judgement-based selection ("Which GPIO pin is most appropriate for PWM motor control?")

## 2. Context

**Runtime environment.** Cross-platform desktop tool — must run on Windows, macOS, and Linux without modification. Pure Python, no Docker, no external servers, no GPU. CPU-only inference. Single user, single machine, accessed via a browser at `localhost:8000`.

**Data.** Input is high-quality text-based PDF datasheets (no OCR needed — assume embedded text). Content is heavy on tables, parametric data, register descriptions, timing diagrams, and pinout information. Each datasheet is typically 20–200 pages. The user uploads datasheets over time and builds up a personal library; the tool must support both single-document and multi-document querying.

**Persistence.** All user data — uploaded PDFs, the vector store, configuration — lives in a single application directory under the user's home folder, located per-OS via `platformdirs`. No cloud storage, no telemetry.

**Network.** Outbound network access is required only for calls to the Anthropic API. Embeddings run locally and offline.

## 3. Constraints

**Technology decisions (locked):**

- Language: Python 3.11+
- PDF parsing: `pymupdf` (naive text extraction, page-aware)
- Chunking: `langchain-text-splitters` `RecursiveCharacterTextSplitter`, 900 characters, 150 character overlap
- Embeddings: `sentence-transformers` with `all-MiniLM-L6-v2` (local, CPU)
- Vector store: `chromadb` `PersistentClient` (embedded, file-backed)
- LLM: Anthropic Claude via the `anthropic` Python SDK. API key read from environment variable `ANTHROPIC_API_KEY`.
- HTTP layer: `fastapi` + `uvicorn`
- Frontend: HTML + HTMX served by FastAPI. No build step, no Node, no React.
- Data directory: resolved via `platformdirs.user_data_dir("datasheet-qa")`

**Must not:**

- Require Docker or any containerisation
- Require a GPU
- Use cloud-hosted vector databases or external indexing services
- Use OCR libraries (datasheets are assumed text-based)
- Implement multi-user features (no authentication, no user accounts, no concurrency for multiple humans)
- Use OpenAI, ChatGPT, or any LLM provider other than Anthropic
- Send any data anywhere except to the Anthropic API during query handling

**Scope limits:**

- No PDF generation, annotation, or modification — read-only ingestion
- No editing of indexed content after ingestion (re-ingestion replaces it)
- No chat history persistence beyond the current session (initial scope)
- No fine-tuning, no agent loops, no tool use by the LLM — single-shot RAG only

## 4. Output

A working Python application with the following deliverables:

- A project repository with a clear folder layout, `requirements.txt` (pinned versions), and a `README.md` documenting installation, configuration, and usage
- A configuration mechanism: environment variables for the API key, a config file or constants module for everything else (chunk size, model names, retrieval `k`, data directory)
- Two command-line entry points (`ingest.py`, `ask.py`) usable independently of the web layer
- A FastAPI application (`app.py` or equivalent) exposing upload, query, and document-listing endpoints
- An HTMX frontend with three functions: upload a PDF, ask a question (optionally scoped to a specific document), view the answer with cited sources (filename + page number) and the retrieved chunks
- Each answer must include the source chunks used to generate it, displayed in the UI alongside the answer
- A `data/` directory structure (created at runtime) holding uploaded PDFs and the Chroma database

---

# Implementation plan

## S1 — Application base and LLM integration

Establish the skeleton before any RAG work. The goal is a working end-to-end loop that calls Claude and returns text, with nothing else in the way.

Deliverables:

- Project structure: `datasheet_qa/` package, `tests/`, `requirements.txt`, `README.md`, `.env.example`
- Configuration module: reads `ANTHROPIC_API_KEY` from environment; defines constants for model name (`claude-sonnet-4-5`), data directory path (via `platformdirs`), and creates the directory on first run
- An `llm.py` module wrapping the Anthropic SDK with a single function `ask(prompt: str) -> str`
- A FastAPI app with one endpoint `POST /api/ping` that takes a string, sends it to Claude, returns the response
- A minimal HTMX page at `/` with a text input and submit button that hits `/api/ping`
- A `tests/test_llm.py` that confirms the API call works (skip if `ANTHROPIC_API_KEY` is absent)

Exit criteria: user can type "hello" in the browser, see Claude's response, and run `pytest` cleanly.

## S2 — RAG implementation

Add ingestion and retrieval. Build the CLI tools first so retrieval can be inspected without the UI in the way.

Deliverables:

- `ingest.py` CLI: takes a PDF path, extracts text with PyMuPDF (preserving page numbers), chunks with `RecursiveCharacterTextSplitter` (900/150), embeds with `all-MiniLM-L6-v2`, stores in Chroma with metadata `{source, page, chunk_index}`
- `ask.py` CLI: takes a question, embeds it, retrieves top 8 chunks from Chroma, builds a prompt with the chunks (each marked `[source: filename, page N]`), calls Claude, prints the answer plus the cited sources
- The prompt instructs Claude to answer only from the provided chunks, to cite sources inline, and to say "not in the provided datasheet" when the information is absent
- FastAPI endpoints: `POST /api/upload` (saves PDF, runs ingestion), `POST /api/query` (runs retrieval + LLM call, returns answer + sources), `GET /api/documents` (lists ingested PDFs)
- HTMX frontend: upload form, question box with optional document filter, answer panel showing the response and the source chunks (filename, page, chunk text)

Exit criteria: user can upload a datasheet, ask a question about it, and get an answer with verifiable citations.

## S3 — PDF-to-Markdown upgrade

Evaluate naive extraction against real datasheets, then upgrade to markdown if (when) tables turn out garbled.

Deliverables:

- Swap the extractor (currently PDF to plain text) for `pymupdf4llm`, which produces markdown with tables preserved as markdown tables
- Switch the chunker to `MarkdownHeaderTextSplitter` so chunks carry their section heading as metadata, with `RecursiveCharacterTextSplitter` as a secondary splitter for oversized sections
- Re-ingest the test datasheets, re-run the test questions, document the improvement
- Update the prompt to surface section headings to the LLM alongside source/page

Exit criteria: documented before/after results showing improvement on table-heavy queries, with the markdown pipeline as the new default.

## S4 — Resilience, logging, cost review

Harden the application for daily use.

Deliverables:

- Structured logging (Python `logging`, JSON-friendly format) written to a rotating file in the data directory; log levels for API calls, ingestion progress, errors
- Error handling on every external boundary: malformed PDFs, missing API key, Anthropic API errors (rate limits, network failures, 5xx responses), Chroma read/write failures. Each surfaces a clear message in the UI rather than a stack trace.
- Input validation: file type check on upload (PDF only), file size limit, question length limit
- A `/api/health` endpoint reporting embedding model loaded, Chroma reachable, API key present
- Cost review: show the input/output tokens per query in the UI, and compute cost per query at current anthropic pricing. In addition, add the ability for the user to switch between Sonnet and Haiku models on demand. If possible, fetch pricing information from Anthropic via its API. If not, add variables local and I will provide the relevant prices.
- A short `OPERATIONS.md` covering log location, common errors, how to reset the index, how to back up the data directory

Exit criteria: the tool runs unattended without producing unhandled exceptions across a session of mixed valid and invalid inputs, and costs per query are known and recorded.

---

Want me to adjust scope on any step before you hand this to the agent? Two areas worth a second look: whether S3's evaluation should be a formal test suite (with expected answers) or just a manual spot-check, and whether S4's cost review justifies adding Haiku routing as a feature or just documenting the option.