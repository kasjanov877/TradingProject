import os
from tinkoff.invest import Client
from tinkoff.invest.constants import INVEST_GRPC_API
# Глобальный токен доступа к API Тинькофф
TOKEN = os.getenv("API_TOKEN")

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

# Если файл запускается напрямую (для тестирования)

if __name__ == "__main__":
    account_id = initialize_account(TOKEN)
    if account_id:
        print(f"Успешно инициализирован аккаунт: {account_id}")
    else:
        print("Не удалось инициализировать аккаунт.")