---
name: vio-services
description: "Use when you need direct VIO service access (no UI): list models, run chat completions, create embeddings, and manage knowledge files with add/load/delete endpoints. Portable setup for any PC via .github/scripts/vio."
argument-hint: "Describe the VIO task, e.g. 'list models', 'ask UXDefaultAgent', 'upload docs and load S3P_Knowledge'."
metadata:
  author: "Zhao Jianbo"
  version: "1.0.0"
---

# VIO Services Skill

## When To Use

Use this skill for backend VIO operations without launching UI:
- List available models from `/v1/models`
- Send a chat request to a selected VIO model
- Generate embeddings for text
- Upload, load, or delete files through native VIO endpoints (`add_file`, `load_file`, `delete_file`)
- Index files or folders for RAG. Folder indexing is recursive and includes supported text/source files from sub-folders.

## Scripts Included

Location: `.github/scripts/vio/`

- `__main__.py`: Entry point for `python -m vio`
- `cli.py`: JSON CLI for all commands
- `client.py`: VIO chat/file clients
- `config.py`: Config loading with env overrides
- `rag.py`: Portable backend logic for indexing and RAG Q&A
- `vio_agent.yaml.template`: Portable local config template

## Portable Setup (Any PC)

1. Install dependencies:

```powershell
pip install -r .github\scripts\requirements.txt
```

2. Make module importable in current terminal:

```powershell
$env:PYTHONPATH = ".github\scripts"
```

3. Configure credentials (recommended via env vars):

```powershell
$env:VIO_API_TOKEN = "<openai-compatible-token>"
$env:VIO_RAG_PROJECT = "<knowledge-project-name>"
```

Optional: create `.github/scripts/vio/vio_agent.yaml` from `vio_agent.yaml.template`.

## Commands

### List models

```powershell
python -m vio models
```

### Ask a model

```powershell
python -m vio chat --question "Summarize DGC-3076"
```

By default, `chat` uses `app.default_llm_mode` (for example `UXDefaultAgent`).
You can still override it with `--model`.

### Create embedding

```powershell
python -m vio embedding --text "PowMon module overview"
```

### File API

Upload files:

```powershell
python -m vio file add --vio-model "S3P_Knowledge" knowledge_repo\PowMon.md
```

Load uploaded files:

```powershell
python -m vio file load --vio-model "S3P_Knowledge" --all
```

Delete files:

```powershell
python -m vio file delete --vio-model "S3P_Knowledge" --files PowMon.md
```

### RAG backend (no UI)

Index files into local knowledge store (and upload/load to VIO by default):

```powershell
python -m vio rag index knowledge_repo\PowMon.md
```

Index a folder recursively:

```powershell
python -m vio rag index knowledge_repo\module_specs
```

Ask with retrieval from local indexed chunks:

```powershell
python -m vio rag ask --question "What is PowMon?"
```

Local-only indexing (skip VIO file API):

```powershell
python -m vio rag index uploads\rag_trial.txt --no-upload
```

Local-only folder indexing:

```powershell
python -m vio rag index knowledge_repo\module_specs --no-upload
```

## Notes

- Output is JSON so agents can parse responses reliably.
- `rag` settings are not required for chat/models/embedding commands.
- `rag index` accepts files or folders. Folders are scanned recursively; unsupported binary/cache files are skipped.
- `rag.vio_rag_project` is used as the default knowledge project name for `file add/load/delete` and RAG upload/load.
- `VIO_RAG_PROJECT` overrides `rag.vio_rag_project`; the older `VIO_FILE_MODEL` and `rag.vio_file_model` names still work as fallbacks.
- `file add/load/delete` uses `VIO_API_TOKEN` as the token; no separate username setting is required.
- If file commands return `{"message": "Invalid input parameters."}`, verify native file API credentials first.
- Config priority order is:
  1. Environment variables
  2. `.github/scripts/vio/vio_agent.yaml`
  3. `config/config.yaml`
- Keep secrets in env vars, not committed files.

## Quick Health Check

```powershell
$env:PYTHONPATH = ".github\scripts"
python -m vio models
python -m vio chat --question "Reply with exactly OK"
python -m vio rag index uploads\rag_trial.txt --no-upload
python -m vio rag ask --question "What is the UniqueKey in rag_trial.txt?"
```
