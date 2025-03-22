from tinkoff.invest import Client, OrderDirection, OrderType
from flask import Flask, request, jsonify

# Ваш токен доступа
TOKEN = "t.GHari6CScXxN9QAO4FnpEKDY-jwBfqUKWKqUj--J2Ry-Rf7Z2XvqEpWdTXgkfIq0k7-hfCO4ptJBUVYRp0yWWw"

# Создаем Flask-приложение для обработки вебхуков
app = Flask(__name__)

# Глобальные переменные для хранения данных о счёте и инструментах
account_id = None
instruments_cache = {}  # Кэш для хранения информации об инструментах

# Функция для получения instrument_id по тикеру
def get_instrument_id(client, ticker):
    if ticker in instruments_cache:
        return instruments_cache[ticker]

    instruments = client.instruments.shares()
    for instrument in instruments.instruments:
        if instrument.ticker == ticker:
            instruments_cache[ticker] = instrument.uid
            return instrument.uid
    return None

# Функция для размещения ордера
def place_order(client, ticker, direction, quantity):
    instrument_id = get_instrument_id(client, ticker)
    if not instrument_id:
        return {"error": f"Инструмент с тикером {ticker} не найден."}

    try:
        response = client.orders.post_order(
            instrument_id=instrument_id,
            quantity=quantity,
            direction=direction,
            account_id=account_id,
            order_type=OrderType.MARKET,
        )
        return {"order_id": response.order_id}
    except Exception as e:
        return {"error": str(e)}

# Обработчик вебхука от TradingView
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Received webhook data:", data)

    ticker = data.get("ticker")
    direction = data.get("direction")
    position_size = data.get("position_size")

    if not direction or not position_size or not ticker:
        return jsonify({"error": "Недостаточно данных в вебхуке: требуется direction, position_size и ticker."}), 400

    if direction.lower() == "buy":
        direction_order = OrderDirection.BUY
    elif direction.lower() == "sell":
        direction_order = OrderDirection.SELL
    else:
        return jsonify({"error": "Неподдерживаемое направление: " + direction}), 400

    quantity = position_size

    with Client(TOKEN) as client:
        result = place_order(client, ticker, direction_order, quantity)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

# Основной процесс
def main():
    global account_id

    with Client(TOKEN) as client:
        # Шаг 1: Проверяем существующие песочные аккаунты
        accounts = client.sandbox.get_sandbox_accounts()
        print("Существующие песочные аккаунты:", accounts)

        if accounts.accounts:
            # Если аккаунты есть, закрываем их все
            for acc in accounts.accounts:
                print(f"Закрываем аккаунт: {acc.id}")
                client.sandbox.close_sandbox_account(account_id=acc.id)
        
        # Шаг 2: Создаём новый аккаунт после очистки
        sandbox_account = client.sandbox.open_sandbox_account()
        account_id = sandbox_account.account_id
        print(f"Создан новый счет: {account_id}")

    # Запускаем Flask-сервер для обработки вебхуков
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()