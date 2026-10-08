# Web security and data handling

- Uploads are limited to PDF, DOCX, and Markdown and 25 MB.
- Filenames and generated run IDs are validated before path construction.
- Browser code receives no API credentials or raw model requests.
- Runs and uploads are marked internal and excluded from Git.
- Local runs persist until an authorized operator deletes the relevant
  `runs/<run-id>/` directory. Production retention and secure deletion periods
  must be approved and implemented in the selected durable storage service.
- Uploaded Markdown is displayed only as escaped text through React. Uploaded
  HTML is not accepted by the web interface.
- Source links are rendered only as links; operators must review their
  sensitivity before sharing a result.
- Logs should contain run state and errors, not full documents or secrets.

Organizational approval is required for hosting region, retention period,
identity provider, baseline-bank ownership, Langfuse tracing, model provider,
and access to generated assessment artifacts.
