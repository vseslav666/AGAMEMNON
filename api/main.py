import subprocess
import json
import logging
import sys
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

# Добавляем путь к корневой директории проекта для импортов
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Пути к файлам
SCRIPTS_DIR = os.path.join(project_root, 'scripts')
LOGS_DIR = os.path.join(project_root, 'logs')
TOTP_SCRIPT = os.path.join(SCRIPTS_DIR, 'totp.py')

# Создаем папку для логов если ее нет
os.makedirs(LOGS_DIR, exist_ok=True)

# Настройка логирования для каждого метода
def setup_logger(name, log_file):
    """Настройка логгера для конкретного метода"""
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Создаем файловый обработчик
    log_path = os.path.join(LOGS_DIR, log_file)
    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)
    
    # Форматтер для логов
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    return logger

# Создаем логгеры для каждого метода
create_logger = setup_logger('create', 'create.log')
verify_logger = setup_logger('verify', 'verify.log')
update_logger = setup_logger('update', 'update.log')
delete_logger = setup_logger('delete', 'delete.log')
list_logger = setup_logger('list', 'list.log')
backup_logger = setup_logger('backup', 'backup.log')

app = FastAPI(
    title="TOTP Manager API",
    version="1.0.0",
    description="API для управления TOTP QR кодами"
)

class CreateRequest(BaseModel):
    username: str

class VerifyRequest(BaseModel):
    username: str
    token: str

class UpdateRequest(BaseModel):
    username: str

class DeleteRequest(BaseModel):
    username: str

class BackupRequest(BaseModel):
    backup_path: Optional[str] = None

def run_totp_command(command, args, logger):
    """Запускает команду totp.py и логирует результат"""
    try:
        # Проверяем существование скрипта
        if not os.path.exists(TOTP_SCRIPT):
            error_msg = f"TOTP script not found at: {TOTP_SCRIPT}"
            logger.error(error_msg)
            return {
                'success': False,
                'error': error_msg,
                'raw_output': ''
            }
        
        # Формируем полную команду
        full_command = ['python', TOTP_SCRIPT, command] + args
        
        # Логируем запрос
        logger.info(f"Command: {' '.join(full_command)}")
        
        # Выполняем команду из директории скриптов
        result = subprocess.run(
            full_command, 
            capture_output=True, 
            text=True, 
            encoding='utf-8',
            cwd=SCRIPTS_DIR  # Запускаем из директории скриптов
        )
        
        # Логируем вывод
        if result.stdout:
            logger.info(f"Output: {result.stdout.strip()}")
        if result.stderr:
            logger.error(f"Error: {result.stderr.strip()}")
        
        # Парсим вывод для структурированного ответа
        response_data = parse_output(result.stdout)
        response_data['raw_output'] = result.stdout
        response_data['success'] = result.returncode == 0
        
        # Добавляем информацию об ошибке если есть
        if result.returncode != 0 and result.stderr:
            response_data['error'] = result.stderr.strip()
        
        return response_data
        
    except Exception as e:
        error_msg = f"Error executing command: {str(e)}"
        logger.error(error_msg)
        return {
            'success': False,
            'error': error_msg,
            'raw_output': ''
        }

def parse_output(output):
    """Парсит вывод скрипта totp.py в структурированный формат"""
    data = {}
    if not output:
        return data
        
    lines = output.strip().split('\n')
    
    for line in lines:
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip().lower().replace(' ', '_')
            value = value.strip()
            
            # Преобразуем булевы значения
            if value.lower() == 'true':
                value = True
            elif value.lower() == 'false':
                value = False
            elif value.isdigit():
                value = int(value)
                
            data[key] = value
    
    return data

@app.post("/create")
async def create_totp(request: CreateRequest):
    """Создать TOTP для пользователя"""
    result = run_totp_command('create', [request.username], create_logger)
    
    if not result.get('success', False):
        raise HTTPException(
            status_code=400, 
            detail=result.get('error', 'Unknown error occurred')
        )
    
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/verify")
async def verify_totp(request: VerifyRequest):
    """Проверить TOTP токен"""
    result = run_totp_command('verify', [request.username, request.token], verify_logger)
    
    if not result.get('success', False):
        raise HTTPException(
            status_code=400, 
            detail=result.get('error', 'Unknown error occurred')
        )
    
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat()
    }

@app.put("/update")
async def update_totp(request: UpdateRequest):
    """Обновить секретный ключ пользователя"""
    result = run_totp_command('update', [request.username], update_logger)
    
    if not result.get('success', False):
        raise HTTPException(
            status_code=400, 
            detail=result.get('error', 'Unknown error occurred')
        )
    
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat()
    }

@app.delete("/delete")
async def delete_totp(request: DeleteRequest):
    """Удалить пользователя"""
    result = run_totp_command('delete', [request.username], delete_logger)
    
    if not result.get('success', False):
        raise HTTPException(
            status_code=400, 
            detail=result.get('error', 'Unknown error occurred')
        )
    
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/list")
async def list_users():
    """Показать всех пользователей"""
    result = run_totp_command('list', [], list_logger)
    
    if not result.get('success', False):
        raise HTTPException(
            status_code=400, 
            detail=result.get('error', 'Unknown error occurred')
        )
    
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat()
    }

@app.post("/backup")
async def create_backup(request: BackupRequest = None):
    """Создать резервную копию данных"""
    args = []
    if request and request.backup_path:
        args = [request.backup_path]
    
    result = run_totp_command('backup', args, backup_logger)
    
    if not result.get('success', False):
        raise HTTPException(
            status_code=400, 
            detail=result.get('error', 'Unknown error occurred')
        )
    
    return {
        "status": "success",
        "data": result,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Проверка здоровья API и доступности скрипта"""
    script_exists = os.path.exists(TOTP_SCRIPT)
    logs_dir_exists = os.path.exists(LOGS_DIR)
    
    return {
        "status": "healthy" if script_exists else "degraded",
        "totp_script_available": script_exists,
        "logs_directory_available": logs_dir_exists,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/")
async def root():
    """Корневой endpoint с информацией о API"""
    return {
        "message": "TOTP Manager API",
        "project_structure": {
            "scripts_directory": SCRIPTS_DIR,
            "logs_directory": LOGS_DIR,
            "api_directory": os.path.dirname(os.path.abspath(__file__))
        },
        "endpoints": {
            "POST /create": "Создать TOTP для пользователя",
            "POST /verify": "Проверить TOTP токен", 
            "PUT /update": "Обновить секретный ключ пользователя",
            "DELETE /delete": "Удалить пользователя",
            "GET /list": "Показать всех пользователей",
            "POST /backup": "Создать резервную копию данных",
            "GET /health": "Проверка здоровья API"
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
