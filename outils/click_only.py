from typing import TypeVar

from textual.widget import Widget
from textual.widgets import Button

W = TypeVar("W", bound=Widget)


def click_only(widget: W) -> W:
    """widget, which a click must not give focus to, so the view keeps it for its keys."""
    widget.can_focus = False
    return widget


def quick_button(label: str, id: str) -> Button:
    """A click_only button that takes every click: Textual ignores clicks during the press flash, so it has none."""
    button = click_only(Button(label, id=id))
    button.active_effect_duration = 0
    return button
