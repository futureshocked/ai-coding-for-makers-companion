"""CLI entry point for PDF ingestion."""

import argparse
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import fitz  # pymupdf
import pymupdf4llm
import chromadb
from chromadb.config import Settings
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

from datasheet_qa import config
from datasheet_qa.errors import PdfIngestionError

# Initialize logging
from datasheet_qa import logging_config

logging_config.setup_logging()
logger = logging_config.get_logger("ingest")


def get_chroma_client() -> Any:
    """Return an authenticated Chroma PersistentClient using a file-backed database."""
    logger.debug("Opening Chroma PersistentClient", path=str(config.DATA_DIR / "chroma_db"))
    db_path = config.DATA_DIR / "chroma_db"
    return chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False),
    )


def extract_markdown(pdf_path: str) -> list[tuple[str, int]]:
    """Extract markdown text from each page of a PDF using pymupdf4llm.

    Returns list of (markdown_text, page_number) tuples.
    Uses page_chunks=True to get per-page results with metadata.

    Raises:
        PdfIngestionError: If the PDF cannot be opened or extracted.
    """
    logger.debug("Opening PDF", pdf_path=pdf_path)
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("Failed to open PDF", pdf_path=pdf_path, error=str(e))
        raise PdfIngestionError(
            user_message=f"The PDF file cannot be opened. It may be corrupted: {e}",
            detail=str(e),
        ) from e

    try:
        page_chunks: list[dict] = pymupdf4llm.to_markdown(doc, page_chunks=True, show_progress=False)  # type: ignore[assignment]
    except Exception as e:
        logger.error("Failed to extract markdown from PDF", pdf_path=pdf_path, error=str(e))
        raise PdfIngestionError(
            user_message="Failed to extract text from the PDF. The file may be corrupted or contain unsupported content.",
            detail=str(e),
        ) from e
    finally:
        doc.close()

    logger.debug("PDF closed", pdf_path=pdf_path)

    pages = []
    for chunk in page_chunks:
        page_num = chunk["metadata"]["page"] + 1  # 0-based to 1-based
        md_text = chunk["text"]
        if md_text.strip():
            pages.append((md_text, page_num))
    logger.info("Markdown extraction complete", page_count=len(pages))
    return pages


def chunk_markdown(pages: list[tuple[str, int]]) -> list[dict]:
    """Split markdown pages into chunks using a two-stage strategy.

    1. MarkdownHeaderTextSplitter splits on headers (h1-h6), preserving
       the header path as metadata.
    2. RecursiveCharacterTextSplitter splits oversized header sections
       into manageable chunks.

    Returns list of dicts with keys: text, page, chunk_index, heading
    """
    # Define header hierarchy for MarkdownHeaderTextSplitter
    headers_to_split_on = [
        ("#", "h1"),
        ("##", "h2"),
        ("###", "h3"),
        ("####", "h4"),
        ("#####", "h5"),
        ("######", "h6"),
    ]

    md_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=config.CHUNK_SIZE,
        chunk_overlap=config.CHUNK_OVERLAP,
    )

    chunks = []
    chunk_index = 0

    for md_text, page_num in pages:
        # Stage 1: split on headers
        header_chunks = md_splitter.split_text(md_text)

        for hc in header_chunks:
            # Build a human-readable heading path from metadata
            heading_parts = []
            for level in ["h1", "h2", "h3", "h4", "h5", "h6"]:
                if level in hc.metadata and hc.metadata[level]:
                    heading_parts.append(hc.metadata[level])
            heading = " > ".join(heading_parts) if heading_parts else ""

            # Stage 2: split oversized sections by character count
            sub_chunks = text_splitter.split_text(hc.page_content)

            for piece in sub_chunks:
                if piece.strip():
                    chunks.append({
                        "text": piece,
                        "page": page_num,
                        "chunk_index": chunk_index,
                        "heading": heading,
                    })
                    chunk_index += 1

    return chunks


def embed_and_store(
    client: Any,
    source: str,
    chunks: list[dict],
) -> None:
    """Embed chunk texts and store them in ChromaDB."""
    collection_name = "datasheets"

    # Get or create collection
    try:
        collection = client.get_collection(name=collection_name)
    except Exception:
        collection = client.create_collection(name=collection_name)

    # Build document IDs
    source_basename = Path(source).stem.replace(" ", "_").lower()
    ids = [f"{source_basename}_p{c['page']}_c{c['chunk_index']}" for c in chunks]

    # Build metadata list
    metadatas = [
        {
            "source": source_basename,
            "page": c["page"],
            "chunk_index": c["chunk_index"],
            "heading": c.get("heading", ""),
        }
        for c in chunks
    ]

    # Build documents list
    documents = [c["text"] for c in chunks]

    # Delete existing entries for this source to support idempotent re-ingestion
    try:
        existing = collection.get(where={"source": source_basename})
        if existing["ids"]:
            collection.delete(ids=existing["ids"])
    except Exception:
        pass

    # Embed chunks in batch
    embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
    embeddings = embedding_model.encode(documents, show_progress_bar=True).tolist()

    # Insert into Chroma
    for i in range(len(ids)):
        collection.add(
            ids=[ids[i]],
            embeddings=[embeddings[i]],
            metadatas=[metadatas[i]],
            documents=[documents[i]],
        )

    # Close the embedding model to free memory
    del embedding_model


def ingest_pdf(pdf_path: str, progress_callback=None) -> list[str]:
    """Full ingestion pipeline for a single PDF.

    Args:
        pdf_path: Path to the PDF file.
        progress_callback: Optional callable that receives progress strings.

    Returns:
        List of progress messages.
    """
    messages: list[str] = []
    start_time = time.monotonic()

    def _log(msg: str) -> None:
        messages.append(msg)
        if progress_callback:
            progress_callback(msg)
        else:
            print(msg)

    logger.info("Ingestion started", pdf_path=pdf_path)

    if not Path(pdf_path).is_file():
        error_msg = f"Error: File not found: {pdf_path}"
        _log(error_msg)
        logger.error("Ingestion failed: file not found", pdf_path=pdf_path)
        if not progress_callback:
            sys.exit(1)
        return messages

    if not pdf_path.lower().endswith(".pdf"):
        error_msg = f"Error: Not a PDF file: {pdf_path}"
        _log(error_msg)
        logger.error("Ingestion failed: not a PDF", pdf_path=pdf_path)
        if not progress_callback:
            sys.exit(1)
        return messages

    _log(f"Extracting markdown from: {Path(pdf_path).name}")
    logger.info("Extracting markdown", pdf_path=Path(pdf_path).name)
    pages = extract_markdown(pdf_path)
    if not pages:
        _log("No text extracted from PDF.")
        logger.warning("No text extracted", pdf_path=pdf_path)
        if not progress_callback:
            sys.exit(1)
        return messages

    _log(f"  Extracted markdown from {len(pages)} pages.")
    logger.info("Pages extracted", page_count=len(pages), pdf_path=Path(pdf_path).name)

    _log("Chunking markdown...")
    logger.info("Chunking markdown")
    chunks = chunk_markdown(pages)
    _log(f"  Created {len(chunks)} chunks.")
    logger.info("Chunking complete", chunk_count=len(chunks))

    _log("Loading embedding model...")
    logger.info("Loading embedding model", model=config.EMBEDDING_MODEL)
    source = Path(pdf_path).name
    client = get_chroma_client()

    _log("Embedding and storing chunks...")
    logger.info("Embedding and storing chunks")
    embed_and_store(client, source, chunks)

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    _log(f"Done. Ingested '{source}' into vector store.")
    logger.info("Ingestion complete", source=source, chunk_count=len(chunks), latency_ms=elapsed_ms)
    return messages


def copy_pdf_to_upload(pdf_path: str) -> Path:
    """Copy the PDF to the upload directory, returning the destination path."""
    dest = config.UPLOAD_DIR / Path(pdf_path).name
    src = Path(pdf_path).resolve()
    if src == dest.resolve():
        print(f"File already in uploads directory, skipping copy.")
        return dest
    shutil.copy2(pdf_path, dest)
    return dest


def main():
    """Ingest a PDF datasheet into the vector store."""
    parser = argparse.ArgumentParser(description="Ingest a PDF datasheet")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    args = parser.parse_args()

    # Copy to upload directory
    dest = copy_pdf_to_upload(args.pdf_path)
    print(f"Copied {args.pdf_path} → {dest}")

    # Run full ingestion
    ingest_pdf(str(dest))


if __name__ == "__main__":
    main()