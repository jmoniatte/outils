# outils

TUI with everyday tools, one tab each: `outils calendar` (the default), `outils weather`,
`outils ip` or `outils life` says which tab it opens on.
It opens as a small pop-up from a status-bar block, so each block opens on the tab it is about.
The calendar shows this month and the next; the weather shows now and the next days, from Open-Meteo; the
IP mode shows what ipinfo.io knows about an address, the public one by default. Life, for fun,
runs Conway's Game of Life.

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
outils ip
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
    __main__.py         # The command line: which tab to open on
    config.py           # Optional ~/.config/outils/config.yaml (theme, through ouikit.config; week_start,
                        # location, units)
    months.py           # The month grids, shift_month and the day labels; no Textual
    weather.py          # Open-Meteo: finding the place, the forecast, the weather codes; no Textual
    life.py             # The Game of Life's rules on a grid that wraps around; no Textual
    ipinfo.py           # ipinfo.io: an address or host name, the public address by default, and the fields shown; no Textual
    widgets/            # One view per mode (calendar_view.py, weather_view.py, ip_view.py, life_view.py); month_view.py draws one month;
                        # lookup_box.py is the box the weather and IP tabs type in
    styles/outils.tcss  # outils's own styles, joined after ouikit's (app.STYLE_FILES)
```

## Modes

Each mode is a tab of the `#modes` `TabbedContent`, under the header; the command line picks the
one it opens on. A click on a tab or `tab` switches; `tab` is an app binding with `priority`, so
the screen's own `tab` (focus next) never runs, and it is skipped while a panel or dialog is up.
The tabs cannot take focus. When a tab shows, `OutilsApp._show_mode` gives focus to a view that
can take it (the calendar, for its arrows, and Life, for `r`) and clears it otherwise, so a hidden view never keeps
it. A view must not focus itself: `TabbedContent` switches to the tab of whatever has focus.
Weather and IP ask their service the first time their tab shows (`on_show`), so opening the
calendar makes no request. The panes are `<mode>-mode`, not the view's own id, which a duplicate
would break.

Every tab sits over the same footer: `OutilsApp.compose` adds `#app-footer`, docked at the
bottom, a rule like the header's (`border-top`) over a Close button on the left that quits.
A view with a `CREDIT`, its words and its site's URL, has it shown in grey at the right, over
the rule (`#mode-credit`), the site as a `Link` that opens it, blue and underlined on hover like
every link: "Weather data by open-meteo.com"
(its CC BY 4.0 license asks for it) and "Data from ipinfo.io". Under the calendar that line is
hidden.
Close cannot take focus, so a click leaves the mode's keys working. App tests patch
`weather_view.forecast` and `ip_view.fetch` so no mode reaches the network.
`MODES` in `app.py` maps each name the command line takes to its tab label and view widget;
the first one is the default. Help lists the view's own `BINDINGS` (`HELP_BINDINGS` is set when
its tab shows) before the app's. A new mode is a view in `widgets/` and an entry in `MODES`;
`__main__` offers it on its own.

## Calendar

`CalendarView` puts `before` + 1 + `after` `MonthView`s side by side (0 and 1 by default), the
month in focus first, under the Previous, Today and Next buttons; it starts on today's
month. `CalendarView.action_shift(delta)` moves them all (Previous, Next, `←` and `→`), and
`show_month` puts any month in focus (Today, which is hidden while today's month is
on show, first or not; hidden with `visible`, so it keeps its place). The buttons cannot take focus, so the calendar keeps it and its keys work after
a click. The button row is as wide as the months (`width: 100%` of an auto-width parent), and
Previous and Next share a width so Today lands in the middle. Each `MonthView` is laid out like
`cal`, with room to read it: every day sits in a four-column cell (its two digits and a space on
each side), so a month is 28 columns wide and two need 58. Top
to bottom: the name centered, a blank row, the day names, a dashed rule under them, then always
`months.WEEKS_SHOWN` (6) week rows, so months side by side line up and a shift never changes
the height. Months sit two columns apart, four with the cells' own space. Time reads from the
colors: days before today are grey (`month--past`), today fills its whole cell in blue
(`month--today`), and what is to come is plain text. Today's month has its name in bold blue
wherever it is in the row (`month--title-current`), and a month wholly past has its name grey
(`month--title-past`). The weekend shows only in the day names (`month--weekend`), so a grey
number always means past. The colors come
from TCSS through `MonthView`'s component classes, so a theme change repaints them with no
`apply_theme` override.

`week_start` in `config.yaml` names the first column, `monday` (the default) to `sunday`, and is
kept as calendar's number (Monday 0). An unknown day is a warning in the header and Monday.

## Weather

`weather.py` talks to Open-Meteo with the standard library (urllib), no account and no key; its
calls block, so `ForecastView.load` runs `weather.forecast` in a worker. Failures raise
`WeatherError`, shown in the view and in the header.

`WeatherView` is a City box over a `ForecastView`. It opens on `location` from `config.yaml`
(`Portland, OR` by default), and Enter in the box looks up what was typed; the forecast on show
stays until the new one comes. Once found, the place replaces the text in the box, in full and
in blue (`ForecastView.Found`, then `LookupBox.show_found`), which is the only place the forecast says
where it is for; clicking the box turns it back to plain text to type over. The app sets `AUTO_FOCUS = None` so the box never takes focus by
itself (it would swallow `?`, `t` and `q`); it has focus only once clicked, and lets go after
Enter or Escape (a `LookupBox` binding, so Escape there does not quit). The IP tab uses the
same box. A typed city is not saved.

A place is "City", or "City" with qualifiers after commas ("City, Region, Country"). `find_place` asks Open-Meteo's
geocoding for the city and `pick_place` chooses among the answers: the exact name first (it lists
Vitória before Victoria), then the most qualifiers, each matching a region, a country or a country code,
in full or by initials ("BC", "Hong Kong" for HK), or a US state or Canadian province by its
postal code (`REGION_CODES`: "OR", "ME", "QC"). A single word never matches by its first letter,
or "ME" would find Multnomah County. A place's own label ("Portland, Maine, United States"), as
the box shows it, finds that place again, so Enter on an untouched box is harmless. The result is cached in
`~/.cache/outils/places.json` (`XDG_CACHE_HOME` respected), keyed by the location text, so opening
the pop-up costs one request. `units` is `metric` (the default) or `imperial`, passed to
Open-Meteo, which converts.

`ForecastView` shows the place, the weather now (icon, temperature, words, then feels like,
wind, humidity and rain), then one row per day for `weather.DAYS` days, today first and the
others by their full day name. Icons are Nerd Font weather glyphs, as ouie uses Nerd Font
battery icons; a clear night gets the moon. The colors come from TCSS through the view's
component classes (high orange, low cyan, rain chance blue).

## IP

`IpView` is an IP box (a `LookupBox`, as on the weather tab) over an `IpDetails`. The first time
it shows, it asks about this computer's public address; Enter in the box asks about what was
typed, and an empty box goes back to this computer's. Once found, the box turns blue and shows
the address, except a host name, which stays as typed (the IP row gives its address), and `IpDetails` shows one row per field in `ipinfo.FIELDS` order, the
address first and in bold blue, skipping
any field ipinfo.io leaves out (and its `readme` link).

`ipinfo.fetch(target)` asks `https://ipinfo.io/json` for this computer's address, or
`https://ipinfo.io/<address>/json` for another (no account, no key), with urllib. ipinfo.io
takes addresses only, so `resolve` turns a host name into one first, with a final dot so the
system's search domain is not tried (a wildcard there answers for any name). A private or
reserved address is refused before any request: ipinfo.io only answers `bogon` for it. Failures
raise `IpInfoError`, shown in red in place of the details and, unlike the other tabs, not in the header. ipinfo.io limits unauthenticated requests
per day, far above what opening a pop-up uses.

## Life

`LifeView` fills its tab with a random grid (`life.DENSITY` of the cells alive) and runs
`life.step` `SPEED` times a second, only while its tab shows (`on_show` and `on_hide` resume and
pause its timer). Each character holds two cells, one over the other, drawn with half blocks
(`▀`, `▄`, `█`), so the cells come out square: an area of 56 by 14 characters is a 56 by 28
grid. The edges wrap around, so gliders come back on the other side. A grid that repeats one of
its last two generations (still or blinking) for `SETTLED_STEPS` is replaced by a new one, as is
the grid after a resize; `r` starts a new one at once. The live cells are green, through the
`life--cell` component class.

## Themes

`t` opens ouikit's theme picker and the choice is saved to `~/.config/outils/config.yaml`; there
is no Settings panel. Anything drawn with Rich instead of TCSS must take its colors from
`BaseApp.palette` and be repainted in an `apply_theme` override.

## Versions

The version comes from git tags via setuptools-scm. Tags have no `v` prefix. Release by
tagging: `git tag 0.1.0`.
