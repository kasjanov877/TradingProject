# Импорт необходимых библиотек
import json
from http.client import responses

from flask import Flask, request, jsonify  # Веб-фреймворк и инструменты для работы с HTTP
from tinkoff.invest import Client, OrderDirection, OrderType, InstrumentIdType, \
    InstrumentRequest, MoneyValue, Quotation  # Официальный SDK Тинькофф Инвестиций
from tinkoff.invest.sandbox.client import SandboxClient

# Токен доступа к API Тинькофф Инвестиций (SANDBOX)
TOKEN = "t.Gk6qrpcVv87MYW8ZPgUOO7dKVV-GLQKtKAeymLEmZaGA6UTi9LseC0zvkCZ4GrgRdnrNFxfuwTgjT1V4xV-oJA"

# Инициализация Flask приложения
app = Flask(__name__)
account_id = None  # Здесь будет храниться ID песочного аккаунта
ticker_to_figi_uid_library = {}  # Словарь для соответствия тикеров и идентификаторов инструментов


def initialize_libraries(tokens_to_figis_file):
    """Загружает данные из JSON-файла в глобальный словарь ticker_to_figi_uid_library"""
    with open(tokens_to_figis_file, 'r', encoding='utf-8') as json_file:
        global ticker_to_figi_uid_library
        ticker_to_figi_uid_library = json.load(json_file)


def get_full_instrument(client, ticker):
    """Получает полную информацию об инструменте по тикеру через API"""
    # Проверка наличия тикера в библиотеке
    if ticker not in ticker_to_figi_uid_library:
        print(f"Тикер {ticker} не найден в библиотеке")
        return None

    figi = ticker_to_figi_uid_library[ticker]["figi"]

    try:
        # Запрос к API Тинькофф
        response_full = client.instruments.get_instrument_by(
            id_type = InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI,
            id=figi
        )
        instrument = response_full.instrument
        if instrument:
            print(
                f"Инструмент найден: TICKER={instrument.ticker} FIGI={instrument.figi}, LOT={instrument.lot}, UID={instrument.uid}")
            return instrument
        else:
            print(f"Инструмент с TICKER={ticker}, FIGI={figi} не найден.")
            return None
    except Exception as e:
        print(f"Ошибка при запросе полного инструмента: {str(e)}")
        return None


def get_quantity(expected_sum, instrument_lot, price=None):
    """Рассчитывает количество лотов для ордера"""
    try:
        if price is not None:
            # Для лимитных ордеров: рассчитываем количество на основе цены
            price_val = float(price.units)
            units = expected_sum / price_val
            quantity = int(units) // instrument_lot * instrument_lot
        else:
            # Для рыночных ордеров: используем ожидаемую сумму напрямую
            quantity = int(expected_sum) // instrument_lot * instrument_lot

        # Проверка минимального количества
        if quantity <= 0:
            print(f"Рассчитанное количество лотов меньше или равно 0 = {quantity}")
            return 0

        return quantity
    except Exception as e:
        print(f"Ошибка при расчёте количества: {str(e)}")
        return 0


def place_order(client, ticker, direction, expected_sum, price=None):
    """Размещает ордер через API Тинькофф"""
    current_instrument = get_full_instrument(client, ticker)
    if current_instrument is None:
        return {"error": "Не найден инструмент"}, 400

    # Расчет количества лотов
    quantity = get_quantity(expected_sum, current_instrument.lot, price)

    try:
        # Определение типа ордера (рыночный/лимитный)
        if price is not None:
            order_type = OrderType.ORDER_TYPE_LIMIT
            print(f"Размещаем лимитный ордер с ценой {price}...")
        else:
            order_type = OrderType.ORDER_TYPE_MARKET
            price_value = None
            print(f"Размещаем рыночный ордер...")

        # Отправка ордера в песочницу
        response = client.orders.post_order(
            instrument_id=current_instrument.uid,
            quantity=quantity,
            direction=direction,
            account_id=account_id,
            order_type=order_type,
            price=price if order_type == OrderType.ORDER_TYPE_LIMIT else None
        )
        print(f"Ордер успешно размещён: {response}")
        return {"order_id": response.order_id}
    except Exception as e:
        print(f"Ошибка при размещении ордера: {str(e)}")
        return {"error": str(e)}


@app.route('/webhook', methods=['POST'])
def webhook():
    """Обработчик входящих вебхуков"""
    data = request.json
    print("Received webhook data:", data)

    # Извлечение параметров из запроса
    ticker = data.get("ticker")
    direction = data.get("direction")
    price_value = data.get("price")

    # Преобразуем цену в float для точности
    price_float = float(price_value)

    # Получаем целую часть и дробную (нано-часть)
    units = int(price_float)
    nano = round((price_float - units) * 1_000_000)

    # Создаем объект Quotation
    price = Quotation(
        units=units,
        nano=nano
    )
    print(price)
    expected_sum = int(data.get("expected_sum"))

    # Валидация входных данных
    if not direction or not expected_sum or not ticker:
        return jsonify({"error": "Недостаточно данных"}), 400

    # Преобразование направления ордера
    if direction.lower() == "buy":
        direction_order = OrderDirection.ORDER_DIRECTION_BUY
    elif direction.lower() == "sell":
        direction_order = OrderDirection.ORDER_DIRECTION_SELL
    else:
        return jsonify({"error": "Неподдерживаемое направление"}), 400

    # Размещение ордера через SDK
    with SandboxClient(TOKEN) as client:
        result = place_order(client, ticker, direction_order, expected_sum, price)
        if "error" in result:
            return jsonify(result), 400
        return jsonify(result)


def initialize_sandbox_account(client):
    global account_id
    accounts = client.sandbox.get_sandbox_accounts()

    # Проверка наличия хотя бы одного аккаунта
    if accounts.accounts:
        # Если аккаунт есть, подключаемся к первому найденному
        account_id = accounts.accounts[0].id
        print(f"Подключено к существующему счету: {account_id}")

        balance = client.sandbox.sandbox_pay_in(
            account_id=account_id,
            amount={"units": 0, "nano": 0}
        )
        print(f"Баланс: {balance}")

    else:
        # Если аккаунтов нет, создаем новый и пополняем его
        sandbox_account = client.sandbox.open_sandbox_account()
        account_id = sandbox_account.account_id
        print(f"Создан новый счет: {account_id}")
        # Пополнение баланса
        client.sandbox.sandbox_pay_in(
            account_id=account_id,
            amount=MoneyValue(units=200000, nano=0, currency="rub")  # 200 000 рублей
        )
        print(f"Добавлены средства на счет {account_id}")

def main():
    """Основная функция инициализации"""
    global account_id

    # Инициализация библиотеки тикеров
    initialize_libraries('tokens_figi_uid.json')

    # Работа с песочными аккаунтами
    with SandboxClient(TOKEN) as client:
        initialize_sandbox_account(client) # Инициализация аккаунта песочницы

    # Запуск веб-сервера
    app.run(host='0.0.0.0', port=5000)

if __name__ == "__main__":
    main()