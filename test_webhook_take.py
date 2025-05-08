import requests

url = "http://localhost:5000/webhook"
data = {
    "ticker": "SBER",
    "figi": "BBG004730N88",
    "direction": "sell",
    "position_size_percent": "null",  # Размер позиции в % капитала на счете
    "price": "null",
    "exitComment": "LongTrTake",
}
response = requests.post(url, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
