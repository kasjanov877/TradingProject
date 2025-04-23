import requests
url = url = "https://ordertrans.ru/webhook"
data = {
    "ticker": "SBER",
    "figi": "BBG004730N88",
    "direction": "buy",
    "expected_sum": 3300,
    "price": 305,
    "stop_loss_price": 295,
    "exitComment": "OpenLong"
}
response = requests.post(url, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
