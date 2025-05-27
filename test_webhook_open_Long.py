# Импорт библиотеки для отправки HTTP-запросов
import requests

# Тестовый вебхук для открытия длинной позиции
# Отправляет данные на сервер для создания рыночного ордера на покупку
url = "https://ordertrans.ru/webhook"
data = {
    "ticker": "GAZP",  # Тикер инструмента
    "figi": "BBG004730RP0",  # FIGI инструмента
    "direction": "buy",  # Направление ордера (покупка)
    "position_size_percent": 5,  # Размер позиции в % капитала на счете
    "price": 139,  # Цена входа (signal_price) для идентификации
    "exitComment": "OpenLong",  # Комментарий, указывающий на открытие длинной позиции
}

# Отправка POST-запроса с данными вебхука
response = requests.post(url, json=data)

# Вывод результата запроса
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
