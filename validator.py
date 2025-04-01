from notifier import notify_error

def validate_webhook_data(ticker, figi, direction, expected_sum, exit_comment, price):
    missing_or_invalid = []
    if not ticker:
        missing_or_invalid.append("ticker")
    if not figi:
        missing_or_invalid.append("figi")
    if not direction:
        missing_or_invalid.append("direction")

    if exit_comment:  # Закрытие
        if missing_or_invalid:
            error_message = f"Недопустимые значения в полях для закрытия: {', '.join(missing_or_invalid)}"
            notify_error(ticker or "Unknown", expected_sum or "N/A", "MissingData", error_message)
            return False, error_message
    else:  # Открытие
        if not expected_sum:
            missing_or_invalid.append("expected_sum")
        if not price:
            missing_or_invalid.append("price")  # Требуем price для открытия
        if missing_or_invalid:
            error_message = f"Недопустимые значения в полях для открытия: {', '.join(missing_or_invalid)}"
            notify_error(ticker or "Unknown", expected_sum or "N/A", "MissingData", error_message)
            return False, error_message
        try:
            expected_sum = int(expected_sum)
            price = float(price)  # Преобразуем price в число
        except ValueError as e:
            notify_error(ticker, expected_sum or "N/A", "ValueError", str(e))
            return False, "expected_sum и price должны быть числами"

    if direction not in ["buy", "sell"]:
        error_message = f"Неподдерживаемое направление: {direction}"
        notify_error(ticker or "Unknown", expected_sum or "N/A", "InvalidDirection", error_message)
        return False, error_message

    return True, (expected_sum, exit_comment, price)