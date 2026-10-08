# Security and data handling

This repository is intended for an access-controlled internal research
environment. Do not open a public issue containing credentials, source text,
model responses, trace identifiers, or assessment results.

Report a suspected vulnerability or accidental disclosure through the Red
Cross-approved private security channel and notify the repository owner. Rotate
any exposed API key immediately.

## Repository boundary

The following must remain outside Git unless they have completed an explicit
publication and data-protection review:

- `.env` and all API credentials;
- source documents and prepared source chunks;
- `source_documents/` and `prepared_data/` Stage 0 working directories;
- evidence banks derived from real source material;
- `dema_run/` and other model-generated run directories;
- exported Langfuse traces and prompt snapshots containing restricted text.

The checked-in `examples/synthetic/` data is fictional and is safe to share.
