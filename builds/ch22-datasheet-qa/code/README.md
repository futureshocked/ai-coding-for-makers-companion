# Datasheet Q&A Tool

A local desktop application that lets you upload PDF datasheets for electronic components and ask natural-language questions about them.

## Features

- Upload PDF datasheets and build a searchable library
- Ask questions about component specifications, configuration guidance, and selection advice
- Answers are grounded in your datasheets with source citations (filename + page number)
- Runs entirely locally — no cloud storage, no telemetry
- LLM calls use Anthropic Claude API

## Installation

1. Clone this repository and change into this `code/` folder
2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Set your Anthropic API key:
   ```bash
   export ANTHROPIC_API_KEY="your-api-key-here"
   ```

## Usage

### Web Interface

```bash
uvicorn datasheet_qa.app:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000` in your browser.

### CLI (S2)

```bash
# Ingest a PDF
python -m datasheet_qa.ingest path/to/datasheet.pdf

# Ask a question
python -m datasheet_qa.ask "What is the maximum supply voltage?"
```

## Configuration

| Variable | Description | Default |
|---|---|---|
| `ANTHROPIC_API_KEY` | Anthropic API key (required) | — |
| `LLM_MODEL` | Claude model name | `claude-sonnet-4-6` |
| `CHUNK_SIZE` | Text chunk size | `900` |
| `CHUNK_OVERLAP` | Chunk overlap | `150` |
| `RETRIEVAL_K` | Number of chunks to retrieve | `8` |

## Data Storage

All data is stored in a platform-specific application data directory:
- **Linux:** `~/.local/share/datasheet-qa/`
- **macOS:** `~/Library/Application Support/datasheet-qa/`
- **Windows:** `%LOCALAPPDATA%\datasheet-qa\`

## License

MIT. See the LICENSE file at the root of the companion repository.