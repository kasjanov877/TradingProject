import json
import os
import logging
from tinkoff.invest import Client, InstrumentIdType

def get_instrument_data(client: Client, figi: str, ticker: str):
    """
    Получает данные об инструменте (instrument_uid, lot) из кэша или API.

    Args:
        client: Клиент Tinkoff API.
        figi: FIGI инструмента.
        ticker: Тикер инструмента.

    Returns:
        tuple: (instrument_uid, lot) или (None, None) при ошибке.
    """
    json_file_path = "tokens_figi_uid.json"
    instrument_data = {}

    try:
        # Загрузка кэша
        if os.path.exists(json_file_path):
            with open(json_file_path, 'r', encoding='utf-8') as json_file:
                instrument_data = json.load(json_file)
            logging.info(f"Loaded instrument data from {json_file_path}")
        else:
            logging.info(f"No instrument data file found at {json_file_path}, starting with empty data")

        # Проверка кэша
        if figi in instrument_data:
            instrument_uid = instrument_data[figi]["instrument_uid"]
            lot = instrument_data[figi]["lot"]
            logging.info(f"Found instrument in cache: figi={figi}, uid={instrument_uid}, lot={lot}")
            return instrument_uid, lot

        # Запрос к API
        instrument = client.instruments.get_instrument_by(
            id_type=InstrumentIdType.INSTRUMENT_ID_TYPE_FIGI, id=figi
        ).instrument
        if not instrument:
            logging.error(f"Instrument not found for FIGI: {figi}")
            return None, None

        instrument_uid = instrument.uid
        lot = instrument.lot
        instrument_data[figi] = {
            "ticker": ticker,
            "instrument_uid": instrument_uid,
            "lot": lot
        }

        # Сохранение кэша
        with open(json_file_path, 'w', encoding='utf-8') as json_file:
            json.dump(instrument_data, json_file, ensure_ascii=False, indent=4)
        logging.info(f"Saved new instrument data: figi={figi}, uid={instrument_uid}, lot={lot}")

        return instrument_uid, lot

    except Exception as e:
        logging.error(f"Error fetching instrument data for FIGI {figi}: {str(e)}")
        return None, None