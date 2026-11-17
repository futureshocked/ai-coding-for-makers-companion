"""CLI tool for inspecting the ChromaDB vector store."""

import argparse
import sys
from pathlib import Path

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer

from datasheet_qa import config


def get_collection():
    """Get the datasheets collection from ChromaDB."""
    db_path = config.DATA_DIR / "chroma_db"
    client = chromadb.PersistentClient(
        path=str(db_path),
        settings=Settings(anonymized_telemetry=False),
    )
    try:
        return client.get_collection(name="datasheets")
    except Exception:
        print("Error: Vector store is empty. No documents have been ingested yet.")
        sys.exit(1)


def mode_list(args):
    """List all ingested documents with statistics."""
    col = get_collection()
    all_data = col.get(include=["metadatas"])

    if not all_data["ids"]:
        print("No documents in the vector store.")
        return

    # Aggregate by source
    sources = {}
    for meta in all_data["metadatas"]:
        src = meta["source"]
        if src not in sources:
            sources[src] = {"chunks": 0, "pages": set()}
        sources[src]["chunks"] += 1
        sources[src]["pages"].add(meta["page"])

    # Print table
    header = f"{'Source':<35} {'Chunks':>6} {'Pages':>6}"
    print(header)
    print("─" * len(header))

    total_chunks = 0
    for src in sorted(sources.keys()):
        info = sources[src]
        page_count = len(info["pages"])
        total_chunks += info["chunks"]
        # Truncate long source names
        display_name = src[:32] + "..." if len(src) > 35 else src
        print(f"{display_name:<35} {info['chunks']:>6} {page_count:>6}")

    print("─" * len(header))
    print(f"Total: {len(sources)} document(s), {total_chunks} chunk(s)")


def mode_chunks(args):
    """Show all chunks for a specific document."""
    col = get_collection()
    source = args.source

    # Check if source exists
    existing = col.get(where={"source": source})
    if not existing["ids"]:
        print(f"Error: Source '{source}' not found in vector store.")
        print("Use 'list' to see available sources.")
        sys.exit(1)

    # Get all chunks for this source, sorted by chunk_index
    all_data = col.get(where={"source": source}, include=["metadatas", "documents"])
    # Sort by chunk_index
    indexed = list(zip(all_data["documents"], all_data["metadatas"]))
    indexed.sort(key=lambda x: x[1]["chunk_index"])

    truncate = args.truncate
    print(f"Source: {source}")
    print(f"Total chunks: {len(indexed)}")
    print("─" * 60)

    for i, (doc, meta) in enumerate(indexed):
        page = meta["page"]
        chunk_idx = meta["chunk_index"]
        if len(doc) > truncate:
            display = doc[:truncate] + "..."
        else:
            display = doc
        print(f"\nChunk {chunk_idx} (page {page}):")
        print(display)


def mode_chunk(args):
    """Show a single specific chunk."""
    col = get_collection()
    source = args.source
    chunk_index = args.index

    # Build the expected ID
    source_clean = source.replace(" ", "_").lower()
    # Try to find the chunk
    result = col.get(
        where={"$and": [{"source": source}, {"chunk_index": chunk_index}]},
        include=["metadatas", "documents"],
    )

    if not result["ids"]:
        print(f"Error: Chunk {chunk_index} not found for source '{source}'.")
        sys.exit(1)

    doc = result["documents"][0]
    meta = result["metadatas"][0]

    print(f"Source: {source}")
    print(f"Chunk: {meta['chunk_index']}, Page: {meta['page']}")
    print("─" * 60)
    print(doc)


def mode_search(args):
    """Semantic search across all chunks."""
    col = get_collection()
    query = args.query
    top_n = args.top

    # Check collection has data
    count = col.count()
    if count == 0:
        print("Error: Vector store is empty.")
        sys.exit(1)

    # Embed and search
    model = SentenceTransformer(config.EMBEDDING_MODEL)
    query_embedding = model.encode(query).tolist()

    results = col.query(
        query_embeddings=[query_embedding],
        n_results=top_n,
        include=["metadatas", "documents", "distances"],
    )

    if not results["ids"] or not results["ids"][0]:
        print("No results found.")
        return

    print(f"Query: \"{query}\"")
    print(f"Top {top_n} results:")
    print("─" * 60)

    for i in range(len(results["ids"][0])):
        meta = results["metadatas"][0][i]
        doc = results["documents"][0][i]
        distance = results["distances"][0][i]
        # Convert distance to similarity score (lower distance = higher similarity)
        score = 1.0 / (1.0 + distance)

        print(f"\nScore: {score:.3f} | Source: {meta['source']}, Page: {meta['page']}, Chunk: {meta['chunk_index']}")
        # Show first 300 chars
        preview = doc[:300] + "..." if len(doc) > 300 else doc
        print(preview)

    del model


def mode_delete(args):
    """Delete all chunks for a specific document."""
    col = get_collection()
    source = args.source

    # Check if source exists
    existing = col.get(where={"source": source})
    if not existing["ids"]:
        print(f"Error: Source '{source}' not found in vector store.")
        sys.exit(1)

    count = len(existing["ids"])
    col.delete(where={"source": source})
    print(f"Deleted {count} chunk(s) for source '{source}'.")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect the ChromaDB vector store for Datasheet Q&A"
    )
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")

    # list
    p_list = subparsers.add_parser("list", help="List all documents with statistics")
    p_list.set_defaults(func=mode_list)

    # chunks
    p_chunks = subparsers.add_parser("chunks", help="Show all chunks for a document")
    p_chunks.add_argument("source", help="Source name (use 'list' to see available)")
    p_chunks.add_argument("--truncate", type=int, default=200, help="Max chars per chunk (default: 200)")
    p_chunks.set_defaults(func=mode_chunks)

    # chunk
    p_chunk = subparsers.add_parser("chunk", help="Show a single specific chunk")
    p_chunk.add_argument("source", help="Source name")
    p_chunk.add_argument("index", type=int, help="Chunk index")
    p_chunk.set_defaults(func=mode_chunk)

    # search
    p_search = subparsers.add_parser("search", help="Semantic search across all chunks")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--top", type=int, default=5, help="Number of results (default: 5)")
    p_search.set_defaults(func=mode_search)

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete all chunks for a document")
    p_delete.add_argument("source", help="Source name to delete")
    p_delete.set_defaults(func=mode_delete)

    args = parser.parse_args()

    if not args.mode:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()