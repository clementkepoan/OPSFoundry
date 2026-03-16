from datetime import UTC, datetime
import hashlib
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from pydantic import BaseModel, Field


class StoredDocument(BaseModel):
    id: str
    workflow_name: str
    filename: str
    content_type: str
    object_key: str
    size_bytes: int
    sha256: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class LocalObjectStore:
    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.metadata_dir = self.root_dir / "_meta"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_dir.mkdir(parents=True, exist_ok=True)

    def save_document(
        self,
        workflow_name: str,
        filename: str,
        content_type: str,
        payload: bytes,
    ) -> StoredDocument:
        return self.save_document_stream(
            workflow_name=workflow_name,
            filename=filename,
            content_type=content_type,
            source=[payload],
        )

    def save_document_stream(
        self,
        workflow_name: str,
        filename: str,
        content_type: str,
        source: BinaryIO | list[bytes],
        chunk_size: int = 1024 * 1024,
        on_chunk: Callable[[bytes], None] | None = None,
    ) -> StoredDocument:
        document_id = str(uuid4())
        safe_name = self._sanitize_filename(filename)
        workflow_dir = self.root_dir / workflow_name
        workflow_dir.mkdir(parents=True, exist_ok=True)

        object_key = f"{workflow_name}/{document_id}_{safe_name}"
        object_path = self.root_dir / object_key
        size_bytes = 0
        hasher = hashlib.sha256()

        try:
            with object_path.open("wb") as output_file:
                for chunk in self._iter_chunks(source, chunk_size=chunk_size):
                    if not chunk:
                        continue

                    output_file.write(chunk)
                    size_bytes += len(chunk)
                    hasher.update(chunk)
                    if on_chunk is not None:
                        on_chunk(chunk)
        except Exception:
            object_path.unlink(missing_ok=True)
            raise

        document = StoredDocument(
            id=document_id,
            workflow_name=workflow_name,
            filename=filename,
            content_type=content_type,
            object_key=object_key,
            size_bytes=size_bytes,
            sha256=hasher.hexdigest(),
        )
        self._write_metadata(document)
        return document

    def get_document(self, document_id: str) -> StoredDocument:
        metadata_path = self.metadata_dir / f"{document_id}.json"
        if not metadata_path.exists():
            raise KeyError(f"Unknown document '{document_id}'")

        return StoredDocument.model_validate_json(metadata_path.read_text(encoding="utf-8"))

    def read_bytes(self, document: StoredDocument) -> bytes:
        return self.resolve_path(document).read_bytes()

    def resolve_path(self, document: StoredDocument) -> Path:
        path = self.root_dir / document.object_key
        if not path.exists():
            raise FileNotFoundError(f"Stored object for document '{document.id}' is missing.")

        return path

    def delete_document(self, document: StoredDocument) -> None:
        metadata_path = self.metadata_dir / f"{document.id}.json"
        object_path = self.root_dir / document.object_key
        object_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)

    def _write_metadata(self, document: StoredDocument) -> None:
        metadata_path = self.metadata_dir / f"{document.id}.json"
        metadata_path.write_text(
            json.dumps(document.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )

    @staticmethod
    def _iter_chunks(source: BinaryIO | list[bytes], chunk_size: int) -> Iterator[bytes]:
        if isinstance(source, list):
            yield from source
            return

        while True:
            chunk = source.read(chunk_size)
            if not chunk:
                break
            yield chunk

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        cleaned = "".join(char if char.isalnum() or char in {"-", "_", "."} else "_" for char in filename)
        return cleaned or "upload.bin"
