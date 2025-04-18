import requests
url = "http://localhost:5000/webhook"
data = {
    "ticker": "SBER",
    "figi": "BBG004730N88",
    "direction": "sell",
    "expected_sum": None,
    "price": None,
    "stop_loss_price": None,
    "exitComment": "LongTrTake"
}
response = requests.post(url, json=data)
print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")
