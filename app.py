from flask import Flask, request, jsonify
from tinkoff.invest import Client, OrderDirection, OrderType, InstrumentType, FindInstrumentRequest

TOKEN = "t.GHari6CScXxN9QAO4FnpEKDY-jwBfqUKWKqUj--J2Ry-Rf7Z2XvqEpWdTXgkfIq0k7-hfCO4ptJBUVYRp0yWWw"

app = Flask(__name__)

account_id = None
# instruments_cache = {}

# Библиотека TICKER => FIGI
ticker_to_figi_library = {
    "SBER" : "BBG004730N88",
}

# Пустая библиотека FIGI => UID
figi_to_uid_library = {}

# Пример добавления значения FIGI и UID
# figi_to_uid_library["BBG004730N88"] = "uid_123456"
# figi_to_uid_library["BBG000B9XRY9"] = "uid_654321"
# В нашему случае
#
# response = client.instruments.find_instrument(query=figi_to_uid_library[ticker_to_figi[ticker]])
#
# Передаем на query нужный uid через нужный figi, что определен ticker'ом
#

def get_instrument_id(client, ticker):
    # Очищаем кэш перед каждым запросом для теста
    # instruments_cache.clear()
    print(f"Кэш очищен перед поиском {ticker}")

    if figi_to_uid_library[ticker_to_figi_library[ticker]] != none:
        return figi_to_uid_library[ticker_to_figi_library[ticker]]

    response = client.instruments.find_instrument(
        query=ticker_to_figi_library[ticker],
        instrument_kind=InstrumentType.INSTRUMENT_TYPE_SHARE,
        api_trade_available_flag=True
    )
    try:
        current_uid = response[0].uid
        print(f"Инструмент TICKER: {ticker} FIGI: {ticker_to_figi_library[ticker]} UID: {current_uid}")
        figi_to_uid_library[ticker_to_figi_library[ticker]] = current_uid
        return current_uid
    except Exception as e:
        print(f"Ошибка при поиске инструмента: {str(e)}")
        return None
    #for instrument in response.instruments:
    #    if instrument.ticker == ticker:
    #        instruments_cache[ticker] = instrument.uid
    #        print(f"Выбран инструмент: {instrument.ticker} с uid {instrument.uid}")
    #        return instrument.uid
    #return None


def place_order(client, ticker, direction, quantity, price=None):
    instrument_id = get_instrument_id(client, ticker)
    if not instrument_id:
        return {"error": f"Инструмент с тикером {ticker} не найден."}

    try:
        if price is not None:
            order_type = OrderType.ORDER_TYPE_LIMIT
            price_dict = {"units": int(price), "nano": 0}
            print(
                f"Размещаем лимитный ордер: instrument_id={instrument_id}, direction={direction}, quantity={quantity}, price={price_dict}, account_id={account_id}")
        else:
            order_type = OrderType.ORDER_TYPE_MARKET
            price_dict = None
            print(
                f"Размещаем рыночный ордер: instrument_id={instrument_id}, direction={direction}, quantity={quantity}, account_id={account_id}")

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