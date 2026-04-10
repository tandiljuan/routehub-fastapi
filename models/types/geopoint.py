import re
from typing import Annotated
from pydantic import AfterValidator

def format_number(number: str, digits: int) -> str:
    number = float(number)
    patter = '{:+0' + str(digits) + '.7f}'
    return patter.format(number).rstrip('0').rstrip('.')

def validate_geo_point(value: str) -> str:
    pattern = r'([+-]?\d{1,2}(?:\.\d+)?)([+-]\d{1,3}(?:\.\d+)?)\/?'
    geo_rgx = re.compile(pattern)
    match = geo_rgx.fullmatch(value.strip())

    if not match:
        raise ValueError("invalid ISO 6709 format: use +NN.NNNNNNN+NNN.NNNNNNN/")

    lat = format_number(match.group(1), 11)
    lon = format_number(match.group(2), 12)

    return f"{lat}{lon}"

# Define the custom type
GeoPoint = Annotated[str, AfterValidator(validate_geo_point)]
