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

-- 1. Пользователи
CREATE TABLE users (
    user_id SERIAL PRIMARY KEY,
    username VARCHAR(64) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(100),
    is_active BOOLEAN DEFAULT TRUE,       -- Флаг "Заблокирован/Активен"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Индекс для ускорения поиска при логине (хотя UNIQUE уже создает его, для явности):
CREATE INDEX idx_users_username ON users(username);


-- 2. Группы пользователей (Роли)
CREATE TABLE user_groups (
    group_id SERIAL PRIMARY KEY,
    group_name VARCHAR(64) NOT NULL UNIQUE,
    description TEXT
);


-- 3. Хосты (Железо)
CREATE TABLE hosts (
    host_id SERIAL PRIMARY KEY,
    hostname VARCHAR(100),
    ip_address VARCHAR(45) NOT NULL UNIQUE,
    tacacs_key VARCHAR(100) NOT NULL,
    description TEXT
);
-- Критически важный индекс. TACACS демон ищет настройки именно по IP входящего пакета.
CREATE INDEX idx_hosts_ip ON hosts(ip_address);


-- 4. Группы хостов (Локации/Типы)
CREATE TABLE host_groups (
    group_id SERIAL PRIMARY KEY,
    group_name VARCHAR(64) NOT NULL UNIQUE,
    description TEXT
);


-- 5. Связь Юзер <-> Группа Юзеров
CREATE TABLE user_group_members (
    user_id INT NOT NULL,
    group_id INT NOT NULL,
    PRIMARY KEY (user_id, group_id), -- Составной ключ (защита от дублей)
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES user_groups(group_id) ON DELETE CASCADE
);
-- Индекс для быстрого поиска "в каких группах состоит этот юзер"
CREATE INDEX idx_ugm_user ON user_group_members(user_id);


-- 6. Связь Хост <-> Группа Хостов
CREATE TABLE host_group_members (
    host_id INT NOT NULL,
    group_id INT NOT NULL,
    PRIMARY KEY (host_id, group_id), -- Составной ключ
    FOREIGN KEY (host_id) REFERENCES hosts(host_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES host_groups(group_id) ON DELETE CASCADE
);
-- Индекс для поиска "каким группам принадлежит этот IP"
CREATE INDEX idx_hgm_host ON host_group_members(host_id);


-- 7. Политики доступа (Матрица доступа)
CREATE TABLE access_policies (
    policy_id SERIAL PRIMARY KEY,
    user_group_id INT NOT NULL,
    host_group_id INT NOT NULL,
    priv_lvl INT DEFAULT 1 CHECK (priv_lvl BETWEEN 0 AND 15), -- Уровень привилегий Cisco (1 или 15)
    allow_access BOOLEAN DEFAULT TRUE, -- Можно явно запретить (Deny rule)
    
    FOREIGN KEY (user_group_id) REFERENCES user_groups(group_id) ON DELETE CASCADE,
    FOREIGN KEY (host_group_id) REFERENCES host_groups(group_id) ON DELETE CASCADE,
    
    -- Защита от дублирования одинаковых правил
    UNIQUE (user_group_id, host_group_id)
);
-- Индексы для JOIN-ов при проверке прав
CREATE INDEX idx_policy_ug ON access_policies(user_group_id);
CREATE INDEX idx_policy_hg ON access_policies(host_group_id);


-- 8. Разрешенные/Запрещенные команды для политики
CREATE TABLE command_rules (
    rule_id SERIAL PRIMARY KEY,
    policy_id INT NOT NULL,
    command_pattern VARCHAR(255) NOT NULL, -- Regex, например: "^show running-config.*"
    action VARCHAR(10) DEFAULT 'PERMIT' CHECK (action IN ('PERMIT', 'DENY')),
    
    FOREIGN KEY (policy_id) REFERENCES access_policies(policy_id) ON DELETE CASCADE
);
-- Индекс для быстрого поиска правил конкретной политики
CREATE INDEX idx_cmd_policy ON command_rules(policy_id);


-- 9. TOTP-профили для 2FA
CREATE TABLE user_totp (
    id SERIAL PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,               -- Один активный TOTP-профиль на юзера
    totp_secret VARCHAR(128) NOT NULL,         -- ЗАШИФРОВАННЫЙ секрет (а не QR)
    is_enabled BOOLEAN NOT NULL DEFAULT FALSE, -- Включена ли 2FA
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP NULL,               -- Когда последний раз прошла 2FA
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
);

-- Индекс для быстрых проверок 2FA по юзеру
CREATE INDEX idx_user_totp_user_id ON user_totp(user_id);


COMMIT;
