# Импорт библиотек для шифрования и работы с Tinkoff API
from cryptography.fernet import Fernet  # Для симметричного шифрования токена
from cryptography.hazmat.primitives.kdf.pbkdf2 import (
    PBKDF2HMAC,
)  # Для генерации ключа из пароля
from cryptography.hazmat.primitives import hashes  # Для хэширования
import base64  # Для кодирования ключа
import os  # Для работы с файлами
import subprocess  # Для вызова shred
from tinkoff.invest import Client  # Клиент Tinkoff API
from tinkoff.invest.constants import INVEST_GRPC_API  # Константа для API


def load_token():
    """Загружает и расшифровывает токен Tinkoff API, затем безопасно удаляет файл."""
    # Путь к зашифрованному токену на сервере
    token_file = "/root/encrypted_token.bin"

    # Запрос пароля с консоли сервера
    password = input("Enter decryption password: ").encode()

    # Генерация ключа из пароля
    salt = b"salt_TradingProject"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password))
    fernet = Fernet(key)

    try:
        # Чтение и расшифровка токена
        with open(token_file, "rb") as f:
            encrypted_token = f.read()
        token = fernet.decrypt(encrypted_token).decode()

        # Безопасное удаление файла после успешной расшифровки
        subprocess.run(["shred", "-u", token_file], check=True)
        return token
    except Exception as e:
        raise Exception(f"Error decrypting token: {str(e)}")


# Глобальный токен доступа к API Тинькофф
TOKEN = load_token()


def initialize_account(token: str):
    """
    Инициализирует подключение к аккаунту с использованием реального токена.

    Аргументы:
        token (str): Токен доступа к API.

    Возвращает:
        account_id (str): Идентификатор аккаунта или None в случае ошибки.
    """
    try:
        with Client(token, target=INVEST_GRPC_API) as client:
            # Получаем список всех аккаунтов
            accounts = client.users.get_accounts()

            if accounts.accounts:
                # Если есть хотя бы один аккаунт, используем первый
                account_id = accounts.accounts
                print(f"Подключено к реальному счету: {account_id}")
                return account_id
            else:
                # Если аккаунтов нет, возвращаем None
                print("Аккаунт не найден.")
                return None
    except Exception as e:
        print(f"Ошибка при инициализации аккаунта: {str(e)}")
        return None


# Тестирование инициализации аккаунта при прямом запуске файла
if __name__ == "__main__":
    account_id = initialize_account(TOKEN)
    if account_id:
        print(f"Успешно инициализирован аккаунт: {account_id}")
    else:
        print("Не удалось инициализировать аккаунт.")
