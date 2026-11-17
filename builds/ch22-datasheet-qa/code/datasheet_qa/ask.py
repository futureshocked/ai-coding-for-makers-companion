"""CLI entry point for asking questions."""

import argparse
import json
import sys
import time
from typing import Generator

from sentence_transformers import SentenceTransformer

from datasheet_qa import config
from datasheet_qa.ingest import get_chroma_client
from datasheet_qa.errors import ChromaError, LlmApiError

# Initialize logging
from datasheet_qa import logging_config

logging_config.setup_logging()
logger = logging_config.get_logger("ask")


def retrieve_chunks(question: str, document_filter: str = "") -> list[dict]:
    """Embed the question and retrieve top K chunks from Chroma.

    Args:
        question: The user's question.
        document_filter: Optional source name to filter results to a specific document.

    Returns:
        List of dicts with keys: source, page, text, heading
    """
    logger.info("Retrieval started", question_length=len(question), filter=document_filter or None)
    start_time = time.monotonic()

    try:
        client = get_chroma_client()
    except Exception as e:
        logger.error("Failed to connect to Chroma", error=str(e))
        raise ChromaError(
            user_message="Unable to access the datasheet store. Please try re-ingesting your documents.",
            detail=str(e),
        ) from e

    try:
        collection = client.get_collection(name="datasheets")
    except Exception:
        logger.error("No datasheets found")
        raise ChromaError(
            user_message="No datasheets found. Please upload PDFs using ingest.py first.",
        )

    try:
        embedding_model = SentenceTransformer(config.EMBEDDING_MODEL)
        question_embedding = embedding_model.encode(question).tolist()
        del embedding_model
    except Exception as e:
        logger.error("Failed to encode question", error=str(e))
        raise ChromaError(
            user_message="Failed to process the question. Please try again.",
            detail=str(e),
        ) from e

    query_params: dict = {
        "query_embeddings": [question_embedding],
        "n_results": config.RETRIEVAL_K,
    }
    if document_filter:
        query_params["where"] = {"source": document_filter}

    try:
        results = collection.query(**query_params)
    except Exception as e:
        logger.error("Chroma query failed", error=str(e))
        raise ChromaError(
            user_message="Failed to search the datasheet store. Please try again.",
            detail=str(e),
        ) from e

    chunks = []
    if results["ids"] and results["ids"][0]:
        for i in range(len(results["ids"][0])):
            chunks.append({
                "source": results["metadatas"][0][i]["source"],
                "page": results["metadatas"][0][i]["page"],
                "heading": results["metadatas"][0][i].get("heading", ""),
                "text": results["documents"][0][i],
            })

    elapsed_ms = int((time.monotonic() - start_time) * 1000)
    logger.info("Retrieval complete", chunk_count=len(chunks), latency_ms=elapsed_ms)
    return chunks


def build_direct_prompt(question: str) -> str:
    """Build a prompt for direct LLM technical advisor mode."""
    system_prompt = (
        "You are a technical advisor specializing on electronic components "
        "and datasheets. Provide accurate, detailed technical information to "
        "assist the user. If you don't know something, use your training "
        "knowledge or suggest the user consult an online search. Keep answers "
        "clear and well-structured."
    )
    return f"{system_prompt}\n\nQuestion: {question}"


def build_prompt(question: str, chunks: list[dict]) -> str:
    """Build a RAG prompt with retrieved chunks and the user question."""
    instruction = (
        "You are a technical assistant that answers questions about electronic "
        "component datasheets. Follow these rules:\n"
        "1. Answer ONLY from the provided context chunks below.\n"
        "2. For every fact or figure you mention, cite the source inline "
        "using the format [source: filename, page N] as shown in the context.\n"
        "3. If the answer cannot be found in the provided context, say exactly: "
        "\"The requested information is not in the provided datasheet.\"\n\n"
        "Context:\n"
    )

    context_parts = []
    for chunk in chunks:
        heading_str = f", section: \"{chunk['heading']}\"" if chunk.get("heading") else ""
        context_parts.append(
            f"[source: {chunk['source']}, page {chunk['page']}{heading_str}]\n"
            f"{chunk['text']}"
        )

    context_block = "\n\n---\n\n".join(context_parts)

    prompt = f"{instruction}{context_block}\n\n---\n\nQuestion: {question}"

    return prompt


def ask_with_rag(question: str, document_filter: str = "") -> tuple[Generator[str, None, None], list[dict]]:
    """Ask a question using RAG and stream the response.

    Args:
        question: The user's question.
        document_filter: Optional source name to filter results to a specific document.

    Returns:
        Tuple of (streaming text generator, list of source chunks).

    Raises:
        ChromaError: If the datasheet store cannot be accessed.
        LlmApiError: If the LLM API call fails.
    """
    from datasheet_qa import llm

    try:
        chunks = retrieve_chunks(question, document_filter)
    except ChromaError:
        raise
    except Exception as e:
        logger.error("Unexpected error during retrieval", error=str(e))
        raise ChromaError(
            user_message="An unexpected error occurred while retrieving context. Please try again.",
            detail=str(e),
        ) from e

    prompt = build_prompt(question, chunks)

    try:
        return llm.ask_stream(prompt), chunks
    except LlmApiError:
        raise
    except Exception as e:
        logger.error("Unexpected error in LLM call", error=str(e))
        raise LlmApiError(
            user_message="An unexpected error occurred while generating the answer. Please try again.",
            detail=str(e),
        ) from e


def main():
    """Ask a question about ingested datasheets."""
    parser = argparse.ArgumentParser(description="Ask a question about datasheets")
    parser.add_argument("question", help="The question to ask")
    args = parser.parse_args()

    question = args.question

    print(f"Retrieving relevant chunks for: {question}")

    stream, chunks = ask_with_rag(question)

    print(f"Retrieved {len(chunks)} chunks:")
    for i, chunk in enumerate(chunks, 1):
        print(f"  [{i}] {chunk['source']} (page {chunk['page']})")

    print("\n" + "=" * 60)
    print("ANSWER:")
    print("=" * 60)

    for text in stream:
        print(text, end="", flush=True)

    print()


if __name__ == "__main__":
    main()