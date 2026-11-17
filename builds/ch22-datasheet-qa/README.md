# Chapters 17–22: datasheet Q&A tool

Upload PDF datasheets for electronic components and ask questions about them in plain English. The tool converts each PDF to Markdown (keeping tables intact), splits it into chunks, stores them in a local vector database, retrieves the most relevant chunks for each question and asks Claude to answer from them, citing the source file and page.

Part III of the book (Chapters 17–21) covers the concepts: when to use an LLM inside an application, API basics, retrieval-augmented generation, preparing documents, and cost, latency and failure. Chapter 22 is the complete build.

## Read these first

| File | What it is |
|---|---|
| [`code/documents/specification.md`](code/documents/specification.md) | The specification handed to the coding agent, staged as S1 to S4 |
| [`prompts.md`](prompts.md) | The build prompts from Chapter 22 |
| [`datasheets.md`](datasheets.md) | Links to the datasheets used in the chapter |

## Run it

You need Python 3.10 or newer and an Anthropic API key ([install guide](../../setup/01-install-tools.md), [API keys](../../setup/02-api-keys-and-secrets.md)).

```bash
cd code
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Create a file named `.env` in the `code/` folder holding your key:

```
ANTHROPIC_API_KEY=your_key_here
```

Then start the web interface:

```bash
uvicorn datasheet_qa.app:app --port 8000
```

Open <http://localhost:8000>, upload a datasheet and ask a question. The first run downloads a small embedding model, so it takes a minute longer.

You can also work from the command line:

```bash
python -m datasheet_qa.ingest path/to/datasheet.pdf
python -m datasheet_qa.ask "What is the maximum supply voltage?"
python -m datasheet_qa.inspect_store --help
```

`inspect_store` is the debugging tool from the chapter. It shows what was stored for each document and the text of any chunk, which is how the chapter traced a wrong answer to a table that had been split badly.

## Notes

1. The models are listed in `code/datasheet_qa/config.py` (`LLM_MODELS`), along with the per-token prices used by the cost tracker. Model names and prices change; update both if a model has been retired.
2. Uploaded datasheets, the vector database and logs are stored in your user data folder (see the Data Storage section of [`code/README.md`](code/README.md)), not in the project folder.
3. The tool runs on your computer and is meant for one user. Don't expose it to the internet as it is.
