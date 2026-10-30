"""Configuration helpers for VIO service scripts."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import yaml


_DEFAULT_BASE_URL = "https://vio.automotive-wan.com:446"
_CONFIG_PATH = Path(__file__).resolve().parents[3] / "config" / "config.yaml"
_LOCAL_VIO_CONFIG = Path(__file__).resolve().parent / "vio_agent.yaml"


@dataclass(frozen=True)
class VioConfig:
    base_url: str
    api_token: str
    headers: Dict[str, str]
    embedding_model: str
    default_llm_mode: str
    vio_rag_project: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    uploads_dir: str
    metadata_file: str
    vio_uploaded_files_track: str


def _read_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
        return data if isinstance(data, dict) else {}


def load_vio_config() -> VioConfig:
    """
    Load config in this order:
    1) Environment variables (highest priority)
    2) .github/scripts/vio/vio_agent.yaml
    3) config/config.yaml (project-level)
    """
    local_all = _read_yaml(_LOCAL_VIO_CONFIG)
    project_all = _read_yaml(_CONFIG_PATH)

    local_cfg = local_all.get("vio", {}) if isinstance(local_all.get("vio"), dict) else {}
    project_cfg = project_all.get("vio", {}) if isinstance(project_all.get("vio"), dict) else {}
    local_app = local_all.get("app", {}) if isinstance(local_all.get("app"), dict) else {}
    project_app = project_all.get("app", {}) if isinstance(project_all.get("app"), dict) else {}
    local_rag = local_all.get("rag", {}) if isinstance(local_all.get("rag"), dict) else {}
    project_rag = project_all.get("rag", {}) if isinstance(project_all.get("rag"), dict) else {}

    def pick(key: str, default: str = "") -> str:
        env_key = f"VIO_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val:
            return env_val
        if key in local_cfg and local_cfg[key] not in (None, ""):
            return str(local_cfg[key])
        if key in project_cfg and project_cfg[key] not in (None, ""):
            return str(project_cfg[key])
        return default

    base_url = pick("base_url", _DEFAULT_BASE_URL)
    api_token = pick("api_token", "")

    local_headers = local_cfg.get("headers", {}) if isinstance(local_cfg.get("headers"), dict) else {}
    project_headers = project_cfg.get("headers", {}) if isinstance(project_cfg.get("headers"), dict) else {}
    headers = {**project_headers, **local_headers}

    embedding_model = pick("embedding_model", "amazon.titan-embed-text-v2:0")
    default_llm_mode = (
        os.environ.get("VIO_DEFAULT_LLM_MODE")
        or local_app.get("default_llm_mode")
        or project_app.get("default_llm_mode")
        or "UXDefaultAgent"
    )
    vio_rag_project = (
        os.environ.get("VIO_RAG_PROJECT")
        or os.environ.get("VIO_FILE_MODEL")
        or local_rag.get("vio_rag_project")
        or project_rag.get("vio_rag_project")
        or local_rag.get("vio_file_model")
        or project_rag.get("vio_file_model")
        or "S3P_Knowledge"
    )
    chunk_size = int(local_rag.get("chunk_size", project_rag.get("chunk_size", 1000)))
    chunk_overlap = int(local_rag.get("chunk_overlap", project_rag.get("chunk_overlap", 200)))
    top_k = int(local_rag.get("top_k", project_rag.get("top_k", 5)))
    uploads_dir = str(local_rag.get("uploads_dir", project_rag.get("uploads_dir", "uploads")))
    metadata_file = str(local_rag.get("metadata_file", project_rag.get("metadata_file", "uploads/knowledge_base.json")))
    vio_uploaded_files_track = str(
        local_rag.get(
            "vio_uploaded_files_track",
            project_rag.get("vio_uploaded_files_track", "uploads/vio_uploaded_files.json"),
        )
    )

    return VioConfig(
        base_url=base_url,
        api_token=api_token,
        headers=headers,
        embedding_model=embedding_model,
        default_llm_mode=str(default_llm_mode),
        vio_rag_project=str(vio_rag_project),
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        top_k=top_k,
        uploads_dir=uploads_dir,
        metadata_file=metadata_file,
        vio_uploaded_files_track=vio_uploaded_files_track,
    )
