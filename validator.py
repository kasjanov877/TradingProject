from notifier import notify_error


def validate_webhook_data(
    ticker, figi, direction, expected_sum, exit_comment, signal_price
):
    missing_or_invalid = []
    if not ticker:
        missing_or_invalid.append("ticker")
    if not figi:
        missing_or_invalid.append("figi")
    if not direction:
        missing_or_invalid.append("direction")
    if signal_price is None:
        missing_or_invalid.append("signal_price")

    if exit_comment is None or exit_comment == "":
        error_message = "exitComment is required and cannot be empty"
        notify_error(
            ticker or "Unknown",
            expected_sum or "N/A",
            "MissingExitComment",
            error_message,
        )
        return False, error_message

    valid_exit_comments = [
        "OpenLong",
        "OpenShort",
        "LongStop",
        "ShortStop",
        "LongTrTake",
        "ShortTrTake",
    ]
    if exit_comment not in valid_exit_comments:
        error_message = f"Недопустимое значение exitComment: {exit_comment}. Допустимые: {valid_exit_comments}"
        notify_error(
            ticker or "Unknown",
            expected_sum or "N/A",
            "InvalidExitComment",
            error_message,
        )
        return False, error_message

    if exit_comment in ["LongStop", "ShortStop", "LongTrTake", "ShortTrTake"]:
        if missing_or_invalid:
            error_message = f"Недопустимые значения в полях для закрытия: {', '.join(missing_or_invalid)}"
            notify_error(
                ticker or "Unknown", expected_sum or "N/A", "MissingData", error_message
            )
            return False, error_message
    else:
        if not expected_sum:
            missing_or_invalid.append("expected_sum")
        if missing_or_invalid:
            error_message = f"Недопустимые значения в полях для открытия: {', '.join(missing_or_invalid)}"
            notify_error(
                ticker or "Unknown", expected_sum or "N/A", "MissingData", error_message
            )
            return False, error_message
        try:
            expected_sum = int(expected_sum)
            signal_price = float(signal_price)
        except ValueError as e:
            notify_error(ticker, expected_sum or "N/A", "ValueError", str(e))
            return False, f"Ошибка валидации: {str(e)}"

    if direction not in ["buy", "sell"]:
        error_message = f"Неподдерживаемое направление: {direction}"
        notify_error(
            ticker or "Unknown",
            expected_sum or "N/A",
            "InvalidDirection",
            error_message,
        )
        return False, error_message

    return True, (expected_sum, exit_comment, signal_price)
