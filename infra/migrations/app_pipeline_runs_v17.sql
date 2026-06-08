-- V1.7 · Pipeline observability — registro de runs + steps
-- Creado: Sub-bloque A V1.7
-- Motor: MySQL InnoDB (Windows, motoshop2024)
--
-- Aplicación (Dev W en Windows):
--   mysql -u root motoshop2024 < infra/migrations/app_pipeline_runs_v17.sql

CREATE TABLE IF NOT EXISTS app_pipeline_runs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pipeline_name VARCHAR(64) NOT NULL COMMENT 'motoshop_full, run_all_v15, etc.',
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(16) NOT NULL COMMENT 'running, success, failed, timeout',
    duration_seconds INT NULL,
    rows_processed INT NULL,
    triggered_by VARCHAR(32) NOT NULL COMMENT 'cron, manual, github_action',
    error_message TEXT NULL,
    INDEX idx_pipeline_started (pipeline_name, started_at),
    INDEX idx_status_started (status, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS app_pipeline_steps (
    id INT AUTO_INCREMENT PRIMARY KEY,
    run_id INT NOT NULL,
    step_order TINYINT NOT NULL,
    step_name VARCHAR(64) NOT NULL COMMENT 'bronze_productos, silver_dim_producto, gold_mart_ventas, ...',
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    status VARCHAR(16) NOT NULL COMMENT 'running, success, failed, skipped',
    duration_seconds INT NULL,
    rows_processed INT NULL,
    log_excerpt TEXT NULL,
    error_message TEXT NULL,
    FOREIGN KEY (run_id) REFERENCES app_pipeline_runs(id) ON DELETE CASCADE,
    INDEX idx_run_step (run_id, step_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verificación:
-- DESCRIBE app_pipeline_runs;
-- DESCRIBE app_pipeline_steps;
