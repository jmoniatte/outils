"""Draw a QR code in text, two rows of modules per line of half blocks."""

import segno
from segno import helpers

from .nmcli import Share

# One light module around the code: less than the spec's four, but phones read it against the dark panel
BORDER = 1
_BLOCKS = {(True, True): "█", (True, False): "▀", (False, True): "▄", (False, False): " "}


def wifi_qr(share: Share) -> tuple[str, ...]:
    """The code phones read to join a network, as lines meant to be drawn dark on light."""
    data = helpers.make_wifi_data(share.ssid, share.password or None, share.qr_security)
    rows = [[bool(module) for module in row] for row in segno.make(data, error="l").matrix_iter(border=BORDER)]
    if len(rows) % 2:
        rows.append([False] * len(rows[0]))
    return tuple(
        "".join(_BLOCKS[(top, bottom)] for top, bottom in zip(rows[index], rows[index + 1]))
        for index in range(0, len(rows), 2)
    )
