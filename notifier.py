import time
import logging

def notify_error(ticker, sum_value, error_type, error_message):
    """
    Отправляет уведомление об ошибке в консоль.

    Args:
        ticker: Тикер инструмента.
        sum_value: Ожидаемая сумма.
        error_type: Тип ошибки.
        error_message: Сообщение об ошибке.
    """
    try:
        current_time = time.strftime("%Y-%m-%d %H:%M:%S")
        badge = (
            "*** ALERT!!! ***\n"
            f"Ticker: {ticker}\n"
            f"Sum: {str(sum_value)}\n"
            f"Time: {current_time}\n"
            f"Error: {error_type} - {error_message}\n"
            "****************"
        )
        print(badge)
        logging.info(f"Sent notification for {ticker}: {error_type}")
    except Exception as e:
        logging.error(f"Failed to send notification for {ticker}: {str(e)}")