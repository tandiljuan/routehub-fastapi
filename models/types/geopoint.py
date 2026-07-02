import re
from typing import Annotated
from pydantic import AfterValidator


def format_number(number: str, digits: int) -> str:
    number = float(number)
    patter = '{:+0' + str(digits) + '.7f}'
    return patter.format(number).rstrip('0').rstrip('.')


def format_geo_point(lat: float, lng: float) -> str:
    slat = f"{lat:+011.7f}".rstrip("0").rstrip(".")
    slng = f"{lng:+012.7f}".rstrip("0").rstrip(".")
    return f"{slat}{slng}"


def validate_geo_point(value: str) -> str:
    pattern = r'([+-]?\d{1,2}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)\/?'
    geo_rgx = re.compile(pattern)
    match = geo_rgx.fullmatch(value.strip())

    if not match:
        raise ValueError("invalid ISO 6709 format: use +NN.NNNNNNN+NNN.NNNNNNN/")

    lat = format_number(match.group(1), 11)
    lon = format_number(match.group(2), 12)

    return f"{lat}{lon}"


GeoPoint = Annotated[str, AfterValidator(validate_geo_point)]
