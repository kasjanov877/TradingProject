# Импорт модуля для уведомлений об ошибках
from notifier import notify_error


# Функция валидации данных вебхука
def validate_webhook_data(
    ticker, figi, direction, position_size_percent, exit_comment, signal_price
):
    missing_or_invalid = []

    # Проверка обязательных полей для всех операций
    if not ticker:
        missing_or_invalid.append("ticker")
    if not figi:
        missing_or_invalid.append("figi")
    if not direction:
        missing_or_invalid.append("direction")
    if signal_price is None:
        missing_or_invalid.append("signal_price")

    # Проверка поля exitComment
    valid_exit_comments = [
        "OpenLong",
        "OpenShort",
        "LongStop",
        "ShortStop",
        "LongTrTake",
        "ShortTrTake",
    ]
    if exit_comment is None or exit_comment == "":
        error_message = "exitComment is required and cannot be empty"
        notify_error(
            ticker or "Unknown",
            position_size_percent or "N/A",
            "MissingExitComment",
            error_message,
        )
        return False, error_message
    if exit_comment not in valid_exit_comments:
        error_message = f"Недопустимое значение exitComment: {exit_comment}. Допустимые: {valid_exit_comments}"
        notify_error(
            ticker or "Unknown",
            position_size_percent or "N/A",
            "InvalidExitComment",
            error_message,
        )
        return False, error_message

    # Дополнительная валидация в зависимости от типа операции
    if exit_comment in ["LongStop", "ShortStop", "LongTrTake", "ShortTrTake"]:
        if position_size_percent is not None:
            missing_or_invalid.append(
                "position_size_percent (should be null for closing)"
            )
        if missing_or_invalid:
            error_message = f"Недопустимые значения в полях для закрытия: {', '.join(missing_or_invalid)}"
            notify_error(
                ticker or "Unknown",
                position_size_percent or "N/A",
                "MissingData",
                error_message,
            )
            return False, error_message
    else:
        if position_size_percent is None:
            missing_or_invalid.append("position_size_percent")
        if missing_or_invalid:
            error_message = f"Недопустимые значения в полях для открытия: {', '.join(missing_or_invalid)}"
            notify_error(
                ticker or "Unknown",
                position_size_percent or "N/A",
                "MissingData",
                error_message,
            )
            return False, error_message
        try:
            position_size_percent = float(position_size_percent)
            signal_price = float(signal_price)
            if position_size_percent <= 0:
                error_message = f"position_size_percent должен быть больше 0, получено: {position_size_percent}"
                notify_error(
                    ticker or "Unknown",
                    position_size_percent,
                    "InvalidPercent",
                    error_message,
                )
                return False, error_message
        except ValueError as e:
            notify_error(ticker, position_size_percent or "N/A", "ValueError", str(e))
            return False, f"Ошибка валидации: {str(e)}"

    # Проверка направления ордера
    if direction not in ["buy", "sell"]:
        error_message = f"Неподдерживаемое направление: {direction}"
        notify_error(
            ticker or "Unknown",
            position_size_percent or "N/A",
            "InvalidDirection",
            error_message,
        )
        return False, error_message

    # Возвращение валидированных данных
    return True, (position_size_percent, exit_comment, signal_price)
