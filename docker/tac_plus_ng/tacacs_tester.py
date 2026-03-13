#!/usr/bin/env python3
"""
TACACS+ Authentication Tester Utility
Исправленная версия для актуального API библиотеки tacacs_plus
"""

import argparse
import sys
from tacacs_plus.client import TACACSClient
from tacacs_plus import flags
import socket

try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass


def _is_auth_success(auth_result):
    """Нормализованная проверка успешности ответа от разных версий tacacs_plus."""
    # 1) bool
    if isinstance(auth_result, bool):
        return auth_result

    # 2) объекты ответа с полем status
    status = getattr(auth_result, 'status', None)
    if status is not None:
        pass_status = getattr(flags, 'TAC_PLUS_AUTHEN_STATUS_PASS', 1)
        return status == pass_status

    # 3) fallback — избегаем ложноположительного bool(object) == True
    return False


def _safe_text(value):
    if value is None:
        return ''
    if isinstance(value, (bytes, bytearray)):
        try:
            return value.decode('utf-8')
        except Exception:
            # Показываем безопасное hex-представление вместо кракозябр.
            sample = bytes(value[:24]).hex()
            return f"<binary:{len(value)} bytes, hex={sample}>"
    return str(value)


def _is_likely_gibberish(text):
    if not text:
        return False
    printable = sum(1 for ch in text if ch.isprintable() and ch not in '\x0b\x0c')
    ratio = printable / max(len(text), 1)
    return ratio < 0.75

def test_tacacs_authentication(host, port, key, username, password, source_ip=None):
    """
    Тестирует TACACS+ аутентификацию с указанными параметрами
    """
    
    try:
        # Создаем TACACS+ клиент
        client = TACACSClient(
            host, 
            port, 
            key,
            timeout=10
        )
        
        print(f"[*] Пытаемся аутентифицироваться:")
        print(f"    Сервер: {host}:{port}")
        print(f"    Username: {username}")
        print(f"    Source IP: {source_ip if source_ip else 'Auto'}")
        
        # Используем правильные константы из модуля flags
        # В новых версиях библиотеки типы аутентификации доступны как атрибуты flags
        try:
            # Пробуем разные варианты именования констант
            if hasattr(flags, 'TAC_PLUS_AUTHEN_TYPE_ASCII'):
                auth_type = flags.TAC_PLUS_AUTHEN_TYPE_ASCII
            elif hasattr(flags, 'AUTHEN_TYPE_ASCII'):
                auth_type = flags.AUTHEN_TYPE_ASCII
            else:
                # Если не нашли, используем числовое значение (1 обычно соответствует ASCII)
                auth_type = 1
                print(f"[*] Используем значение по умолчанию для типа аутентификации")
            
            # Выполняем аутентификацию
            # В некоторых версиях метод authenticate может принимать другие параметры
            authenticated = client.authenticate(
                username,
                password
                #authen_type=auth_type
            )
            
        except TypeError as e:
            # Если не получается с дополнительными параметрами, пробуем базовый вызов
            print(f"[*] Пробуем базовый метод аутентификации...")
            authenticated = client.authenticate(username, password)
        
        if _is_auth_success(authenticated):
            print(f"[OK] Аутентификация успешна")
            return True
        else:
            status = getattr(authenticated, 'status', None)
            server_msg = getattr(authenticated, 'server_msg', b'')
            message_text = _safe_text(server_msg)
            print(f"[FAIL] Аутентификация не удалась: status={status}, msg={message_text}")
            if isinstance(message_text, str) and 'Illegal packet' in message_text:
                print("[HINT] Проверь TACACS shared secret (-k). Несовпадение секрета часто даёт Illegal packet (version=0xc0 type=0x01).")
            elif _is_likely_gibberish(message_text) or (isinstance(status, int) and status > 10):
                print("[HINT] Ответ выглядит как некорректно расшифрованный пакет. Наиболее вероятно не совпадает shared secret (-k) между клиентом и TACACS-сервером.")
            return False
            
    except ImportError as e:
        print(f"[!] Ошибка импорта: {e}")
        print(f"    Убедитесь, что библиотека tacacs_plus установлена корректно:")
        print(f"    pip install --upgrade tacacs_plus")
        return False
    except ConnectionRefusedError:
        print(f"[!] Ошибка: Соединение отклонено сервером {host}:{port}")
        return False
    except socket.timeout:
        print(f"[!] Ошибка: Таймаут соединения с сервером {host}:{port}")
        return False
    except Exception as e:
        print(f"[!] Ошибка: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='TACACS+ Authentication Tester Utility',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('-s', '--server', required=True,
                       help='TACACS+ сервер (IP или hostname)')
    parser.add_argument('-k', '--key', required=True,
                       help='TACACS+ секретный ключ')
    parser.add_argument('-u', '--username', required=True,
                       help='Имя пользователя для аутентификации')
    parser.add_argument('-p', '--password', required=True,
                       help='Пароль пользователя')
    parser.add_argument('--port', type=int, default=49,
                       help='Порт TACACS+ сервера (по умолчанию: 49)')
    parser.add_argument('-src', '--source-ip',
                       help='IP адрес источника (опционально)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Подробный вывод')
    
    args = parser.parse_args()
    
    # Выводим информацию о версии библиотеки для отладки
    if args.verbose:
        import tacacs_plus
        print(f"[*] Версия tacacs_plus: {getattr(tacacs_plus, '__version__', 'unknown')}")
        print(f"[*] Доступные атрибуты flags: {dir(flags)}")
        print()
    
    result = test_tacacs_authentication(
        args.server,
        args.port,
        args.key,
        args.username,
        args.password,
        args.source_ip
    )
    
    sys.exit(0 if result else 1)

if __name__ == "__main__":
    main()
