# Импорт библиотеки для отправки HTTP-запросов
import requests

# Тестовый вебхук для закрытия позиции по тейк-профиту
# Отправляет данные на сервер для создания рыночного ордера на продажу
url = "https://ordertrans.ru/webhook"
data = {
    "ticker": "SBER",  # Тикер инструмента
    "figi": "BBG004730N88",  # FIGI инструмента
    "direction": "sell",  # Направление ордера (продажа для закрытия длинной позиции)
    "expected_sum": None,  # Ожидаемая сумма не требуется для закрытия
    "price": 315,  # Цена выхода (signal_price) для идентификации
    "exitComment": "LongTrTake",  # Комментарий, указывающий на закрытие по тейк-профиту
}

# Отправка POST-запроса с данными вебхука
response = requests.post(url, json=data)

# Вывод результата запроса
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
