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
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,       -- Флаг "Заблокирован/Активен"
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- Индекс для ускорения поиска при логине (хотя UNIQUE уже создает его, для явности):
CREATE INDEX idx_users_username ON users(username);


-- 3. Вендоры устройств
CREATE TABLE vendors (
    vendor_id SERIAL PRIMARY KEY,
    vendor_name VARCHAR(64) NOT NULL UNIQUE,
    description TEXT
);

-- Дефолтные вендоры (идемпотентно)
INSERT INTO vendors (vendor_name, description)
VALUES
    ('cisco', 'Cisco vendor profile'),
    ('eltex', 'Eltex vendor profile'),
    ('h3c', 'H3C vendor profile')
ON CONFLICT (vendor_name) DO NOTHING;

CREATE INDEX idx_vendors_name ON vendors(vendor_name);


-- 4. Устройства
CREATE TABLE devices (
    device_id SERIAL PRIMARY KEY,
    hostname VARCHAR(100),
    ip_address VARCHAR(45) NOT NULL UNIQUE,
    tacacs_key VARCHAR(100),
    vendor_id INT,
    description TEXT,
    FOREIGN KEY (vendor_id) REFERENCES vendors(vendor_id) ON DELETE SET NULL
);
-- Критически важный индекс. TACACS демон ищет настройки именно по IP входящего пакета.
CREATE INDEX idx_devices_ip ON devices(ip_address);
CREATE INDEX idx_devices_vendor_id ON devices(vendor_id);
CREATE INDEX idx_devices_hostname ON devices(hostname);
CREATE INDEX idx_devices_device_vendor ON devices(device_id, vendor_id);


-- 5. Группы устройств (Локации/Типы)
CREATE TABLE device_groups (
    group_id SERIAL PRIMARY KEY,
    group_name VARCHAR(64) NOT NULL UNIQUE,
    tacacs_key VARCHAR(100),
    description TEXT
);


-- 6. Связь Юзер <-> Группа Юзеров
CREATE TABLE user_group_members (
    user_id INT NOT NULL,
    group_id INT NOT NULL,
    ro_rw SMALLINT NOT NULL DEFAULT 0 CHECK (ro_rw IN (0, 1)),
    PRIMARY KEY (user_id, group_id), -- Составной ключ (защита от дублей)
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES device_groups(group_id) ON DELETE CASCADE
);
-- Индекс для быстрого поиска "в каких группах состоит этот юзер"
CREATE INDEX idx_ugm_user ON user_group_members(user_id);
CREATE INDEX idx_ugm_group ON user_group_members(group_id);
CREATE INDEX idx_ugm_user_group_mode ON user_group_members(user_id, group_id, ro_rw);


-- 7. Связь Устройство <-> Группа Устройств
CREATE TABLE device_group_members (
    device_id INT NOT NULL,
    group_id INT NOT NULL,
    PRIMARY KEY (device_id, group_id), -- Составной ключ
    FOREIGN KEY (device_id) REFERENCES devices(device_id) ON DELETE CASCADE,
    FOREIGN KEY (group_id) REFERENCES device_groups(group_id) ON DELETE CASCADE
);
-- Индекс для поиска "каким группам принадлежит этот IP"
CREATE INDEX idx_dgm_device ON device_group_members(device_id);
CREATE INDEX idx_dgm_group ON device_group_members(group_id);
CREATE INDEX idx_dgm_group_device ON device_group_members(group_id, device_id);


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


-- 10. Profiles для tac_plus-ng
CREATE TABLE profiles (
    profile_id SERIAL PRIMARY KEY,
    profile_name VARCHAR(64) NOT NULL UNIQUE,
    profile_body TEXT NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Индекс для быстрого поиска профиля по имени
CREATE INDEX idx_profiles_name ON profiles(profile_name);
CREATE INDEX idx_profiles_active_profile_id ON profiles(is_active, profile_id);

-- Дефолтные profiles для TACACS (идемпотентно, с обновлением body)
INSERT INTO profiles (profile_name, profile_body, description, is_active)
VALUES
    (
        'cisco_ro',
        $cisco_ro$    script {
        if (service == "shell") {
            # старт shell
            if (cmd == "") {
                set priv-lvl = 15
                permit
            }

            # разрешаем только read-only команды
            if (cmd =~ /^(show|ping|traceroute|terminal length|terminal pager)(\s|$)/)
                permit

            # явно режем опасные штуки
            if (cmd =~ /^(configure|conf t|write|copy|erase|delete|reload|debug|undebug|clear)(\s|$)/)
                deny

            deny
        }
    }
$cisco_ro$,
        'Cisco read-only access profile',
        TRUE
    ),
    (
        'cisco_rw',
        $cisco_rw$    script {
        if (service == "shell" && cmd == "") {
            set priv-lvl = 15
            permit
        }
        permit
    }
$cisco_rw$,
        'Cisco read-write access profile',
        TRUE
    ),
    (
        'eltex_ro',
        $eltex_ro$    script {
        if (service == "shell" && cmd == "")
            permit
        if (cmd =~ /^(show|ping|traceroute)(\s|$)/)
            permit
        deny
    }
$eltex_ro$,
        'Eltex read-only access profile',
        TRUE
    ),
    (
        'eltex_rw',
        $eltex_rw$    script {
        if (service == "shell" && cmd == "") {
            set priv-lvl = 15
            permit
        }
        permit
    }
$eltex_rw$,
        'Eltex read-write access profile',
        TRUE
    ),
    (
        'h3c_ro',
        $h3c_ro$    script {
        if (service == "shell" && cmd == "") {
            set roles = '"network-operator"'
            permit
        }
        permit
    }
$h3c_ro$,
        'H3C read-only access profile',
        TRUE
    ),
    (
        'h3c_rw',
        $h3c_rw$    script {
        if (service == "shell" && cmd == "") {
            set roles = '"network-admin"'
            permit
        }
        permit
    }
$h3c_rw$,
        'H3C read-write access profile',
        TRUE
    )
ON CONFLICT (profile_name)
DO UPDATE SET
    profile_body = EXCLUDED.profile_body,
    description = EXCLUDED.description,
    is_active = EXCLUDED.is_active;


-- 11. Связь User <-> Profiles (many-to-many)
CREATE TABLE user_profile_members (
    user_id INT NOT NULL,
    profile_id INT NOT NULL,
    PRIMARY KEY (user_id, profile_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (profile_id) REFERENCES profiles(profile_id) ON DELETE CASCADE
);

CREATE INDEX idx_upm_user ON user_profile_members(user_id);
CREATE INDEX idx_upm_profile ON user_profile_members(profile_id);

COMMIT;
