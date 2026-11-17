"""FastAPI application for Datasheet Q&A Tool."""

import json
import time
import traceback
import unicodedata

from fastapi import FastAPI, Form, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel

from . import llm
from . import config
from . import ingest
from . import ask
from .errors import (
    AppError,
    PdfIngestionError,
    MissingApiKeyError,
    LlmApiError,
    ChromaError,
    error_response,
)

# Initialize logging
from . import logging_config

# Cached embedding model instance for health checks
_embedding_model = None

logging_config.setup_logging()
logger = logging_config.get_logger("app")

app = FastAPI(title="Datasheet Q&A")


# ---------------------------------------------------------------------------
# Exception handlers — return JSON with user-friendly messages
# ---------------------------------------------------------------------------

@app.exception_handler(MissingApiKeyError)
async def handle_missing_api_key(request, exc: MissingApiKeyError):
    logger.error("Missing API key", path=request.url.path)
    return JSONResponse(content=error_response(exc), status_code=500)


@app.exception_handler(LlmApiError)
async def handle_llm_error(request, exc: LlmApiError):
    logger.error("LLM API error", path=request.url.path, detail=exc.detail)
    return JSONResponse(content=error_response(exc), status_code=502)


@app.exception_handler(PdfIngestionError)
async def handle_pdf_error(request, exc: PdfIngestionError):
    logger.error("PDF ingestion error", path=request.url.path, detail=exc.detail)
    return JSONResponse(content=error_response(exc), status_code=400)


@app.exception_handler(ChromaError)
async def handle_chroma_error(request, exc: ChromaError):
    logger.error("Chroma database error", path=request.url.path, detail=exc.detail)
    return JSONResponse(content=error_response(exc), status_code=500)


@app.exception_handler(AppError)
async def handle_app_error(request, exc: AppError):
    logger.error("Application error", path=request.url.path, detail=exc.detail)
    return JSONResponse(content=error_response(exc), status_code=500)


@app.exception_handler(Exception)
async def handle_unexpected_error(request, exc: Exception):
    logger.error("Unexpected error", path=request.url.path, error=str(exc), traceback=traceback.format_exc())
    return JSONResponse(
        content={"status": "error", "message": "An unexpected error occurred. Please try again."},
        status_code=500,
    )


class PingRequest(BaseModel):
    text: str


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main frontend page."""
    with open("templates/index.html") as f:
        return f.read()


@app.post("/api/ping")
async def ping(text: str = Form(...)):
    """Return a blocking JSON response from Claude."""
    logger.info("Ping request received", text_length=len(text))
    response = llm.ask(text)
    return {"response": response}


def _safe_stream_llm(prompt: str, system: str | None = None):
    """Stream LLM response, yielding SSE error frame on failure."""
    try:
        for frame in llm.ask_stream(prompt, system=system):
            if frame["type"] == "text":
                yield f"event: text\ndata: {frame['content']}\n\n"
            elif frame["type"] == "usage":
                # ping endpoint doesn't show usage, just skip
                pass
    except LlmApiError as e:
        logger.error("LLM stream error", detail=e.detail)
        yield f"event: error\ndata: {json.dumps({'message': e.user_message})}\n\n"
    except Exception as e:
        logger.error("Unexpected stream error", error=str(e))
        yield f"event: error\ndata: {json.dumps({'message': 'An unexpected error occurred. Please try again.'})}\n\n"


@app.post("/api/ping/stream")
async def ping_stream(text: str = Form(...)):
    """Stream a response from Claude as raw text."""
    logger.info("Ping stream request received", text_length=len(text))
    return StreamingResponse(
        _safe_stream_llm(text),
        media_type="text/event-stream",
    )


@app.get("/api/documents")
async def list_documents():
    """Return a list of all ingested document sources with their page ranges."""
    logger.info("List documents request received")
    try:
        client = ingest.get_chroma_client()
    except Exception as e:
        logger.error("Failed to connect to Chroma", error=str(e))
        raise ChromaError(
            user_message="Unable to access the document store.",
            detail=str(e),
        ) from e

    try:
        collection = client.get_collection(name="datasheets")
    except Exception as e:
        logger.warning("No documents found (empty or unavailable collection)", error=str(e))
        return {"documents": []}

    all_data = collection.get(include=["metadatas"])
    seen = {}
    for meta in all_data["metadatas"]:
        src = meta["source"]
        page = meta["page"]
        if src not in seen:
            seen[src] = set()
        seen[src].add(page)

    docs = [{"source": src, "pages": sorted(pg)} for src, pg in seen.items()]
    logger.info("Documents listed", document_count=len(docs))
    return {"documents": docs}


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """Upload a PDF file to the uploads directory."""
    filename = getattr(file, "filename", None) or "unknown"
    logger.info("Upload request received", filename=filename)

    # Validate file type
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        logger.warning("Upload rejected: invalid file type", filename=filename)
        return {"status": "error", "message": "Only PDF files are accepted."}

    # Validate content type if available
    if file.content_type and file.content_type not in (
        "application/pdf",
        "application/octet-stream",
    ):
        logger.warning("Upload rejected: invalid content type", content_type=file.content_type)
        return {"status": "error", "message": "Only PDF files are accepted."}

    # Create uploads directory
    uploads_dir = config.UPLOAD_DIR

    # Sanitize filename
    original_name = unicodedata.normalize("NFKD", file.filename).encode("ascii", "ignore").decode("ascii")
    name_no_ext = original_name.rsplit(".", 1)[0] if "." in original_name else original_name
    ext = ".pdf"

    # Generate unique filename to avoid overwriting
    timestamp = int(time.time())
    dest_name = f"{timestamp}_{name_no_ext}{ext}"
    dest_path = uploads_dir / dest_name

    # If somehow collision, add counter
    counter = 1
    while dest_path.exists():
        dest_name = f"{timestamp}_{name_no_ext}_{counter}{ext}"
        dest_path = uploads_dir / dest_name
        counter += 1

    # Read file content and check size
    content = await file.read()
    if len(content) > config.MAX_UPLOAD_SIZE:
        max_mb = config.MAX_UPLOAD_SIZE / (1024 * 1024)
        logger.warning("Upload rejected: file too large", size_bytes=len(content), max_bytes=config.MAX_UPLOAD_SIZE)
        return {"status": "error", "message": f"File size exceeds maximum allowed size of {int(max_mb)} MB."}

    # Write file
    try:
        with open(dest_path, "wb") as f:
            f.write(content)
    except OSError as e:
        logger.error("Failed to save uploaded file", error=str(e))
        return {"status": "error", "message": f"Failed to save file: {str(e)}"}

    # Run ingestion pipeline
    logger.info("Running ingestion pipeline", dest_path=str(dest_path))
    try:
        messages = ingest.ingest_pdf(str(dest_path))
    except PdfIngestionError as e:
        logger.error("Ingestion failed", error=str(e))
        return {"status": "error", "message": e.user_message}
    except Exception as e:
        logger.error("Unexpected ingestion error", error=str(e), traceback=traceback.format_exc())
        return {"status": "error", "message": "An unexpected error occurred during ingestion. Please try again."}

    logger.info("Upload complete", dest_filename=dest_name)
    return JSONResponse(content={
        "status": "success",
        "message": f"File '{dest_name}' uploaded successfully.",
        "filename": dest_name,
        "messages": messages,
    })


def _rag_stream_with_sources(question: str, document_filter: str = ""):
    """RAG query that yields SSE-style frames.

    First yields a JSON frame with source metadata, then streams text chunks,
    then yields a final usage frame with tokens and cost.
    Errors during retrieval are yielded as SSE error events.
    """
    model_key = config.LLM_MODEL_KEY
    try:
        logger.info("RAG query started", question_length=len(question), filter=document_filter or None, model=model_key)
        chunks = ask.retrieve_chunks(question, document_filter)
        prompt = ask.build_prompt(question, chunks)

        # Yield sources as first SSE event
        sources_json = json.dumps(chunks, ensure_ascii=False)
        yield f"event: sources\ndata: {sources_json}\n\n"

        logger.info("RAG query streaming response")
        for frame in llm.ask_stream(prompt, model_key=model_key):
            if frame["type"] == "text":
                yield f"event: text\ndata: {frame['content']}\n\n"
            elif frame["type"] == "usage":
                cost = config.compute_cost_usd(model_key, frame["input_tokens"], frame["output_tokens"])
                usage_data = {
                    "input_tokens": frame["input_tokens"],
                    "output_tokens": frame["output_tokens"],
                    "model": frame["model"],
                    "model_key": frame["model_key"],
                    "cost_usd": round(cost, 6),
                }
                yield f"event: usage\ndata: {json.dumps(usage_data)}\n\n"

    except LlmApiError as e:
        logger.error("LLM API error during RAG", detail=e.detail)
        yield f"event: error\ndata: {json.dumps({'message': e.user_message})}\n\n"
    except ChromaError as e:
        logger.error("Chroma error during RAG", detail=e.detail)
        yield f"event: error\ndata: {json.dumps({'message': e.user_message})}\n\n"
    except Exception as e:
        logger.error("Unexpected RAG error", error=str(e))
        yield f"event: error\ndata: {json.dumps({'message': 'An unexpected error occurred. Please try again.'})}\n\n"


DIRECT_SYSTEM_PROMPT = (
    "You are a technical advisor specializing on electronic components "
    "and datasheets. Your role is to provide clear, accurate, and detailed "
    "technical information to assist users.\n"
    "Guidelines:\n"
    "- Use proper markdown formatting with headings, paragraphs, bullet "
    "lists, and tables where appropriate.\n"
    "- Ensure proper spacing between sentences and paragraphs.\n"
    "- Use bold or italic for emphasis where helpful.\n"
    "- If you don't know the exact answer, state what you do know and "
    "suggest the user verify with official manufacturer datasheets.\n"
    "- Be concise but thorough."
)


def _direct_stream(question: str):
    """Direct LLM stream bypassing retrieved content."""
    model_key = config.LLM_MODEL_KEY
    logger.info("Direct query started", question_length=len(question), model=model_key)
    try:
        prompt = f"Question: {question}"
        for frame in llm.ask_stream(prompt, system=DIRECT_SYSTEM_PROMPT, model_key=model_key):
            if frame["type"] == "text":
                yield f"event: text\ndata: {frame['content']}\n\n"
            elif frame["type"] == "usage":
                cost = config.compute_cost_usd(model_key, frame["input_tokens"], frame["output_tokens"])
                usage_data = {
                    "input_tokens": frame["input_tokens"],
                    "output_tokens": frame["output_tokens"],
                    "model": frame["model"],
                    "model_key": frame["model_key"],
                    "cost_usd": round(cost, 6),
                }
                yield f"event: usage\ndata: {json.dumps(usage_data)}\n\n"
    except LlmApiError as e:
        logger.error("LLM API error during direct query", detail=e.detail)
        yield f"event: error\ndata: {json.dumps({'message': e.user_message})}\n\n"
    except Exception as e:
        logger.error("Unexpected direct stream error", error=str(e))
        yield f"event: error\ndata: {json.dumps({'message': 'An unexpected error occurred. Please try again.'})}\n\n"


@app.post("/api/query")
async def query(text: str = Form(...), document_filter: str = Form(default=""), mode: str = Form(default="rag")):
    """Stream a response: RAG mode (with sources) or direct LLM mode."""
    logger.debug("Query request received", mode=mode, question_length=len(text))

    # Validate question length
    if len(text) > config.MAX_QUESTION_LENGTH:
        logger.warning("Query rejected: question too long", length=len(text), max=config.MAX_QUESTION_LENGTH)
        return JSONResponse(
            content={"status": "error", "message": f"Question exceeds maximum length of {config.MAX_QUESTION_LENGTH} characters."},
            status_code=400,
        )
    if mode == "direct":
        return StreamingResponse(
            _direct_stream(text),
            media_type="text/event-stream",
        )
    return StreamingResponse(
        _rag_stream_with_sources(text, document_filter),
        media_type="text/event-stream",
    )


def _get_embedding_model():
    """Lazy-load embedding model and cache the singleton."""
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    return _embedding_model


@app.get("/api/health")
async def health():
    """Health check reporting API key, Chroma, and embedding model status."""

    checks = {}

    # 1. API key present
    api_key_ok = bool(config.ANTHROPIC_API_KEY)
    checks["api_key_present"] = api_key_ok

    # 2. Chroma reachable
    try:
        client = ingest.get_chroma_client()
        client.list_collections()
        checks["chroma_reachable"] = True
    except Exception as e:
        checks["chroma_reachable"] = False
        checks["chroma_error"] = str(e)

    # 3. Embedding model loaded
    try:
        model = _get_embedding_model()
        # Run a quick encode to verify the model actually loaded
        model.encode(["health check"])
        checks["embedding_model_loaded"] = True
    except Exception as e:
        checks["embedding_model_loaded"] = False
        checks["embedding_error"] = str(e)

    overall = "healthy" if all([checks["chroma_reachable"], checks["embedding_model_loaded"]]) else "degraded"
    if not api_key_ok:
        overall = "degraded"

    status_code = 200 if overall == "healthy" else 503

    return JSONResponse(content={"status": overall, "checks": checks}, status_code=status_code)


# ---------------------------------------------------------------------------
# Config / model switching endpoints
# ---------------------------------------------------------------------------

class ModelConfigRequest(BaseModel):
    model_key: str


@app.get("/api/config")
async def get_config():
    """Return available models, current selection, and pricing info."""
    logger.info("Config request received")
    return {
        "model_key": config.LLM_MODEL_KEY,
        "model_id": config.LLM_MODEL,
        "available_models": config.LLM_MODELS,
        "pricing": {k: {"input_per_1k": v["input_per_1k"], "output_per_1k": v["output_per_1k"]} for k, v in config.PRICING.items()},
    }


@app.post("/api/config/model")
async def set_model(req: ModelConfigRequest):
    """Switch the active model and persist the selection."""
    model_key = req.model_key
    logger.info("Model switch request", requested_key=model_key)

    if model_key not in config.LLM_MODELS:
        logger.warning("Model switch rejected: unknown model key", key=model_key)
        return JSONResponse(
            content={"status": "error", "message": f"Unknown model key: {model_key}"},
            status_code=400,
        )

    try:
        config.save_model_config(model_key)
        # Reload module-level state
        config.LLM_MODEL_KEY = model_key
        config.LLM_MODEL = config.LLM_MODELS[model_key]
    except Exception as e:
        logger.error("Model switch failed", key=model_key, error=str(e))
        return JSONResponse(
            content={"status": "error", "message": f"Failed to save model config: {str(e)}"},
            status_code=500,
        )

    logger.info("Model switched successfully", key=model_key, model_id=config.LLM_MODEL)
    return {
        "status": "success",
        "model_key": model_key,
        "model_id": config.LLM_MODEL,
    }