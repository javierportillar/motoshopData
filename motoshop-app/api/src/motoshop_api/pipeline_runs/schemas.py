"""Schemas para pipeline observability (V1.7)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class PipelineStep(BaseModel):
    id: int
    run_id: int
    step_order: int
    step_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str  # running, success, failed, skipped
    duration_seconds: int | None = None
    rows_processed: int | None = None
    log_excerpt: str | None = None
    error_message: str | None = None


class PipelineRun(BaseModel):
    id: int
    pipeline_name: str
    started_at: datetime
    finished_at: datetime | None = None
    status: str  # running, success, failed, timeout
    duration_seconds: int | None = None
    rows_processed: int | None = None
    triggered_by: str  # cron, manual, github_action
    error_message: str | None = None


class PipelineRunDetail(PipelineRun):
    steps: list[PipelineStep] = []


class RunsSummary(BaseModel):
    success_rate_30d_pct: float
    avg_duration_seconds: float
    total_runs_30d: int
    last_run_status: str | None = None
    last_run_finished_at: datetime | None = None
