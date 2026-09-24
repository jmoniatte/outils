from textual.widgets import Static


class CalendarView(Static):
    """The calendar mode; not built yet."""

    def __init__(self) -> None:
        super().__init__("Calendar: not built yet", classes="mode-placeholder")
