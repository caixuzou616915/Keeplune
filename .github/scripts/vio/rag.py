"""Portable RAG service for VIO scripts (no UI dependencies)."""

from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

from .client import VioChatClient, VioKnowledgeClient
from .config import VioConfig, load_vio_config


_SUPPORTED_TEXT_SUFFIXES = {
    ".c",
    ".cfg",
    ".cmd",
    ".cpp",
    ".cs",
    ".css",
    ".csv",
    ".h",
    ".hpp",
    ".html",
    ".ini",
    ".java",
    ".js",
    ".json",
    ".md",
    ".plantuml",
    ".ps1",
    ".puml",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".ts",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}


@dataclass
class VioRAGService:
    """Backend-style RAG service for file indexing and QA."""

    cfg: VioConfig

    def __post_init__(self) -> None:
        self.chat = VioChatClient(self.cfg)
        self.files = VioKnowledgeClient(self.cfg)
        self.model_name: Optional[str] = None
        self.default_model: Optional[str] = None

        self.chunk_size = self.cfg.chunk_size
        self.chunk_overlap = self.cfg.chunk_overlap
        self.top_k = self.cfg.top_k
        self.vio_rag_project = self.cfg.vio_rag_project

        self.metadata_path = Path(self.cfg.metadata_file)
        self.vio_track_path = Path(self.cfg.vio_uploaded_files_track)
        self.knowledge_base: Dict[str, Dict[str, List]] = {}
        self.uploaded_files: List[str] = []
        self.show_progress = True

        self._load_knowledge_base()

    @classmethod
    def from_config(cls) -> "VioRAGService":
        return cls(load_vio_config())

    def connect(self, model_name: Optional[str] = None) -> Dict[str, object]:
        target = model_name or self.cfg.default_llm_mode
        available = self.chat.list_models()

        selected = None
        if target in available:
            selected = target
        else:
            lower_target = target.lower()
            for m in available:
                if lower_target in m.lower():
                    selected = m
                    break

        if not selected:
            return {
                "success": False,
                "message": f"Model '{target}' not found",
                "error": f"Available models (first 10): {available[:10]}",
            }

        self.model_name = target
        self.default_model = selected
        return {
            "success": True,
            "message": f"Connected to model: {selected}",
            "model_name": selected,
        }

    def _chunk_text(self, text: str) -> List[str]:
        chunks: List[str] = []
        start = 0
        size = len(text)

        while start < size:
            end = start + self.chunk_size
            chunk = text[start:end]

            if end < size:
                last_period = chunk.rfind(".")
                last_newline = chunk.rfind("\n\n")
                break_point = max(last_period, last_newline)
                if break_point > self.chunk_size * 0.5:
                    chunk = text[start:start + break_point + 1]
                    end = start + break_point + 1

            chunk = chunk.strip()
            if chunk:
                chunks.append(chunk)
            start = max(end - self.chunk_overlap, end)

        return chunks

    def _progress(self, message: str) -> None:
        if self.show_progress:
            print(message, file=sys.stderr, flush=True)

    def _embed_document(self, filename: str, content: str) -> Dict[str, object]:
        chunks = self._chunk_text(content)
        if not chunks:
            return {"success": False, "error": "No valid content chunks"}

        embeddings = []
        total = len(chunks)
        start_time = time.monotonic()
        for idx, chunk in enumerate(chunks, start=1):
            embeddings.append(self.chat.embedding(chunk))
            elapsed = time.monotonic() - start_time
            self._progress(f"    embedding chunk {idx}/{total} ({elapsed:.1f}s elapsed)")
        self.knowledge_base[filename] = {
            "chunks": chunks,
            "embeddings": embeddings,
            "content": content,
        }
        return {"success": True, "chunks": len(chunks)}

    def _load_knowledge_base(self) -> None:
        if not self.metadata_path.exists():
            self.knowledge_base = {}
            self.uploaded_files = []
            return
        try:
            with self.metadata_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
            self.knowledge_base = data.get("knowledge_base", {})
            self.uploaded_files = data.get("uploaded_files", [])
        except Exception:
            self.knowledge_base = {}
            self.uploaded_files = []

    def _save_knowledge_base(self) -> None:
        self.metadata_path.parent.mkdir(parents=True, exist_ok=True)
        data = {"knowledge_base": self.knowledge_base, "uploaded_files": self.uploaded_files}
        with self.metadata_path.open("w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)

    def _load_vio_track(self) -> Dict[str, List[str]]:
        if not self.vio_track_path.exists():
            return {}
        try:
            with self.vio_track_path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:
            return {}

    def _save_vio_track(self, tracking: Dict[str, List[str]]) -> None:
        self.vio_track_path.parent.mkdir(parents=True, exist_ok=True)
        with self.vio_track_path.open("w", encoding="utf-8") as handle:
            json.dump(tracking, handle, indent=2)

    def _get_vio_uploaded_files(self) -> List[str]:
        tracking = self._load_vio_track()
        return tracking.get(self.vio_rag_project, [])

    def _set_vio_uploaded_files(self, files: List[str]) -> None:
        tracking = self._load_vio_track()
        tracking[self.vio_rag_project] = sorted(list(dict.fromkeys(files)))
        self._save_vio_track(tracking)

    def _is_supported_text_file(self, path: Path) -> bool:
        if any(part in {"__pycache__", ".git"} for part in path.parts):
            return False
        return path.suffix.lower() in _SUPPORTED_TEXT_SUFFIXES

    def _expand_paths(self, paths: List[str]) -> Tuple[List[Path], List[str]]:
        files: List[Path] = []
        errors: List[str] = []

        for input_path in paths:
            path = Path(input_path)
            if not path.exists():
                errors.append(f"Not found: {input_path}")
                continue
            if path.is_file():
                if self._is_supported_text_file(path):
                    files.append(path)
                else:
                    errors.append(f"Unsupported file type skipped: {input_path}")
                continue
            if path.is_dir():
                folder_files = sorted(p for p in path.rglob("*") if p.is_file() and self._is_supported_text_file(p))
                if folder_files:
                    files.extend(folder_files)
                else:
                    errors.append(f"Empty folder skipped: {input_path}")
                continue
            errors.append(f"Unsupported path skipped: {input_path}")

        unique_files = list(dict.fromkeys(files))
        return unique_files, errors

    def index_files(self, paths: List[str], upload_to_vio: bool = True) -> Dict[str, object]:
        if not self.default_model:
            return {"success": False, "message": "Connect to a model first"}

        indexed: List[str] = []
        files, errors = self._expand_paths(paths)
        total_files = len(files)

        for file_num, p in enumerate(files, start=1):
            try:
                self._progress(f"[{file_num}/{total_files}] Indexing {p.name} ...")
                content = p.read_text(encoding="utf-8")
                if not content.strip():
                    errors.append(f"Empty file skipped: {p.name}")
                    self._progress(f"[{file_num}/{total_files}] {p.name}: skipped (empty)")
                    continue

                embed_result = self._embed_document(p.name, content)
                if not embed_result.get("success"):
                    errors.append(f"Embed failed for {p.name}: {embed_result.get('error')}")
                    self._progress(f"[{file_num}/{total_files}] {p.name}: embed failed")
                    continue
                self._progress(f"[{file_num}/{total_files}] {p.name}: done ({embed_result.get('chunks')} chunks)")

                if p.name not in self.uploaded_files:
                    self.uploaded_files.append(p.name)

                if upload_to_vio:
                    add_resp = self.files.add_files([str(p)], self.vio_rag_project)
                    if add_resp.get("error"):
                        errors.append(f"VIO add_file failed for {p.name}: {add_resp.get('error')}")
                    else:
                        tracked = self._get_vio_uploaded_files()
                        if p.name not in tracked:
                            tracked.append(p.name)
                        self._set_vio_uploaded_files(tracked)

                indexed.append(p.name)
            except Exception as exc:
                errors.append(f"{p.name}: {exc}")

        if upload_to_vio:
            tracked = self._get_vio_uploaded_files()
            if tracked:
                try:
                    self.files.load_files(vio_model=self.vio_rag_project, files=tracked, all_files=False)
                except Exception as exc:
                    errors.append(f"VIO load_file failed: {exc}")

        self._save_knowledge_base()

        return {
            "success": len(indexed) > 0,
            "indexed_files": indexed,
            "errors": errors,
            "message": f"Indexed {len(indexed)} file(s)",
        }

    def _retrieve(self, question: str, top_k: Optional[int] = None) -> List[Tuple[str, str, float]]:
        if not self.knowledge_base:
            return []

        k = top_k or self.top_k
        question_embedding = np.array(self.chat.embedding(question), dtype=float)

        results: List[Tuple[str, str, float]] = []
        for filename, data in self.knowledge_base.items():
            chunks = data.get("chunks", [])
            embeddings = data.get("embeddings", [])
            for chunk, emb in zip(chunks, embeddings):
                emb_vec = np.array(emb, dtype=float)
                denom = np.linalg.norm(question_embedding) * np.linalg.norm(emb_vec)
                sim = float(np.dot(question_embedding, emb_vec) / denom) if denom else 0.0
                results.append((filename, chunk, sim))

        results.sort(key=lambda x: x[2], reverse=True)
        return results[:k]

    def ask(self, question: str, use_rag: bool = True) -> Dict[str, object]:
        if not self.default_model:
            return {"success": False, "message": "Connect to a model first"}
        if not question.strip():
            return {"success": False, "message": "Question is empty"}

        context = ""
        sources: List[Dict[str, object]] = []

        if use_rag and self.knowledge_base:
            chunks = self._retrieve(question)
            if chunks:
                lines = ["Here is relevant information from the knowledge base:\n"]
                for idx, (fname, chunk, score) in enumerate(chunks, 1):
                    lines.append(f"\n[Source {idx}: {fname} (relevance: {score:.2f})]")
                    lines.append(chunk)
                    lines.append("---")
                    sources.append({"filename": fname, "relevance": round(score, 4)})
                context = "\n".join(lines)

        final_question = (
            f"{context}\n\nBased on the above information, answer:\n\n{question}"
            if context else question
        )
        system_prompt = (
            "You are an expert assistant with access to a knowledge base. "
            "Use provided context when relevant. If missing, say so briefly."
        )

        answer = self.chat.ask(final_question, model=self.default_model, system_prompt=system_prompt)
        return {"success": True, "answer": answer, "sources": sources}
