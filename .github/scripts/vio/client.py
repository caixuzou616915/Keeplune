"""VIO clients for OpenAI-compatible and native file APIs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import openai
import requests

from .config import VioConfig


@dataclass
class VioChatClient:
    cfg: VioConfig

    def __post_init__(self) -> None:
        if not self.cfg.api_token:
            raise ValueError("Missing VIO API token. Set VIO_API_TOKEN or configure vio.api_token.")
        self.default_model = self.cfg.default_llm_mode
        self.client = openai.OpenAI(
            api_key=self.cfg.api_token,
            base_url=self.cfg.base_url,
            default_headers=self.cfg.headers,
        )

    def list_models(self) -> List[str]:
        models = self.client.models.list()
        return [model.id for model in models.data]

    def ask(self, question: str, model: Optional[str] = None, system_prompt: Optional[str] = None) -> str:
        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": question})

        target_model = model or self.default_model
        response = self.client.chat.completions.create(model=target_model, messages=messages)
        return response.choices[0].message.content or ""

    def embedding(self, text: str, model: Optional[str] = None) -> List[float]:
        embedding_model = model or self.cfg.embedding_model
        response = self.client.embeddings.create(model=embedding_model, input=[text])
        return response.data[0].embedding


@dataclass
class VioKnowledgeClient:
    cfg: VioConfig

    def __post_init__(self) -> None:
        self.session = requests.Session()

    def _payload(self, req_type: str, vio_model: str, files: Optional[List[str]] = None, all_files: bool = False) -> Dict[str, Any]:
        return {
            "username": "",
            "token": self.cfg.api_token,
            "type": req_type,
            "vio_model": vio_model,
            "files": files or [],
            "all": all_files,
        }

    def _request(self, endpoint: str, payload: Dict[str, Any], files: Optional[List[Any]] = None) -> Dict[str, Any]:
        if not payload.get("token"):
            raise ValueError("Missing VIO API token. Set VIO_API_TOKEN.")

        url = f"{self.cfg.base_url}/{endpoint}"
        if files:
            resp = self.session.post(url, data=payload, files=files, timeout=120)
        else:
            resp = self.session.post(url, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            if data.get("error"):
                raise ValueError(str(data["error"]))
            message = str(data.get("message", ""))
            if message.lower().startswith("invalid input"):
                raise ValueError(message)
        return data

    def add_files(self, file_paths: List[str], vio_model: str) -> Dict[str, Any]:
        upload_files = []
        for path in file_paths:
            with open(path, "rb") as handle:
                upload_files.append(("files", (path.split("/")[-1].split("\\")[-1], handle.read())))
        payload = {
            "username": "",
            "token": self.cfg.api_token,
            "type": "ADD_FILE",
            "vio_model": vio_model,
        }
        return self._request("add_file", payload, files=upload_files)

    def load_files(self, vio_model: str, files: Optional[List[str]] = None, all_files: bool = False) -> Dict[str, Any]:
        payload = self._payload("LOAD_FILE", vio_model, files=files, all_files=all_files)
        return self._request("load_file", payload)

    def delete_files(self, vio_model: str, files: Optional[List[str]] = None, all_files: bool = False) -> Dict[str, Any]:
        payload = self._payload("DELETE_FILE", vio_model, files=files, all_files=all_files)
        return self._request("delete_file", payload)
