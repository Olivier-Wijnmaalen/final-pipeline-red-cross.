# Configuration

A configuration template is a safe example of the settings an application
expects. This repository uses `.env.example`: it contains variable names and
non-secret placeholders, but no credentials. Copy it to the ignored `.env`
file and fill in values locally:

```powershell
Copy-Item .env.example .env
```

Never put real keys in `.env.example`, source code, Git history, screenshots,
issues, or chat messages.

## Model provider

Set `AI_PROVIDER` to one of:

- `azure`: requires `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, and
  `AZURE_OPENAI_API_KEY`;
- `openai`: requires `OPENAI_API_KEY` and `OPENAI_MODEL`; `OPENAI_BASE_URL`
  normally remains `https://api.openai.com/v1`.

The selected deployment must support the OpenAI Responses API and the output
sizes used by this pipeline.

## Prompts and tracing

Production execution always uses the reviewed text files in `prompts/`. Stage
1 inserts the command-line country and one Markdown chunk into `{{Country}}`
and `{{input_text}}`. Stage 2 inserts the combined evidence-bank JSON into
`{{databank}}`. The application checks the prompt hashes and variables against
`prompts/manifest.json` before making a model call.

Langfuse is not required to run the pipeline. To enable optional tracing,
install its separate dependency set:

```powershell
python -m pip install -r requirements-tracing.txt
```

Then set `LANGFUSE_TRACING_ENABLED=true` and fill in the three Langfuse values
in the local `.env`. Do this only when the relevant project permits assessment
metadata and trace records to be sent to that Langfuse project. Keep it `false`
for local-only execution. See `prompts/README.md` for the controlled prompt
update procedure.

## Command-line configuration

`main.py --help` documents runtime arguments. The most important are:

- `--chunks`: prepared Markdown source directory;
- `--base-bank`: reviewed base evidence bank;
- `--output`: private run-artifact directory;
- `--country`: country substituted into Stage 1;
- `--stage2-max-output-tokens`: Stage 2 response ceiling.

Runtime arguments override the default paths in `dema/config.py`. Secrets are
read only from the process environment or local `.env` file.
