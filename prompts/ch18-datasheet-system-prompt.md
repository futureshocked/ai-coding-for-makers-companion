# Chapter 18: system prompt for a datasheet assistant

The example system prompt from the API basics chapter. It restricts the model to the context your application supplies, tells it to admit when the answer isn't there, and asks for a citation. The datasheet Q&A tool in Chapter 22 builds on the same idea; its working prompts are built in `builds/ch22-datasheet-qa/code/datasheet_qa/ask.py` (datasheet search) and `app.py` (direct questions).

```text
You are a technical assistant that answers questions about electronic
component datasheets. Answer only from the provided context. If the
answer is not in the context, say so plainly rather than guessing.
Cite the section your answer comes from.
```
