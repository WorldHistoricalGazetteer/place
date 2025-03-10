# dates/dates.py

import re

def year_from_value(date_value, default=None):
    """
    Parses a date string or integer and returns the year as an integer.

    Handles various date string patterns, including:
    - YYYY (e.g., "1999", "-1000", "20231")
    - YYYY-MM (e.g., "2020-12", "-500-01")
    - YYYY-MM-DD (e.g., "1984-07-20", "-200-03-15")
    - YYYY.MM.DD (e.g., "1776.04.04", "10000.01.01")
    - YYYY MM DD (e.g., "2024 01 01", "-1234 12 31")
    - integer (e.g. 1999, -1000, 20231)

    Handles negative years and years with more than four digits.

    Note: This function prioritises efficiency for the given patterns. For more robust and flexible date parsing,
    especially with complex or ambiguous dates, consider using the 'dateutil' library.

    Args:
        date_value (str or int): The date string or integer to parse.
        default (int, optional): The value to return if parsing fails. Defaults to None.

    Returns:
        int: The year as an integer, or the default value if parsing fails.

    Examples:
        >>> year_from_value("1999")
        1999
        >>> year_from_value("2020-12")
        2020
        >>> year_from_value("1984-07-20")
        1984
        >>> year_from_value("1776.04.04")
        1776
        >>> year_from_value("2024 01 01")
        2024
        >>> year_from_value("-1000")
        -1000
        >>> year_from_value("20231")
        20231
        >>> year_from_value("")
        None
        >>> year_from_value("invalid", default=0)
        0
        >>> year_from_value(1999)
        1999
        >>> year_from_value(-1000)
        -1000
    """
    if isinstance(date_value, int):
        return date_value
    if not date_value: # empty string or None
        return default
    try:
        return int(re.split(r"[ .]|(?<!^)-", date_value)[0])
    except (ValueError, IndexError):
        return default