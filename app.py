from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType, InstrumentType

TOKEN = "t.7zly2sSg895J9ZdZCyQUAZEwMzNhOOflnsN6JQ_GSbyQUPOTnkCL7cuPAFV8Z71sTbSdCFfs-V9IpDIDYqwN1w"
app = Flask(__name__)

account_id = None
instruments_cache = {}

def get_instrument_id(client, ticker):
    # Очищаем кэш перед каждым запросом для теста
    instruments_cache.clear()
    print(f"Кэш очищен перед поиском {ticker}")

    response = client.instruments.find_instrument(
        query=ticker,
        instrument_kind=InstrumentType.INSTRUMENT_TYPE_SHARE,
        api_trade_available_flag=True
    )
    print(f"Найденные инструменты для {ticker}: {response.instruments}")
    for instrument in response.instruments:
        if instrument.ticker == ticker:
            instruments_cache[ticker] = instrument.uid
            print(f"Выбран инструмент: {instrument.ticker} с uid {instrument.uid}")
            return instrument.uid
    return None

def place_order(client, ticker, direction, quantity, price=None):
    instrument_id = get_instrument_id(client, ticker)
    if not instrument_id:
        return {"error": f"Инструмент с тикером {ticker} не найден."}

    try:
        if price is not None:
            order_type = OrderType.ORDER_TYPE_LIMIT
            price_dict = {"units": int(price), "nano": 0}
            print(f"Размещаем лимитный ордер: instrument_id={instrument_id}, direction={direction}, quantity={quantity}, price={price_dict}, account_id={account_id}")
        else:
            order_type = OrderType.ORDER_TYPE_MARKET
            price_dict = None
            print(f"Размещаем рыночный ордер: instrument_id={instrument_id}, direction={direction}, quantity={quantity}, account_id={account_id}")

        response = client.orders.post_order(
            instrument_id=instrument_id,
            quantity=quantity,
            direction=direction,
            account_id=account_id,
            order_type=order_type,
            price=price_dict if order_type == OrderType.ORDER_TYPE_LIMIT else None
        )
        print(f"Ордер успешно размещён: {response}")
        return {"order_id": response.order_id}
    except Exception as e:
        print(f"Ошибка при размещении ордера: {str(e)}")
        return {"error": str(e)}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print("Received webhook data:", data)

    ticker = data.get("ticker")
    direction = data.get("direction")
    position_size = data.get("position_size")
    price = data.get("price")

    if not direction or not position_size or not ticker:
        return jsonify({"error": "Недостаточно данных в вебхуке: требуется direction, position_size и ticker."}), 400

    if direction.lower() == "buy":
        direction_order = OrderDirection.ORDER_DIRECTION_BUY
    elif direction.lower() == "sell":
        direction_order = OrderDirection.ORDER_DIRECTION_SELL
    else:
        return jsonify({"error": "Неподдерживаемое направление: " + direction}), 400

    quantity = int(position_size)

    with Client(TOKEN) as client:
        result = place_order(client, ticker, direction_order, quantity, price)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)

def main():
    global account_id

    with Client(TOKEN) as client:
        accounts = client.sandbox.get_sandbox_accounts()
        print("Существующие песочные аккаунты:", accounts)

        if accounts.accounts:
            for acc in accounts.accounts:
                print(f"Закрываем аккаунт: {acc.id}")
                client.sandbox.close_sandbox_account(account_id=acc.id)
        
        sandbox_account = client.sandbox.open_sandbox_account()
        account_id = sandbox_account.account_id
        print(f"Создан новый счет: {account_id}")

        client.sandbox.sandbox_pay_in(account_id=account_id, amount={"units": 200000, "nano": 0})
        print(f"Добавлено 100,000 рублей на счёт {account_id}")

    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()