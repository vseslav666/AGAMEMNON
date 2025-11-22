import json
import qrcode
import os
import argparse
import sys
from datetime import datetime
import pyotp


class TOTPManager:
    def __init__(self, storage_file="totp_data.json"):
        self.storage_file = storage_file
        self.data = self.load_data()

    def load_data(self):
        """Загрузка данных из JSON файла"""
        try:
            if os.path.exists(self.storage_file):
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                # Создание файла с начальной структурой
                initial_data = {"users": {}}
                self.save_data(initial_data)
                return initial_data
        except Exception as e:
            print(f"Ошибка при загрузке данных: {e}")
            return {"users": {}}

    def save_data(self, data=None):
        """Сохранение данных в JSON файл"""
        if data is None:
            data = self.data
        
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"Ошибка при сохранении данных: {e}")
            return False

    def generate_totp_secret(self):
        """Генерация секретного ключа для TOTP"""
        return pyotp.random_base32()

    def generate_qr_code(self, username, secret_key, issuer_name="MyApp"):
        """Генерация QR кода"""
        try:
            # Создание TOTP URI
            totp = pyotp.TOTP(secret_key)
            uri = totp.provisioning_uri(username, issuer_name=issuer_name)
            
            # Генерация QR кода
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(uri)
            qr.make(fit=True)
            
            # Создание изображения
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Сохранение QR кода
            qr_dir = "qr_codes"
            if not os.path.exists(qr_dir):
                os.makedirs(qr_dir)
            
            qr_path = os.path.join(qr_dir, f"{username}_totp.png")
            img.save(qr_path)
            
            return qr_path
            
        except Exception as e:
            print(f"Ошибка при генерации QR кода: {e}")
            return None

    def create_user_totp(self, username, issuer_name="MyApp"):
        """Создание TOTP для пользователя"""
        try:
            # Проверка существования пользователя
            if username in self.data["users"]:
                return {"status": "error", "message": "Пользователь уже существует"}
            
            # Генерация секретного ключа
            secret_key = self.generate_totp_secret()
            
            # Генерация QR кода
            qr_path = self.generate_qr_code(username, secret_key, issuer_name)
            
            if not qr_path:
                return {"status": "error", "message": "Ошибка при генерации QR кода"}
            
            # Сохранение данных
            current_time = datetime.now().isoformat()
            self.data["users"][username] = {
                "secret_key": secret_key,
                "qr_code_path": qr_path,
                "issuer_name": issuer_name,
                "created_at": current_time,
                "updated_at": current_time
            }
            
            # Сохранение в файл
            if self.save_data():
                return {
                    "status": "success", 
                    "message": "TOTP успешно создан",
                    "username": username,
                    "qr_code_path": qr_path,
                    "secret_key": secret_key
                }
            else:
                return {"status": "error", "message": "Ошибка при сохранении данных"}
            
        except Exception as e:
            return {"status": "error", "message": f"Ошибка при создании TOTP: {str(e)}"}

    def get_user(self, username):
        """Получение информации о пользователе"""
        try:
            user_data = self.data["users"].get(username)
            if user_data:
                return {
                    "username": username,
                    "secret_key": user_data["secret_key"],
                    "qr_code_path": user_data["qr_code_path"],
                    "issuer_name": user_data.get("issuer_name", "MyApp"),
                    "created_at": user_data["created_at"],
                    "updated_at": user_data["updated_at"]
                }
            return None
            
        except Exception as e:
            print(f"Ошибка при получении пользователя: {e}")
            return None

    def verify_totp(self, username, token):
        """Проверка TOTP токена"""
        try:
            user = self.get_user(username)
            if not user:
                return {"status": "error", "message": "Пользователь не найден"}
            
            totp = pyotp.TOTP(user['secret_key'])
            is_valid = totp.verify(token)
            
            return {
                "status": "success",
                "is_valid": is_valid,
                "message": "Токен верный" if is_valid else "Токен неверный"
            }
            
        except Exception as e:
            return {"status": "error", "message": f"Ошибка при проверке токена: {str(e)}"}

    def update_user_secret(self, username, issuer_name=None):
        """Обновление секретного ключа пользователя"""
        try:
            user = self.get_user(username)
            if not user:
                return {"status": "error", "message": "Пользователь не найден"}
            
            # Используем существующее имя приложения или переданное
            if issuer_name is None:
                issuer_name = user.get('issuer_name', 'MyApp')
            
            # Генерация нового секретного ключа
            new_secret = self.generate_totp_secret()
            
            # Генерация нового QR кода
            qr_path = self.generate_qr_code(username, new_secret, issuer_name)
            
            if not qr_path:
                return {"status": "error", "message": "Ошибка при генерации QR кода"}
            
            # Удаление старого QR кода
            old_qr_path = user['qr_code_path']
            if old_qr_path and os.path.exists(old_qr_path):
                try:
                    os.remove(old_qr_path)
                except Exception as e:
                    print(f"Ошибка при удалении старого QR кода: {e}")
            
            # Обновление данных
            current_time = datetime.now().isoformat()
            self.data["users"][username] = {
                "secret_key": new_secret,
                "qr_code_path": qr_path,
                "issuer_name": issuer_name,
                "created_at": user['created_at'],
                "updated_at": current_time
            }
            
            # Сохранение в файл
            if self.save_data():
                return {
                    "status": "success",
                    "message": "Секретный ключ успешно обновлен",
                    "username": username,
                    "qr_code_path": qr_path
                }
            else:
                return {"status": "error", "message": "Ошибка при сохранении данных"}
            
        except Exception as e:
            return {"status": "error", "message": f"Ошибка при обновлении ключа: {str(e)}"}

    def delete_user(self, username):
        """Удаление пользователя"""
        try:
            user = self.get_user(username)
            if not user:
                return {"status": "error", "message": "Пользователь не найден"}
            
            # Удаление файла QR кода
            if user['qr_code_path'] and os.path.exists(user['qr_code_path']):
                try:
                    os.remove(user['qr_code_path'])
                except Exception as e:
                    print(f"Ошибка при удалении QR кода: {e}")
            
            # Удаление из данных
            if username in self.data["users"]:
                del self.data["users"][username]
                
                # Сохранение в файл
                if self.save_data():
                    return {"status": "success", "message": "Пользователь успешно удален"}
                else:
                    return {"status": "error", "message": "Ошибка при сохранении данных"}
            else:
                return {"status": "error", "message": "Пользователь не найден в данных"}
            
        except Exception as e:
            return {"status": "error", "message": f"Ошибка при удалении пользователя: {str(e)}"}

    def get_all_users(self):
        """Получение списка всех пользователей"""
        try:
            users = []
            for username, user_data in self.data["users"].items():
                users.append({
                    "username": username,
                    "issuer_name": user_data.get("issuer_name", "MyApp"),
                    "created_at": user_data["created_at"],
                    "updated_at": user_data["updated_at"],
                    "qr_code_path": user_data["qr_code_path"]
                })
            
            return {"status": "success", "users": users}
            
        except Exception as e:
            return {"status": "error", "message": f"Ошибка при получении списка пользователей: {str(e)}"}

    def backup_data(self, backup_file=None):
        """Создание резервной копии данных"""
        try:
            if backup_file is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_file = f"totp_backup_{timestamp}.json"
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            
            return {"status": "success", "message": f"Резервная копия создана: {backup_file}"}
            
        except Exception as e:
            return {"status": "error", "message": f"Ошибка при создании резервной копии: {str(e)}"}


def main():
    """Основная функция для обработки аргументов командной строки"""
    parser = argparse.ArgumentParser(description='TOTP Manager - генерация и управление TOTP QR кодами')
    subparsers = parser.add_subparsers(dest='command', help='Доступные команды')
    
    # Команда создания пользователя
    create_parser = subparsers.add_parser('create', help='Создать TOTP для пользователя')
    create_parser.add_argument('username', help='Имя пользователя')
    create_parser.add_argument('--issuer', '-i', default='MyApp', help='Название приложения (по умолчанию: MyApp)')
    create_parser.add_argument('--storage', '-s', default='totp_data.json', help='Файл для хранения данных')
    
    # Команда проверки токена
    verify_parser = subparsers.add_parser('verify', help='Проверить TOTP токен')
    verify_parser.add_argument('username', help='Имя пользователя')
    verify_parser.add_argument('token', help='TOTP токен для проверки')
    verify_parser.add_argument('--storage', '-s', default='totp_data.json', help='Файл для хранения данных')
    
    # Команда обновления ключа
    update_parser = subparsers.add_parser('update', help='Обновить секретный ключ пользователя')
    update_parser.add_argument('username', help='Имя пользователя')
    update_parser.add_argument('--issuer', '-i', help='Новое название приложения')
    update_parser.add_argument('--storage', '-s', default='totp_data.json', help='Файл для хранения данных')
    
    # Команда удаления пользователя
    delete_parser = subparsers.add_parser('delete', help='Удалить пользователя')
    delete_parser.add_argument('username', help='Имя пользователя')
    delete_parser.add_argument('--storage', '-s', default='totp_data.json', help='Файл для хранения данных')
    
    # Команда списка пользователей
    list_parser = subparsers.add_parser('list', help='Показать всех пользователей')
    list_parser.add_argument('--storage', '-s', default='totp_data.json', help='Файл для хранения данных')
    
    # Команда резервного копирования
    backup_parser = subparsers.add_parser('backup', help='Создать резервную копию данных')
    backup_parser.add_argument('--file', '-f', help='Имя файла для резервной копии')
    backup_parser.add_argument('--storage', '-s', default='totp_data.json', help='Файл для хранения данных')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # Инициализация менеджера с указанным файлом хранения
    manager = TOTPManager(args.storage)
    
    try:
        if args.command == 'create':
            result = manager.create_user_totp(args.username, args.issuer)
            print(f"Статус: {result['status']}")
            print(f"Сообщение: {result['message']}")
            if result['status'] == 'success':
                print(f"Пользователь: {result['username']}")
                print(f"QR код: {result['qr_code_path']}")
                if 'secret_key' in result:
                    print(f"Секретный ключ: {result['secret_key']}")
        
        elif args.command == 'verify':
            result = manager.verify_totp(args.username, args.token)
            print(f"Статус: {result['status']}")
            print(f"Сообщение: {result['message']}")
            if result['status'] == 'success':
                print(f"Токен верный: {result['is_valid']}")
        
        elif args.command == 'update':
            result = manager.update_user_secret(args.username, args.issuer)
            print(f"Статус: {result['status']}")
            print(f"Сообщение: {result['message']}")
            if result['status'] == 'success':
                print(f"Новый QR код: {result['qr_code_path']}")
        
        elif args.command == 'delete':
            result = manager.delete_user(args.username)
            print(f"Статус: {result['status']}")
            print(f"Сообщение: {result['message']}")
        
        elif args.command == 'list':
            result = manager.get_all_users()
            if result['status'] == 'success':
                if result['users']:
                    print("Список пользователей:")
                    for user in result['users']:
                        print(f"- {user['username']}")
                        print(f"  Приложение: {user['issuer_name']}")
                        print(f"  Создан: {user['created_at']}")
                        print(f"  QR код: {user['qr_code_path']}")
                        print()
                else:
                    print("Пользователи не найдены")
            else:
                print(f"Ошибка: {result['message']}")
        
        elif args.command == 'backup':
            result = manager.backup_data(args.file)
            print(f"Статус: {result['status']}")
            print(f"Сообщение: {result['message']}")
    
    except Exception as e:
        print(f"Ошибка при выполнении команды: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
