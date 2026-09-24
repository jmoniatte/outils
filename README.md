# outils

Everyday tools in the terminal: a calendar and the weather forecast, one per run. The calendar
shows three months side by side like `cal -3`, the current one in the middle and today
highlighted. **← Previous** and **Next →** (or the arrow keys) move a month at a time, and
**Today**, shown once you have moved away, comes back to the current month.

The weather shows the conditions now and a row per day for a week, from
[Open-Meteo](https://open-meteo.com) (free, no account). It opens on your `location` (Portland, OR
unless you set one, see below); the place found shows in the City box, in blue. Click the box, type
another place and press Enter to look it up, or Escape to leave the box.
The weather icons need a [Nerd Font](https://www.nerdfonts.com).

## Install

```bash
./install.sh
```

It installs `outils` as a [uv](https://docs.astral.sh/uv/) tool. It needs SSH access to GitHub,
where its shared UI library, [ouikit](https://github.com/jmoniatte/ouikit), lives.

## Use

```bash
outils            # the calendar
outils weather    # the weather forecast
```

Each opens on its own, so a status-bar block can open the one it is about. `?` shows the
shortcuts, `t` picks a theme and `q` or `Esc` quits. Click the name in the header to open the
shortcuts too.

## Configuration

Nothing is required. Press `t` to browse the themes: each one applies as the cursor moves,
`enter` keeps it and `esc` restores the one you started on. The choice is written to
`~/.config/outils/config.yaml`, which you can also edit by hand:

```yaml
theme: one-light
week_start: sunday       # the calendar's first column; monday by default
location: Victoria, BC   # where the weather opens; Portland, OR by default
units: imperial          # metric by default
```

A place is "City", or "City, Region or Country" when the name is shared; US states and Canadian
provinces can go by their postal code (Portland, ME). Each is looked up once through Open-Meteo and kept in `~/.cache/outils/places.json`;
delete that file after changing where a name should point.

The default, `terminal`, reads the colours from the terminal itself. The other themes are
[base16 schemes](https://github.com/tinted-theming/schemes) named by their upstream slug.

## Development

```bash
uv run outils
uv run python -m unittest discover -s tests
uv run ruff check .
```

Releases are git tags without a `v` prefix (`0.1.0`); the version is derived from them by
setuptools-scm.
