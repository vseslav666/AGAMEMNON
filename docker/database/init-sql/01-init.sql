BEGIN;

-- 0) Расширения (нужны права суперпользователя/владельца БД)
CREATE EXTENSION IF NOT EXISTS citext;

-- 1) Создаём прикладного пользователя, если его нет
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'tacacs_pg') THEN
    CREATE ROLE tacacs_pg
      LOGIN
      PASSWORD 'supersecret'
      NOSUPERUSER
      NOCREATEDB
      NOCREATEROLE
      NOINHERIT;
  END IF;
END $$;

-- 2) Права на БД
GRANT CONNECT, TEMPORARY ON DATABASE tacacs_db TO tacacs_pg;

-- 3) Создаём отдельную схему под tacacs и делаем её владельцем tacacs_pg
CREATE SCHEMA IF NOT EXISTS tacacs AUTHORIZATION tacacs_pg;

-- Чтобы по умолчанию всё искалось в tacacs
ALTER DATABASE tacacs_db SET search_path = tacacs, public;

-- 4) Переключаемся на прикладную роль: дальше все объекты будут её собственностью
SET ROLE tacacs_pg;
SET search_path = tacacs, public;

-- ENUM'ы
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auth_object_type') THEN
    CREATE TYPE auth_object_type AS ENUM ('user', 'group');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'accounting_record_type') THEN
    CREATE TYPE accounting_record_type AS ENUM ('start', 'stop', 'update', 'command');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auth_method') THEN
    CREATE TYPE auth_method AS ENUM ('password', 'totp', 'password+totp');
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'auth_result') THEN
    CREATE TYPE auth_result AS ENUM ('allow', 'deny', 'error');
  END IF;
END$$;

-- Функция авто-обновления updated_at
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = CURRENT_TIMESTAMP;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- USERS
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        CITEXT NOT NULL UNIQUE,
    password_hash   VARCHAR(255),
    password_type   VARCHAR(16) DEFAULT 'bcrypt',
    description     TEXT,
    enabled         BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_users_updated_at
BEFORE UPDATE ON users
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- GROUPS
CREATE TABLE IF NOT EXISTS groups (
    id          SERIAL PRIMARY KEY,
    name        CITEXT NOT NULL UNIQUE,
    description TEXT,
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_groups_updated_at
BEFORE UPDATE ON groups
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- USER <-> GROUPS
CREATE TABLE IF NOT EXISTS user_groups (
    user_id     INTEGER NOT NULL REFERENCES users(id)  ON DELETE CASCADE,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    priority    INTEGER DEFAULT 10,
    PRIMARY KEY (user_id, group_id)
);

CREATE INDEX IF NOT EXISTS idx_user_groups_group_id ON user_groups(group_id);

-- DEVICES (NAS)
CREATE TABLE IF NOT EXISTS devices (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(64) NOT NULL UNIQUE,
    ip_address  INET NOT NULL,
    secret      VARCHAR(255) NOT NULL,
    description TEXT,
    enabled     BOOLEAN DEFAULT TRUE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_devices_updated_at
BEFORE UPDATE ON devices
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_devices_ip ON devices(ip_address);

-- AUTHORIZATION RULES
CREATE TABLE IF NOT EXISTS authorization_rules (
    id                  SERIAL PRIMARY KEY,
    name                VARCHAR(64) NOT NULL,
    object_type         auth_object_type NOT NULL,
    user_id             INTEGER REFERENCES users(id)  ON DELETE CASCADE,
    group_id            INTEGER REFERENCES groups(id) ON DELETE CASCADE,
    service             VARCHAR(32) DEFAULT 'shell',
    privilege_level     SMALLINT CHECK (privilege_level BETWEEN 0 AND 15),
    permitted_commands  TEXT,
    denied_commands     TEXT,
    argument_filter     TEXT,
    enabled             BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (
      (object_type = 'user'  AND user_id  IS NOT NULL AND group_id IS NULL) OR
      (object_type = 'group' AND group_id IS NOT NULL AND user_id  IS NULL)
    )
);

CREATE TRIGGER trg_auth_rules_updated_at
BEFORE UPDATE ON authorization_rules
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE INDEX IF NOT EXISTS idx_auth_rules_user  ON authorization_rules(user_id)
  WHERE object_type = 'user';
CREATE INDEX IF NOT EXISTS idx_auth_rules_group ON authorization_rules(group_id)
  WHERE object_type = 'group';
CREATE INDEX IF NOT EXISTS idx_auth_rules_service ON authorization_rules(service);

-- AV-пары для правил
CREATE TABLE IF NOT EXISTS authorization_rule_avpairs (
    id          SERIAL PRIMARY KEY,
    rule_id     INTEGER NOT NULL REFERENCES authorization_rules(id) ON DELETE CASCADE,
    av_key      VARCHAR(64) NOT NULL,
    av_value    TEXT NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    UNIQUE (rule_id, av_key, av_value)
);

CREATE INDEX IF NOT EXISTS idx_rule_avpairs_rule ON authorization_rule_avpairs(rule_id);

-- USER ATTRIBUTES
CREATE TABLE IF NOT EXISTS user_attributes (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    attr_key    VARCHAR(64) NOT NULL,
    attr_value  TEXT NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    UNIQUE (user_id, attr_key)
);

CREATE INDEX IF NOT EXISTS idx_user_attrs_user ON user_attributes(user_id);

-- GROUP ATTRIBUTES
CREATE TABLE IF NOT EXISTS group_attributes (
    id          SERIAL PRIMARY KEY,
    group_id    INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    attr_key    VARCHAR(64) NOT NULL,
    attr_value  TEXT NOT NULL,
    enabled     BOOLEAN DEFAULT TRUE,
    UNIQUE (group_id, attr_key)
);

CREATE INDEX IF NOT EXISTS idx_group_attrs_group ON group_attributes(group_id);

-- TOTP / 2FA
CREATE TABLE IF NOT EXISTS user_mfa_totp (
    user_id         INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    secret_base32   TEXT NOT NULL,
    otp_uri         TEXT,
    issuer          VARCHAR(64) DEFAULT 'tacacs-plus',
    label           VARCHAR(128),
    digits          SMALLINT DEFAULT 6 CHECK (digits IN (6,8)),
    period          SMALLINT DEFAULT 30 CHECK (period BETWEEN 10 AND 120),
    algorithm       VARCHAR(8) DEFAULT 'SHA1' CHECK (algorithm IN ('SHA1','SHA256','SHA512')),
    enabled         BOOLEAN DEFAULT TRUE,
    disabled_until  TIMESTAMP NULL,
    last_used_step  BIGINT NULL,
    last_used_at    TIMESTAMP NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER trg_user_mfa_updated_at
BEFORE UPDATE ON user_mfa_totp
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Логи аутентификаций
CREATE TABLE IF NOT EXISTS auth_logs (
    id          BIGSERIAL PRIMARY KEY,
    event_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    username    TEXT NOT NULL,
    user_id     INTEGER REFERENCES users(id)    ON DELETE SET NULL,
    device_id   INTEGER REFERENCES devices(id)  ON DELETE SET NULL,
    remote_addr INET,
    method      auth_method NOT NULL,
    result      auth_result NOT NULL,
    reason      TEXT,
    data        JSONB
);

CREATE INDEX IF NOT EXISTS idx_auth_logs_user_time ON auth_logs(username, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_auth_logs_result ON auth_logs(result);
CREATE INDEX IF NOT EXISTS idx_auth_logs_device_time ON auth_logs(device_id, event_time DESC);

-- Accounting
CREATE TABLE IF NOT EXISTS accounting_records (
    id          BIGSERIAL PRIMARY KEY,
    event_time  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    record_type accounting_record_type NOT NULL,
    session_id  VARCHAR(64) NOT NULL,
    username    TEXT NOT NULL,
    user_id     INTEGER REFERENCES users(id)    ON DELETE SET NULL,
    device_id   INTEGER REFERENCES devices(id)  ON DELETE SET NULL,
    service     VARCHAR(32),
    priv_lvl    SMALLINT CHECK (priv_lvl BETWEEN 0 AND 15),
    command     TEXT,
    arguments   TEXT,
    remote_addr INET,
    result      auth_result,
    data        JSONB
);

CREATE INDEX IF NOT EXISTS idx_acct_session ON accounting_records(session_id);
CREATE INDEX IF NOT EXISTS idx_acct_user_time ON accounting_records(username, event_time DESC);
CREATE INDEX IF NOT EXISTS idx_acct_device_time ON accounting_records(device_id, event_time DESC);

COMMIT;
