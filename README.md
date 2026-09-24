# outils

Everyday tools in the terminal: a calendar and the weather forecast, one per run. Both are still
to come; for now outils is the shell they will live in.

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
```

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
