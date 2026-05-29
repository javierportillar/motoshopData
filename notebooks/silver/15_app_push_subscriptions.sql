-- DDL: silver.app_push_subscriptions
--
-- Persiste las suscripciones push de los usuarios para enviar
-- notificaciones de alertas de quiebre (urgencia = alta).
--
-- Creado: F4-C (Dev T)
-- Dependencia: ninguna (tabla silver independiente)

CREATE TABLE IF NOT EXISTS motoshop.silver.app_push_subscriptions (
    subscription_id      BIGINT GENERATED ALWAYS AS IDENTITY,
    endpoint             STRING NOT NULL,
    p256dh               STRING NOT NULL,
    auth                 STRING NOT NULL,
    user_id              STRING NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP(),
    active               BOOLEAN NOT NULL DEFAULT TRUE
)
USING DELTA
TBLPROPERTIES (
    'delta.feature.allowColumnDefaults' = 'true'
);

-- Las suscripciones expiradas se marcan active=FALSE en lugar de borrarse.
-- Se eliminan físicamente en mantenimiento anual si es necesario.

ALTER TABLE motoshop.silver.app_push_subscriptions SET TBLPROPERTIES (
    'comment' = 'Suscripciones push de usuarios para alertas de quiebre (F4-C)'
);
