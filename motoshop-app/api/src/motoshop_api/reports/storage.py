"""Almacenamiento temporal de reportes descargables con TTL."""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(os.environ.get("REPORTS_STORAGE_PATH", "out/reports"))
REPORT_TTL_SECONDS = 86400  # 24 horas


@dataclass
class ReportRecord:
    report_id: str
    filename: str
    file_path: Path
    mime_type: str
    file_size: int
    created_at: float
    tenant: str
    user_id: str

    @property
    def download_url(self) -> str:
        return f"/api/reports/download/{self.report_id}"


class ReportStorage:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = (base_dir or REPORTS_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, ReportRecord] = {}

    def save_report(
        self,
        data: bytes,
        filename: str,
        mime_type: str,
        tenant: str,
        user_id: str,
    ) -> ReportRecord:
        self.cleanup()
        report_id = f"rep_{uuid.uuid4().hex[:12]}"
        safe_name = "".join(c for c in filename if c.isalnum() or c in "._- ")
        file_path = self.base_dir / f"{report_id}_{safe_name}"
        file_path.write_bytes(data)

        rec = ReportRecord(
            report_id=report_id,
            filename=safe_name,
            file_path=file_path,
            mime_type=mime_type,
            file_size=len(data),
            created_at=time.time(),
            tenant=tenant,
            user_id=user_id,
        )
        self._index[report_id] = rec
        logger.info("report_saved id=%s filename=%s size=%d tenant=%s", report_id, safe_name, len(data), tenant)
        return rec

    def get_report(self, report_id: str) -> ReportRecord | None:
        rec = self._index.get(report_id)
        if rec and rec.file_path.exists():
            return rec
        # Fallback: buscar en disco si se reinició el servidor
        matches = list(self.base_dir.glob(f"{report_id}_*"))
        if matches:
            fp = matches[0]
            orig_name = fp.name[len(report_id) + 1 :]
            ext = fp.suffix.lower()
            mime = "application/octet-stream"
            if ext == ".xlsx":
                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            elif ext == ".pdf":
                mime = "application/pdf"
            elif ext == ".docx":
                mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            rec = ReportRecord(
                report_id=report_id,
                filename=orig_name,
                file_path=fp,
                mime_type=mime,
                file_size=fp.stat().st_size,
                created_at=fp.stat().st_mtime,
                tenant="unknown",
                user_id="unknown",
            )
            self._index[report_id] = rec
            return rec
        return None

    def cleanup(self, max_age: int = REPORT_TTL_SECONDS) -> None:
        now = time.time()
        to_delete = [k for k, v in self._index.items() if now - v.created_at > max_age]
        for k in to_delete:
            rec = self._index.pop(k, None)
            if rec and rec.file_path.exists():
                try:
                    rec.file_path.unlink()
                except OSError:
                    pass


_storage_singleton: ReportStorage | None = None


def get_report_storage() -> ReportStorage:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = ReportStorage()
    return _storage_singleton
