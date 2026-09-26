# outils

TUI with everyday tools, one tab each: `outils calendar` (the default), `outils time`,
`outils weather`, `outils ip`, `outils sound`, `outils wifi`, `outils dropbox`, `outils life` or `outils snake` says which tab it opens on.
It opens as a small pop-up from a status-bar block, so each block opens on the tab it is about.
The calendar shows this month and the next; the time, the time now in a few places and an epoch converter; the weather
shows now and the next days, from Open-Meteo; the IP mode shows what ipinfo.io knows about an address, the public one by default; Dropbox starts
or stops the Dropbox client on this computer and shows the files that changed last; Sound, the
outputs and microphones through `pactl`, a simplified pavucontrol; Wi-Fi, the networks through
NetworkManager's `nmcli`. Life, for fun,
runs Conway's Game of Life, and Snake is the game of snake.

It is built on [tui-kit](https://github.com/jmoniatte/tui-kit), shared with flotte
and yafyaf-tui: the themes and the picker (`t`), the messages, Help (`?`), the
dialogs and the startup check all come from there. Put what every app would use
in tui-kit, not here; see its AGENTS.md. Like the other apps it draws no border around the
screen. Unlike them it has no title bar (tui-kit's `AppHeader`): the tabs are the first row, and
every message, errors included, goes to the footer, in Help's place (see Modes).

## Rules

- Do not git commit unless asked
- Keep the shortcuts few: the ones on the Help panel are the whole set
- The help screen lists every binding that has a description and a `group`
  (`tui_kit.shortcuts.ACTIONS` or `GENERAL`) in `OutilsApp.BINDINGS` and in the tab's view's
  `BINDINGS` (or its `HELP_BINDINGS`); document a new key there
- Never hardcode a color in a `.tcss` file

## Run

```bash
outils            # the calendar
outils time
outils weather
outils ip
outils sound
outils wifi
outils dropbox
outils life
outils snake
```

It refuses to start unless stdin and stdout are a terminal (tui-kit's `start`).

`outils --show <mode>` starts nothing: it asks an outils already running to show that tab
(`remote.py`), and exits 0 when it switched, 2 when that tab was on show already, 1 when no outils
answers. The one started from the command line listens on a Unix socket, `remote.SOCKET`
(`$XDG_RUNTIME_DIR/outils.sock`), through `asyncio.start_unix_server` in `OutilsApp.on_mount`,
and removes it on unmount; a second outils finds the first listening and does without
(`remote.free`), and a socket file left by a crash is removed by the next `--show` or start.
`OutilsApp.show_mode` closes any panel or dialog, then switches. Tests leave `socket_path` at
None, so they never listen, except `test_remote.py`, on a temporary path. The status-bar blocks
call a script in the dotfiles (`i3blocks/scripts/outils-open <mode>`) that shows the pop-up after
a switch, hides or shows it on the tab already on show, and starts outils when none runs.

## Test

Run both from the git root.

```bash
uv run python -m unittest discover -s tests
uv run ruff check .
```

There is no pytest. A view's tests show it alone in `tests/host.py`'s `Host`, in outils's styles and
onedark's colors. `ruff` is pinned in the `dev` dependency group, so use `uv run ruff`.
tui-kit comes from GitHub's master (`[tool.uv.sources]`); after a push there,
`uv lock --upgrade-package tui-kit` picks it up. To work on both at once, switch that source to
the commented-out `../tui-kit` path.

## Structure

```
outils/                 # git root + pyproject.toml (run uv commands here)
  outils/               # Python package
    __init__.py         # The version, the repository's URL and CACHE_DIR (~/.cache/outils, XDG_CACHE_HOME respected)
    app.py              # OutilsApp, a tui-kit BaseApp: MODES, the footer and its messages, the keys
    __main__.py         # The command line: which tab to open on
    config.py           # Optional ~/.config/outils/config.yaml (theme, through tui_kit.config; week_start,
                        # clocks, location, units)
    clocks.py           # The time, offset and summer time in an IANA time zone; no Textual
    epoch.py            # Epoch timestamps to dates and back; no Textual
    months.py           # The month grids, shift_month and the day labels; no Textual
    weather.py          # Open-Meteo: finding the place, the forecast, the weather codes; no Textual
    life.py             # The Game of Life's rules on a grid that wraps around; no Textual
    snake.py            # The game of snake on a walled grid, and the best score's file; no Textual
    command.py          # Runs a tab's command (pactl, bluetoothctl, nmcli) through tui-kit, failures as the tab's error; no Textual
    click_only.py       # Widgets a click must not give focus to, so the view keeps its keys; quick_button takes every click
    web.py              # JSON from a web service (Open-Meteo, ipinfo.io) with urllib, failures as the tab's error; no Textual
    reload.py           # A view's reload one at a time: a timer tick while one runs is skipped, a request runs it again after; no Textual
    remote.py           # `outils --show <mode>`: tell an outils already running which tab to show, over a Unix socket; no Textual
    ipinfo.py           # ipinfo.io: an address or host name, the public address by default, and the fields shown; no Textual
    dropbox.py          # The dropbox command (status, start, stop) and the files changed last in its folder; no Textual
    pactl.py            # Every pactl call and the parsing of its JSON output; no Textual
    bluetooth.py        # Paired Bluetooth headphones through bluetoothctl, merged into pactl's outputs; no Textual
    status_bar.py       # Signals i3blocks after a sound change so its volume block redraws
    nmcli.py            # Every nmcli call and the parsing of its terse output; no Textual
    qr.py               # A Wi-Fi network's QR code, drawn in half blocks (segno); no Textual
    screens/            # Help, and the Wi-Fi tab's panels: details and share (tui-kit PanelScreens), the password, and the QR code alone
    widgets/            # One view per mode (calendar_view.py, time_view.py, weather_view.py, ip_view.py,
                        # dropbox_view.py, sound_view.py, wifi_view.py, life_view.py, snake_view.py);
                        # device_card.py is one sound device on one line, networks_table.py a Wi-Fi list;
                        # month_view.py draws one month, clocks_view.py the time tab's clocks;
                        # lookup_box.py, the time, weather and IP tabs' box to type in and rows of what was found
    styles/outils.tcss  # outils's own styles, joined after tui-kit's (app.STYLE_FILES)
```

## Modes

Each mode is a tab of the `#modes` `TabbedContent`, the first row; the command line picks the
one it opens on. A click on a tab or `tab` switches; `tab` is an app binding with `priority`, so
the screen's own `tab` (focus next) never runs, and it is skipped while a panel or dialog is up.
The tabs cannot take focus. When a tab shows, `OutilsApp._show_mode` gives focus to a view that
can take it (the calendar, for its arrows, Dropbox, for its list, Life, for `r`, and Snake, for its keys) and clears it otherwise,
so a hidden view never keeps it. A view must not focus itself while hidden: `TabbedContent`
switches to the tab of whatever has focus. `_show_mode` also calls `tab_shown` on a view that
has it, and `tab_hidden` on the one before (`OutilsApp.shown_view`): Sound and Wi-Fi use those,
not `on_show` and `on_hide`, because Textual's partial relayout does not always send Show to a
pane that comes back (Sound got none once Wi-Fi sat next to it). `tab_shown` is where they give
focus to one of their own widgets. `_show_mode` runs twice for the first tab (on mount, then on
`TabActivated`), so it does all this only when the view changes.
Weather and IP ask their service the first time their tab shows (`on_show`), so opening the
calendar makes no request. The panes are `<mode>-mode`, not the view's own id, which a duplicate
would break.

Every tab sits over the same footer: `OutilsApp.compose` adds `#app-footer`, docked at the
bottom, a rule (`border-top`) over Close, which quits, on the left, and Help, which opens the
shortcuts (as `?` does), on the right (`dock: right`). tui-kit shows messages in whatever `HeaderNotification` the screen holds, so
the footer holds one, `FooterMessage`: while a message shows, it takes Help's place, right-aligned
over the rest of the line (an error wraps onto up to three lines), and Help comes back once it clears.
A view with a `CREDIT`, its words and its site's URL, has it shown in grey at the right, over
the rule (`#mode-credit`), the site as a `Link` that opens it, blue and underlined on hover like
every link: "Data by open-meteo.com" on the Weather tab
(its CC BY 4.0 license asks for it) and "Data by ipinfo.io" on the IP tab. A view with a `footnote`
instead has that text there, in blue and with no link: the calendar gives today in full ("Thursday,
September 24, 2026"), shown again when a new day starts (`FootnoteChanged`). Time, Dropbox, Sound, Wi-Fi, Life and Snake have neither, so the line is hidden there.
Close cannot take focus, so a click leaves the mode's keys working. App tests patch
`weather_view.forecast` and `ip_view.fetch` so no mode reaches the network, and
`dropbox_view.status` and `dropbox_view.recent` so none runs `dropbox` or reads the Dropbox folder,
`pactl.mixer` and `bluetooth.headsets` so none runs `pactl` or `bluetoothctl`, and the
`nmcli` functions so none runs `nmcli`.
`MODES` in `app.py` maps each name the command line takes to its tab label and view widget;
the first one is the default. Help (`OutilsHelpScreen`, `screens/help_screen.py`, tui-kit's with
two columns of outils' own) lists the app's keys under General on the left, and the tab's own on
the right under the tab's name: the view's `BINDINGS`, or its `HELP_BINDINGS` when it has more
(`OutilsApp.action_help` passes the view on show), of either group. Each column is as
wide as its longest line and at least General's width (`min-width: 24`), so a tab with no keys of
its own still gets a panel of a fair size. Every view gets the `mode` class, which gives all tabs
the same padding (a view that sizes what it draws reads `self.size`, the area inside it). A new
mode is a view in `widgets/` and an entry in `MODES`;
`__main__` offers it on its own.

## Calendar

`CalendarView` puts `before` + 1 + `after` `MonthView`s side by side (0 and 1 by default), the
month in focus first, under the Previous, Today and Next buttons; it starts on today's
month. outils stays open for days, so `CalendarView.set_today` reads the date again every minute and
when its tab shows (`tab_shown`): today's highlight moves, and a calendar on today's old month follows
to the new one, while a month picked by hand stays. Tests pass `today=` and call `set_today`. `CalendarView.action_shift(delta)` moves them all (Previous, Next, `←` and `→`), and
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
kept as calendar's number (Monday 0). An unknown day is a warning in the footer and Monday.

## Time

`TimeView` holds a `ClocksView` over an epoch converter (below), a row per clock: its name, the time there, its offset from
UTC in orange (the weather's high temperature color) and, while summer time is in force, Nerd
Font's sun (the weather tab's) in yellow. The clocks are `clocks` in `config.yaml`, names mapped to IANA time zones in the order shown; the default is
Portland, Chicago, UTC and Strasbourg. A zone Python's `zoneinfo` does not know is a warning in
the footer and is left out. The view checks the time every second and redraws when the minute
turns; it makes no request.

The Time, Weather and IP tabs share a layout, in `widgets/lookup_box.py`: a row
(`lookup_row`) with a green label and a `LookupBox` to type in, over what was found. On Time and
IP that is a `LookupDetails`, a row per label and value, the labels green; `lookup_row` makes the
box's label as wide as the details' labels, so the box lines up with the values. An error shows
in red in place of the rows.

Under the clocks and a rule (`#time-rule`), an Epoch box converts what Enter finds there. It
opens on now, in seconds, and follows it every second (`follow_now`) until it is used: never
while the box has focus or holds an edit, and not once something typed was converted. The green
Now button beside the box, shown only while the box is not following now (hidden with
`visible`, so it keeps its place), goes back to following it, as does Enter on an empty box. Now
cannot take focus. The box then turns blue (what was typed, or the seconds for an empty box) and
the rows give the timestamp in seconds, the date in UTC and here, both ISO 8601 with their offset
(`+00:00` for UTC), and how far it is from now, redrawn every second (`TimeView.measure`) so
"2 seconds ago" stays true. `epoch.parse` reads a number as seconds (a fraction is kept), or as
milliseconds when it is 13 digits with no fraction (2001 to 2286; as seconds, 13 digits would be
past year 33000); anything else goes to `datetime.fromisoformat`, and a date with no offset is
local time, the system's (summer time included, through `astimezone`). An empty box, or `now`,
is now.

## Weather

`weather.py` talks to Open-Meteo through `web.get_json` (urllib), no account and no key; its
calls block, so `WeatherView.load` runs `weather.forecast` in a worker. Failures raise
`WeatherError`, shown in the view and in the footer; so does an answer of another shape than
expected, caught around the parsing, not field by field. A cache entry of another shape is asked again.

`WeatherView` is a City box over a `ForecastView`. It opens on `location` from `config.yaml`
(`Portland, OR` by default), and Enter in the box looks up what was typed; the forecast on show
stays until the new one comes. A forecast older than `MAX_AGE` (an hour, by wall time so a night's
suspend counts) is asked again when the tab shows. Once found, the place replaces the text in the box, in full and
in blue (`LookupBox.show_found`), which is the only place the forecast says where it is for;
clicking the box turns it back to plain text to type over. The app sets `AUTO_FOCUS = None` so
the box never takes focus by itself (it would swallow `?`, `t` and `q`); it has focus only once
clicked, and lets go after Enter or Escape (a `LookupBox` binding, so Escape there does not
quit). A typed city is not saved.

A place is "City", or "City" with qualifiers after commas ("City, Region, Country"). `find_place` asks Open-Meteo's
geocoding for the city and `pick_place` chooses among the answers: the exact name first (it lists
Vitória before Victoria), then the most qualifiers, each matching a region, a country or a country code,
in full or by initials ("BC", "Hong Kong" for HK), or a US state or Canadian province by its
postal code (`REGION_CODES`: "OR", "ME", "QC"). A single word never matches by its first letter,
or "ME" would find Multnomah County. A place's own label ("Portland, Maine, United States"), as
the box shows it, finds that place again, so Enter on an untouched box is harmless. The result is cached in
`~/.cache/outils/places.json` (`outils.CACHE_DIR`), keyed by the location text, so opening
the pop-up costs one request. `units` is `metric` (the default) or `imperial`, passed to
Open-Meteo, which converts. °C and °F, right of the City box (`#weather-units`, buttons that
cannot take focus), switch them, the one in use in bold blue: the place on show is asked again
in the other units (`WeatherView.location`), and `WeatherView.UnitsChanged` has the app write
`units:` to `config.yaml` (`config.save_units`, which replaces only the value, found through PyYAML's node positions, checks
the file reads back the same but for it, and writes it aside then moves it over, through a link to
the file it points at; a file it cannot change safely is left as it was, with a warning in the footer).

`ForecastView` shows the weather now (icon, temperature, words, then feels like,
wind, humidity and rain), then one row per day for `weather.DAYS` days, today first and the
others by their full day name. The days are the forecast's own dates (`timezone=auto`, the place's
time zone), so the first is "Today" there, whatever the date here. Icons are Nerd Font weather glyphs, as the Sound tab uses Nerd Font
battery icons; a clear night gets the moon. The colors come from TCSS through the view's
component classes (high orange, low cyan, rain chance blue).

## IP

`IpView` is an IP box over an `IpDetails` (a `LookupDetails`). The first time it shows, it asks
about this computer's public address; Enter in the box asks about what was typed, and an empty
box goes back to this computer's. Once found, the box turns blue and shows the address, except a
host name, which stays as typed (the IP row gives its address), and `IpDetails` shows one row per
field in `ipinfo.FIELDS` order, the address first and in bold blue, skipping any field ipinfo.io
leaves out (and its `readme` link).

`ipinfo.fetch(target)` asks `https://ipinfo.io/json` for this computer's address, or
`https://ipinfo.io/<address>/json` for another (no account, no key), through `web.get_json`. ipinfo.io
takes addresses only, so `resolve` turns a host name into one first, with a final dot so the
system's search domain is not tried (a wildcard there answers for any name). A private or
reserved address is refused before any request: ipinfo.io only answers `bogon` for it. Failures
raise `IpInfoError`, shown in red in place of the details and, unlike the Weather tab, not in the footer. ipinfo.io limits unauthenticated requests
per day, far above what opening a pop-up uses.

## Dropbox

`DropboxView` starts or stops the Dropbox client on this computer, with a button over the right
end of the list, and shows the files that changed last in the Dropbox folder. It uses only the `dropbox` command (`dropbox.py`, through
`tui_kit.processes.run`), which talks to the local daemon: no account and no network. It has no history of
what synced, so the files are the `RECENT` (200) with the latest modified times under the folder
(`~/.dropbox/info.json` names it, `~/Dropbox` by default), skipping the client's `.dropbox` and
`.dropbox.cache`. A downloaded file keeps the time it was changed elsewhere, not when it synced.

Over the list, "Last 200 synced files" (`#dropbox-title`) on the left, and on the right a button that names what it acts on: Stop Dropbox (red) while the client
runs, Start Dropbox (green) while it is stopped, as `dropbox status` tells. Its tooltip says what it
does: stop quits the whole app, it does not pause, so nothing syncs until it starts again. It runs
`dropbox stop` or `dropbox start` in a worker; meanwhile "Starting..." (green) or "Stopping..."
(red) takes the button's place (`#dropbox-state`, hidden otherwise). A failure goes to the
footer. `dropbox stop` only asks the daemon to quit and returns at once, while `dropbox status`
still answers for a few seconds, so `dropbox.stop` waits until it says not running
(`STOP_TIMEOUT`). `dropbox start` gets no pipes (plain `subprocess.Popen`), since the daemon it launches would hold
them open and the call would never return. It exits 0 even when the daemon did not start, so
`dropbox.start` waits, within `START_TIMEOUT`, until `dropbox status` says it runs. A command that
exits non-zero raises `DropboxError` with the last line of its stderr, else of its stdout; a
stopped client is no failure (`dropbox status` says "Dropbox isn't running!" and exits 0), and a
status that times out or fails shows as running. `start` and `stop` are coroutines that check every
`CHECK` seconds, not blocking calls in a thread: Python waits for its threads before it exits, so
quitting during "Stopping..." would wait for the daemon. With no `dropbox` command, a red line says so in place of the button.
The view asks every `POLL` seconds, only while its tab shows (`on_show` and `on_hide`), one look
at a time (`reload.Reload`): walking a big folder can take longer than `POLL`, and a cancelled
look would leave its thread running and throw its result away, so a tick skips while one runs,
and the look after a start or stop runs once it ends; a look overtaken that way is not shown (`Reload.overtaken`).

`RecentFiles` shows a row per file: how long ago (`epoch.relative`), then its path, the folder dimmer than
the file name (`$fg 60%`), which is bold; a path too long for the row loses its start, so the file's own name stays. As in flotte's
tables, one row is selected, shaded with its colors kept: `↑` and `↓` move it, and so does the
mouse, over a row (it stays when the mouse leaves). It stays on the same file as new ones come in.
Enter or a single click opens the file with `xdg-open` (`dropbox.open_file`); `ALLOW_SELECT` is
off, or a double click would select the text of every row. When they do not all fit, the list
scrolls (`#dropbox-scroll`, with a thin scrollbar), and `↑` and `↓` keep the selected row in sight.

## Sound

The Sound tab came from ouie, a separate app until then (github.com/jmoniatte/ouie),
which replaced the fzf `audio` script from the dotfiles repo. It keeps what that script did:
list only plugged-in outputs, move playing streams when the output changes, and signal i3blocks
(`status_bar.refresh`, signal 10 for the volume block).

`SoundView` (`widgets/sound_view.py`) has no section titles: the outputs (sinks), a line, then
the microphones (sources), one `DeviceCard` (`widgets/device_card.py`) per device. The line is `#inputs-cards`' top border, so
it goes with the section when there is no microphone. A card is a single line with a blank line
after it: the name (green and bold for the device in use, no other marker) and battery, the
volume figure (grey when muted, no "muted" text) and bar, Mute or Unmute, then Connect /
Disconnect for headphones. Everything right of the name has a fixed width and the name column
takes the rest (`1fr`, capped by `max-width`, and never below the longest name, which
`DeviceCard.set_columns` sets as its `min-width`), so the bars line up and names are never cut. With
today's devices that needs about 70 columns. The battery is a Nerd Font level icon and the
percentage (`battery_text`, `󰁽 40%`); a terminal without a Nerd Font shows a box for the icon.
It is dropped when it does not fit whole (`DeviceCard._fit_battery`). The Bluetooth button is
only hidden (`visible`) on wired devices, to keep its column, and so is Mute on headphones with no
sink, so their Connect lines up with the Disconnect of others; `DeviceCard.set_columns` removes the
Bluetooth column when no headphones are paired. The user tried a two-line card with its own background
and a colored left edge, and preferred this. The output and microphone in use are always
highlighted, and so is the focused card, with `$bg-light` over the name, figure and bar only:
the buttons' `$color 30%` backgrounds would change over it, so the gaps in that stretch are
padding (which takes the background) rather than margin, and the name column's `min-width`
counts its padding. `↑` and `↓` (`SoundView.action_move`) go through both sections as one list.

Every action on a device sits on its card, so nothing depends on which
card has focus. The buttons are real `Button`s that cannot take focus. The highlight
follows the mouse (`DeviceCard.on_mouse_move` focuses the card), and `DeviceCard.on_click` finds
what is under the pointer: on the bar a click sets the volume there (`VolumeBar.volume_at`), on
the rest of the highlight (`HIGHLIGHTED`) it uses the device, and past the buttons it does
nothing. Bubbled mouse events carry offsets for the widget that first got them, so it works
from `screen_x`, not `event.x`.

`SoundView.show` updates the cards in place when the same devices are listed, so a reload
every 2 seconds does not steal focus or flicker; when the list changes, it remounts that
section's cards and puts focus back on the same device.

`pactl.mixer` reads `pactl --format=json` for `info` (the default sink and source), `sinks` and
`sources`. `parse_devices` drops a device whose active port reports `not available` (the video
card lists four HDMI outputs whether a screen is on them or not) and monitor sources. On a
source `monitor_source` names the sink it listens to; on a sink it names the sink's own monitor,
so that check only applies to sources. Labels come from `short_label`: a
Bluetooth device's own description, else `PORT_LABELS` by the active port's type. Two devices
with the same label get their port description added.

`Device.kind` is the word pactl uses in `set-<kind>-volume`, `set-<kind>-mute` and
`set-default-<kind>`. `pactl.set_default` also moves every sink-input (or source-output) onto the
new device, since the default only applies to streams opened afterwards; a source-output
recording a monitor stays. A device's volume is the mean of its channels; setting it sets every
channel, so balance is lost.

Volume keys and mute redraw the row at once through `SoundView.redraw`, then run pactl in the
`_change` worker, then `status_bar.refresh`. `SoundView._pactl_lock` runs pactl calls one at a
time, so a held key lands in order. Every change and a timer every `REFRESH_SECONDS` reload
everything, the timer only while the tab shows (`tab_shown` and `tab_hidden`). One reload runs at a time
(`reload.Reload`): a tick while one runs is skipped, and a change's reload runs after it, the one
it overtook not shown (`Reload.overtaken`), so the change never flickers back and the latest state shows and a slow pactl or bluetoothctl never has its result thrown away; a pactl failure while
reloading is shown in the footer once, not every 2 seconds (`SoundView._load_error`). `MAX_VOLUME` caps the keys at 100%. Every volume set here is a multiple of `VOLUME_STEP`:
the keys go to the next multiple (`step_volume`, so 61% becomes 65% or 60%) and a click on the
bar rounds to the nearest one. Other programs, and headphones' own buttons, can still leave any
value; it is shown as it is.

A card takes focus only while the tab shows (`SoundView.showing`), since `TabbedContent` would
switch to the tab of a hidden card with focus: `tab_shown` puts it on the output in use, or the
first load does. The view gives Help the card's keys as well as its own
(`SoundView.HELP_BINDINGS`, which Help reads when a view has it).

Every `pactl` and `bluetoothctl` call runs in a worker thread through `command.run` (tui-kit's `processes.run`).
Python waits for those threads before it exits, so tui-kit's `BaseApp` kills whatever is still
running when the app unmounts; otherwise quitting during a slow call (a connect can take 20
seconds) waits for it.

### Bluetooth

`bluetooth.headsets` lists paired devices (`bluetoothctl devices Paired`) and reads each with
`bluetoothctl info <mac>`; `info` with no address only shows what is connected. Only devices
whose `Icon` starts with `audio-` are kept, so the mouse is left out. bluetoothctl prints
failures on stdout, sometimes with exit status 0, so `bluetooth.run` looks for `Failed` too.

`bluetooth.merge` joins them to the outputs by address (`Device.mac`, read by
`pactl.bluetooth_address` from `api.bluez5.address` or the sink name). A connected headset gets
its battery on its card. A headset with no sink (not connected, or just connected) gets a card of
its own with a negative index: `Device.playable` is then False, so the volume keys, mute and
the bar do nothing on it. Clicking its row, or Enter, connects it and then, once its sink shows
up (`SoundView._wait_for_sink`), switches to it. The card's Connect / Disconnect button (`c`) connects
or disconnects. One connect or disconnect runs at a time (`SoundView.bluetooth_busy`), and its
button reads `Wait...` meanwhile. The i3blocks `audio-route` script also switches to headphones
when they connect; the two agree, so that is harmless.

Headphones stay in whatever Bluetooth profile they are in: switching between music (A2DP, no
microphone) and headset (HFP, with microphone) was left out on purpose, as not needed.

Not done yet: a test sound, live updates through `pactl subscribe` instead of polling, and
pairing new headphones. Pairing works without an interactive session:
`bluetoothctl --timeout 15 scan on`, then `bluetoothctl --agent NoInputNoOutput pair <mac>`,
`trust` and `connect`; a device that asks for a PIN would still need `bluetoothctl` itself.

## Wi-Fi

The Wi-Fi tab came from ouifi, a separate app until then (github.com/jmoniatte/ouifi), a front
end to NetworkManager's `nmcli`. `WifiView` (`widgets/wifi_view.py`) has two lists in their own
`TabbedContent` (`#networks-tabs`), Nearby and Saved, each a `NetworksTable`
(`widgets/networks_table.py`), then a footer with the status and the Rescan, Disconnect and Wi-Fi
buttons, right over the app's footer rule. `tab` moves between outils' own tabs, so `←` and `→`
switch lists (`NetworksTable.SwitchList`); the table has no use for them. `WifiView` stops the
inner `TabActivated`, and `OutilsApp.mode_tabs` names outils' own row of tabs, not this one. The
lists bake their colors into Rich text, which `refresh_css` does not reach, so
`WifiView.set_colors` repaints them from `BaseApp.palette` on a theme change (see Themes).

`nmcli.scan` reads `nmcli -t device wifi list` and `parse_scan` merges access points into one
`Network` per SSID: the one in use wins, else the strongest. Hidden SSIDs are dropped. Saved
profiles (`nmcli.Profile`) are matched by their `802-11-wireless.ssid`, not their name, and carried as
`Network.saved_uuid`; every later nmcli call names a profile by UUID. Two profiles can share an
SSID: its Nearby row gets the most recently used (`connection.timestamp`), which is the one in use
if any. `nmcli.scan` returns a `Scan` with both tabs' lists: `saved_list` has a row per profile,
keyed by UUID (Nearby's rows are keyed by SSID, `TABS`), with `in_range=False` for each one the
scan did not see. Tab labels carry the counts; the footer shows the time of the last
scan, or in its place a status while scanning or connecting, when Wi-Fi is off, or when there is no
internet or a login page.

The first time the tab shows, and on `r`, it shows NetworkManager's cached list at once, then
runs `--rescan yes`, which takes around 10 seconds; later shows only read the cached list. `nmcli.run` goes through `command.run` (tui-kit's `processes.run`), and Python waits for
worker threads before it exits, so tui-kit's `BaseApp` kills the nmcli processes still running
when the app unmounts; otherwise quitting during a rescan hangs until it ends. A timer refreshes the cached list every `REFRESH_SECONDS` while the tab shows (`tab_shown` and
`tab_hidden`), and skips while a scan or a connect is running so it never cancels one. An nmcli failure while loading is shown in the footer once, as on the Sound tab.

Joining (`WifiView._connect_requested`): the network in use opens its details; saved and open ones
connect at once; 802.1X ones are refused with a hint; the rest open `PasswordScreen`, which only
collects the password. Every connect runs in `WifiView._connect`, which reports to the dialog while
it is open, so it stays open on an error. `WifiView.connecting` holds the SSID being joined until
nmcli returns, even after Cancel, since nmcli cannot be stopped midway; another connect,
disconnect and forget wait for it. The password reaches nmcli on stdin through `--ask`, never in
argv. When a new connect fails, `nmcli.connect` deletes the profiles it made, not one saved before.

`i` (or Enter on the network in use) opens `DetailsScreen` with `nmcli.details()`: `device show`
for the addresses, plus the `*` row of `wifi list` for the access point, on its Details tab.
The Password tab (`p`), with a QR code button under the password (`c`), comes from `ShareTabsScreen`,
the panel both screens share (`DetailsScreen.panes` adds the Details tab before it), which calls `nmcli.share(uuid)` the first time either is asked for: `nmcli -s` reads the
profile's key-mgmt and password, which NetworkManager gives the session's owner without a
prompt. Tab cycles the tabs (the app's `tab` steps aside while a panel is up). The code opens
alone over the whole window (`QrScreen`, closed by any key or a click), "Scan to join" and the
network's name in blue under it: as a tab of the panel it
needed about 26 rows, and it was the only reason for a tall pop-up; alone it needs 18 at most
for a usual network. Enter on the Saved tab opens `ShareScreen`, the Password tab alone, with
its button, for any profile but the one in use (that one gets `DetailsScreen`); connecting
is done from Nearby.
`qr.wifi_qr` builds the standard `WIFI:` text with segno and draws it with half blocks, two rows
of modules per line. It is drawn in fixed black on white, since a phone camera needs that whatever
the theme. The password is only read when asked for.

The footer status is built by `WifiView._show_status` from `connecting`, `wifi_on`,
`connectivity` and `scanning`, most urgent first. `connectivity` is `nmcli networking
connectivity`, NetworkManager's cached check, read on every refresh. `portal` means a login page:
`o` opens `LOGIN_PAGE_URL`, a plain http address that the login page intercepts. `w` flips the
radio with `nmcli radio wifi on|off` and reloads again after `WIFI_ON_DELAY`, since the card
lists nothing for a few seconds after it comes on.

## Life

`LifeView` fills its tab with a random grid (`life.DENSITY` of the cells alive) and runs
`life.step` `SPEED` times a second, only while its tab shows (`on_show` and `on_hide` resume and
pause its timer). Each character holds two cells, one over the other, drawn with half blocks
(`▀`, `▄`, `█`), so the cells come out square: an area of 56 by 14 characters is a 56 by 28
grid. The edges wrap around, so gliders come back on the other side. A grid that repeats one of
its last two generations (still or blinking) for `SETTLED_STEPS` is replaced by a new one, as is
the grid after a resize; `r` starts a new one at once. The live cells are green, through the
`life--cell` component class.

## Snake

`SnakeView` is a `SnakeBoard` with a column right of it (`#snake-side`, its first line level with
the first row inside the wall, its last with the last): on top, the state in its color (Ready
blue, Paused yellow, Game over red, You win! green; nothing while a game runs) and "Press Space"
whenever the game is not running; at the bottom, "New best!" when the game just set it, the best
score, then the score, colored by how close it is to the best (`score_level`): red under half,
orange to three quarters, yellow to the best, blue from the best on (and when there is no best
yet). The lines that
come and go are hidden with `visible`, so the others keep their places. Nothing is written on
the board once a game has started, so a screenshot shows it whole. Before a game, the board holds
the splash screen (`SnakeBoard._splash`): a snake shaped like an S, in board cells, its tail back
to the left wall and its yellow head top right, "S N A K E" in yellow right of it and the red food
under the title. A board smaller than `SPLASH_SIZE` gets the title alone.

The board is as tall as the tab allows and at most `SHAPE` (4:3) as wide, as snake boards
usually are: `SnakeView.on_resize` sets its width. A cell is two characters wide and one tall
(`CELL`), so it comes out square and a game is short. The wall is a full block thick at the
sides and a half block on top (`▄`) and under (`▀`), the half on the board's side, not a CSS
border: a border's line runs through the middle of its characters, so a snake touching it seemed
not to. Where the snake crashed (`Game.crash`, in the wall or in itself) is red. `snake.Game` has
the rules, with no Textual: the snake starts across the middle heading right, a turn waits for
the next step (two at most, a turn back onto itself ignored), eating grows it and scores a
point, and a wall or its own body ends the game (the cell the tail leaves is free). Filling the
board wins.

The view has four states: `ready` (before any game; the keys are on Help), `playing`, `paused`
and `over`. It starts `ready`, and pauses when its tab hides (`on_hide`). Arrows, hjkl or wasd
steer (and start or resume the game), p or space plays or pauses (and, once
over, goes back to `ready` on a new board, so a second press starts it), r starts a new game at
once. Each steer key is one `Binding` of three keys with a `key_display`, so Help
shows one line per direction. A step is a `set_timer`, not an interval, so each point makes the
next step quicker (`START_DELAY` down to `FASTEST_DELAY`). A new size (`SnakeBoard.Resized`) is
a new board, back to `ready`. The best score is kept in `~/.cache/outils/snake.json`
(`XDG_CACHE_HOME` respected); tests point `snake.BEST_FILE` elsewhere.

## Themes

`t` opens tui-kit's theme picker and the choice is saved to `~/.config/outils/config.yaml`; there
is no Settings panel. Anything drawn with Rich instead of TCSS must take its colors from
`BaseApp.palette`, and its view repaints it in a `set_colors` method, which `OutilsApp.apply_theme`
calls on every view that has one.

## Versions

The version comes from git tags via setuptools-scm. Tags have no `v` prefix. Release by
tagging: `git tag 0.1.0`.
