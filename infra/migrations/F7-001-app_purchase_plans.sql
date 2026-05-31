-- F7-001: Tabla app_purchase_plans para guardar planes de compra históricos
-- Aplica: Dev W en Windows MySQL 5.0+
-- Rollback: DROP TABLE IF EXISTS app_purchase_plans;
-- Fecha: 2026-05-30 · Sprint F7-D

CREATE TABLE IF NOT EXISTS app_purchase_plans (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  created_by VARCHAR(64) NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  plan_name VARCHAR(255),
  total_skus INT,
  total_value DECIMAL(15,2),
  items JSON,
  status ENUM('draft','approved','sent','received') DEFAULT 'draft',
  INDEX idx_user_created (created_by, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;
