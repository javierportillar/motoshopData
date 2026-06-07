-- V1.6 · app_llm_usage — registro de uso de LLM (cost audit)
-- Creado: Sprint A V1.6
-- Motor: MySQL InnoDB (Windows, motoshop2024)
-- 
-- Aunque los modelos free tienen costo $0, esta tabla loguea uso
-- por modelo/tokens para auditoría y monitoreo de adopción.
--
-- Aplicación:
--   mysql -u root motoshop2024 < infra/migrations/app_llm_usage_v16.sql

CREATE TABLE IF NOT EXISTS app_llm_usage (
    id INT AUTO_INCREMENT PRIMARY KEY,
    timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    endpoint VARCHAR(64) NOT NULL COMMENT 'briefing_generate, briefing_send, forecast_explain, qa_chat',
    model VARCHAR(64) NOT NULL COMMENT 'deepseek-v4-flash-free, qwen3.6-plus-free, etc.',
    tokens_input INT NULL COMMENT 'Tokens enviados al modelo (prompt + contexto)',
    tokens_output INT NULL COMMENT 'Tokens generados por el modelo (respuesta)',
    cost_usd DECIMAL(8,5) NOT NULL DEFAULT 0 COMMENT 'Costo real USD (0.0 para modelos free)',
    conversation_id VARCHAR(64) NULL COMMENT 'UUID de sesión para Q&A (NULL para briefing)',
    success TINYINT NOT NULL DEFAULT 1 COMMENT '1=exito, 0=fallo (timeout, 500, etc.)',
    error_message TEXT NULL COMMENT 'Mensaje de error si success=0',
    INDEX idx_timestamp (timestamp),
    INDEX idx_endpoint (endpoint, timestamp),
    INDEX idx_model (model, timestamp)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Verificación:
-- DESCRIBE app_llm_usage;
-- SELECT COUNT(*) FROM app_llm_usage;
