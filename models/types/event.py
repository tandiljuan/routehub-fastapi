import re
from typing import Annotated
from pydantic import AfterValidator
from icalendar import Event as iEvent
from dateutil.rrule import rrulestr

def validate_ical_event(event: str) -> str:
    pattern = r'(?P<key>[A-Z-]+)(?:;(?P<par>[^:\r\n]+))?(?::(?P<val>.*))?(?:\r?\n)*'
    mandatory_keys = [
        'DTSTART',
    ]
    valid_keys = mandatory_keys + [
        'DTEND',
        'DURATION',
        'RRULE',
        'RDATE',
        'EXRULE',
        'EXDATE',
    ]
    result = ''

    for match in re.finditer(pattern, event.strip()):
        key = match.group('key')
        if key in valid_keys:
            result += match.group(0).strip() + "\r\n"
            if key in mandatory_keys:
                mandatory_keys.remove(key)

    result = result.strip()
    errmsg = []

    if 0 < len(mandatory_keys):
        msg = 'Missing mandatory key'
        msg += ' ' if 1 == len(mandatory_keys) else 's '
        msg += ', '.join(mandatory_keys)
        errmsg.append(msg)

    if re.search('DTEND', result) \
    and re.search('DURATION', result):
        msg = 'DTEND and DURATION are mutually exclusive'
        errmsg.append(msg)

    if not len(errmsg):

        # Wrap inside a VEVENT container
        wrapped = (
            "BEGIN:VEVENT\r\n"
            f"{result}\r\n"
            "END:VEVENT\r\n"
        )

        try:
            vevent = iEvent.from_ical(wrapped)
            if len(vevent.errors):
                for e in vevent.errors:
                    errmsg.append(f"{e[0]}: {e[1]}")
        except Exception as e:
            errmsg.append(f"{key}: {e}")

        for key in ['RRULE', 'EXRULE']:
            if key in vevent:
                rr = vevent.get(key).to_ical().decode()
                try:
                    rrulestr(f"RRULE:{rr}")
                except Exception as e:
                    errmsg.append(f"{key}: {e}")

    if len(errmsg):
        raise ValueError(".\n".join(errmsg))

    return result

# Define the custom type
Event = Annotated[str, AfterValidator(validate_ical_event)]
