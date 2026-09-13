# Pinecone RAG

The prototype retrieves reviewed fashion and cultural guidance before Nebius creates a family outfit plan. Pinecone is a contextual source; inventory, ownership, availability, events, and budget remain authoritative application data.

## Data flow

1. `scripts/index_guidance.py` loads the reviewed records in `data/seed/guidance.json`.
2. Pinecone's `llama-text-embed-v2` integrated model embeds each `chunk_text` as a passage.
3. The LangGraph context tool builds a query from selected event types and dress codes.
4. Pinecone embeds the query and returns the six most relevant passages with scores.
5. The passages and source IDs are included in the Nebius planning context.
6. The Streamlit planning-details panel exposes the query, provider, scores, sources, and text.

The index is `wardrobe-guidance` and the namespace is `reviewed-guidance-v1`. Ingestion is idempotent because every reviewed passage has a stable `_id`.

## Demo resilience

If Pinecone is unconfigured or a search fails, the tool uses the local keyword retriever. The planning-details panel labels this fallback; it never presents local retrieval as Pinecone retrieval.

## Adding larger documents

PDFs and other sources should be extracted, divided into focused passages, reviewed, and assigned stable source and page metadata before ingestion. The original files remain outside Pinecone; Pinecone stores searchable passage text, embeddings, and metadata.
