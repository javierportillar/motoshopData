"""Almacenamiento temporal de reportes descargables con TTL."""

from __future__ import annotations

import logging
import os
import time
import uuid
from dataclasses import dataclass
from contextlib import suppress
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

    @property
    def expires_at_iso(self) -> str:
        from datetime import datetime, timedelta, timezone

        expires = datetime.fromtimestamp(self.created_at, tz=timezone.utc) + timedelta(
            seconds=REPORT_TTL_SECONDS
        )
        return expires.isoformat()


class ReportStorage:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = (base_dir or REPORTS_DIR).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._index: dict[str, ReportRecord] = {}
        # Startup sweep: borra reportes vencidos que quedaron en disco tras un
        # reinicio (el índice en memoria se perdió, el archivo no).
        self.sweep_expired_files()

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
        # El tenant viaja en el nombre de archivo para que la validación de
        # acceso sobreviva a reinicios del servidor (índice en memoria perdido).
        file_path = self.base_dir / f"{report_id}__{tenant}__{safe_name}"
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
        # report_id viene de la URL: solo aceptamos el formato exacto rep_ + 12
        # hex para que no se pueda inyectar un patrón de glob (*, ?, /).
        import re

        if not re.fullmatch(r"rep_[0-9a-f]{12}", report_id):
            return None
        rec = self._index.get(report_id)
        if rec and rec.file_path.exists() and not self._expired(rec):
            return rec
        if rec and rec.file_path.exists():
            with suppress(OSError):
                rec.file_path.unlink()
            self._index.pop(report_id, None)
            return None
        # Fallback: buscar en disco si se reinició el servidor
        matches = list(self.base_dir.glob(f"{report_id}__*")) or list(
            self.base_dir.glob(f"{report_id}_*")
        )
        if matches:
            fp = matches[0]
            if time.time() - fp.stat().st_mtime > REPORT_TTL_SECONDS:
                with suppress(OSError):
                    fp.unlink()
                return None
            rest = fp.name[len(report_id) + 2 :] if "__" in fp.name else fp.name[len(report_id) + 1 :]
            # Formato nuevo: {report_id}__{tenant}__{filename} → tenant recuperable
            if "__" in fp.name:
                parts = fp.name[len(report_id) + 2 :].split("__", 1)
                tenant, orig_name = (parts + [""])[:2] if len(parts) == 2 else ("unknown", rest)
            else:
                tenant, orig_name = "unknown", rest
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
                filename=orig_name or fp.name,
                file_path=fp,
                mime_type=mime,
                file_size=fp.stat().st_size,
                created_at=fp.stat().st_mtime,
                tenant=tenant,
                user_id="unknown",
            )
            self._index[report_id] = rec
            return rec
        return None

    @staticmethod
    def _expired(record: ReportRecord) -> bool:
        """Use the earliest creation/file timestamp after a restart or copy."""
        try:
            created_at = min(record.created_at, record.file_path.stat().st_mtime)
        except OSError:
            return True
        return time.time() - created_at > REPORT_TTL_SECONDS

    def cleanup(self, max_age: int = REPORT_TTL_SECONDS) -> None:
        now = time.time()
        to_delete = [k for k, v in self._index.items() if self._expired(v) or now - v.created_at > max_age]
        for k in to_delete:
            rec = self._index.pop(k, None)
            if rec and rec.file_path.exists():
                try:
                    rec.file_path.unlink()
                except OSError:
                    pass

    def sweep_expired_files(self, max_age: int = REPORT_TTL_SECONDS) -> int:
        """Borra del disco cualquier reporte vencido, esté o no en el índice."""
        now = time.time()
        removed = 0
        for fp in self.base_dir.glob("rep_*"):
            try:
                if now - fp.stat().st_mtime > max_age:
                    fp.unlink()
                    self._index.pop(fp.name.split("__", 1)[0], None)
                    removed += 1
            except OSError:
                continue
        return removed


_storage_singleton: ReportStorage | None = None


def get_report_storage() -> ReportStorage:
    global _storage_singleton
    if _storage_singleton is None:
        _storage_singleton = ReportStorage()
    return _storage_singleton
