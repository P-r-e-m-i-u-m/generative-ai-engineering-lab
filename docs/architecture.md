# Architecture

The repo is dependency-light on purpose.

## Core

`src/lab.ts` implements:

- keyword retrieval
- RAG answer generation
- prompt evaluation
- safety scanning
- agent planning

## Upgrade Path

- Replace keyword retrieval with embeddings.
- Add model provider adapters.
- Add vector storage.
- Add traces.
- Add eval reports.
- Add browser UI.
