# outils

TUI with everyday tools, one mode per run: `outils calendar` (the default) or `outils weather`.
It opens as a small pop-up from a status-bar block, so each block opens the mode it is about.
Only the shell exists so far: the header, a placeholder view per mode, Help and the theme picker.

It is built on [ouikit](https://github.com/jmoniatte/ouikit), shared with ouie, ouifi, flotte
and yafyaf-tui: the themes and the picker (`t`), the header and its messages, Help (`?`), the
dialogs and the startup check all come from there. Put what every app would use
in ouikit, not here; see its AGENTS.md. Like the other apps it draws no border around the
screen, and every message, errors included, goes to the header.

## Rules

- Do not git commit unless asked
- Keep the shortcuts few: the ones on the Help panel are the whole set
- The help screen lists every binding that has a description and a `group`
  (`ouikit.shortcuts.ACTIONS` or `GENERAL`) in `OutilsApp.HELP_BINDINGS` and
  `OutilsApp.BINDINGS`; document a new key there
- Never hardcode a color in a `.tcss` file

## Run

```bash
outils            # the calendar
outils weather
```

It refuses to start unless stdin and stdout are a terminal (ouikit's `start`).

## Test

Run both from the git root.

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
```

There is no pytest. `ruff` is pinned in the `dev` dependency group, so use `uv run ruff`.
ouikit comes from GitHub's master (`[tool.uv.sources]`); after a push there,
`uv lock --upgrade-package ouikit` picks it up. To work on both at once, switch that source to
the commented-out `../ouikit` path.

## Structure

```
outils/                 # git root + pyproject.toml (run uv commands here)
  outils/               # Python package
    app.py              # OutilsApp, an ouikit BaseApp: MODES, the header, the keys
    __main__.py         # The command line: which mode to open
    config.py           # Optional ~/.config/outils/config.yaml (theme, through ouikit.config)
    widgets/            # One view per mode: calendar_view.py, weather_view.py
    styles/outils.tcss  # outils's own styles, joined after ouikit's (app.STYLE_FILES)
```

## Modes

One mode per run, no tabs: switching means closing the pop-up and opening the other one.
`MODES` in `app.py` maps each name the command line takes to its header label and view widget;
the first one is the default. The header shows the label on the right (`#mode-name`), and Help
lists the view's own `BINDINGS` (`HELP_BINDINGS` is set per mode) before the app's. A new mode
is a view in `widgets/` and an entry in `MODES`; `__main__` offers it on its own.

## Themes

`t` opens ouikit's theme picker and the choice is saved to `~/.config/outils/config.yaml`; there
is no Settings panel. Anything drawn with Rich instead of TCSS must take its colors from
`BaseApp.palette` and be repainted in an `apply_theme` override.

## Versions

The version comes from git tags via setuptools-scm. Tags have no `v` prefix. Release by
tagging: `git tag 0.1.0`.
