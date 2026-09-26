# outils

Everyday tools in the terminal, one tab each: a calendar, clocks, the weather forecast, this
computer's public IP, the Dropbox client's sync, the sound devices, Wi-Fi and, for fun, the Game of Life and snake. The calendar
shows this month and the next side by side like `cal`, with today
highlighted. **← Previous** and **Next →** (or the arrow keys) move a month at a time, and
**Today**, shown once the current month is off screen, comes back to the current month.
Today's date, in full, is at the bottom right.

The Time tab gives the time now in a few places, with the offset from UTC and a yellow sun while
summer time is in force (see `clocks` below). Above the clocks, the Epoch box converts an epoch
timestamp to a date, or a date to a timestamp: click it, type `1790222400` (seconds; 13 digits are milliseconds) or `2026-09-24 15:30` (local time, unless it ends in `Z` or an offset like
`+02:00`) and press Enter. It shows the current time, ticking, until you use it; the green
**Now** button next to it, or Enter on an empty box, goes back to it.

The weather shows the conditions now and a row per day for a week, from
[Open-Meteo](https://open-meteo.com) (free, no account). It opens on your `location` (Portland, OR
unless you set one, see below); the place found shows in the City box, in blue. Click the box, type
another place and press Enter to look it up, or Escape to leave the box. **°C** and **°F**, next
to the box, switch the units (wind and rain too); the one in use is blue, and the choice is saved.
The weather icons need a [Nerd Font](https://www.nerdfonts.com).

The IP mode shows the public (WAN) address this computer reaches the internet from, with what
[ipinfo.io](https://ipinfo.io) knows about it: host name, city, region, country, postal code,
location, time zone and network. It needs no account. Click the IP box, type another address or
a host name and press Enter to look it up; an empty box goes back to this computer's address.

The Dropbox tab shows the files that changed last in the Dropbox folder, the latest first. Over
the list, on the right, it shows whether the Dropbox app on this computer is running, with a **Stop Dropbox**
or **Start Dropbox** button (stop quits the app, so nothing syncs until you start it again). `↑` and `↓` or the mouse select a file, and
Enter or a click opens it. It needs the `dropbox` command, and asks it only while the tab shows.

The Sound tab is a simplified pavucontrol built on `pactl`: pick the output and the microphone,
and set their volume. It needs `pactl` (PulseAudio, or PipeWire through pipewire-pulse), and
`bluetoothctl` for Bluetooth headphones. One line per device: first the outputs that are plugged
in (laptop speakers, a monitor over HDMI or DisplayPort, Bluetooth headphones), then, below a
line, the microphones. The device in use has its name in green. Click a row to switch to that
device (what is playing moves onto it), or click its volume bar to set the volume there; each row
has its own **Mute** / **Unmute** button. Paired Bluetooth headphones stay listed when they are
not connected: click their row to connect and switch to them, or use **Connect** /
**Disconnect** (`c`); their battery shows next to their name when they report it. From the
keyboard, `↑` and `↓` (or `j` and `k`) select a device, Enter uses it, `m` mutes it, and `←`
and `→` (or `h` and `l`) turn it down or up by 5%, up to 100%. The tab reloads every 2 seconds
while it shows, and after each change it sends `SIGRTMIN+10` to i3blocks so its volume block
redraws.

The Wi-Fi tab lists the networks through NetworkManager's `nmcli`, in two lists: Nearby, the
networks in range with their signal, security and band, the one in use first and in green, and
Saved, every saved profile, in range or not. `←` and `→` switch lists. Click a network (or Enter)
to join it: a saved or open one connects at once, a new one asks for its password. On the network
in use, it opens its details (addresses, gateway, DNS, access point) with its password (`p`) and
a QR code to join it from a phone (`c`); on the Saved list, any other network shows its password
and QR code. `r` rescans, `d` disconnects, `f` forgets the selected network, `w` turns Wi-Fi on
or off, and `o` opens the login page a hotel or café network asks for. Networks that sign in
with 802.1X are left to nm-connection-editor.

The Life tab runs [Conway's Game of Life](https://en.wikipedia.org/wiki/Conway%27s_Game_of_Life)
on a random grid that fills the tab, its edges wrapping around. A grid that settles into still or
blinking shapes is replaced by a new one after a few seconds; `r` starts a new one at once.

The Snake tab is the game of snake. It starts paused (`?` lists its keys): the arrows, `hjkl` or
`wasd` steer, `p` or `space` plays and pauses, and `r` restarts. Leaving the tab pauses the game.
Each point makes the snake a little quicker; the best score is kept between games.

## Install

```bash
./install.sh
```

It installs `outils` as a [uv](https://docs.astral.sh/uv/) tool. It needs SSH access to GitHub,
where its shared UI library, [tui-kit](https://github.com/jmoniatte/tui-kit), lives.

## Use

```bash
outils            # opens on the calendar
outils time       # opens on the clocks
outils weather    # opens on the weather forecast
outils ip         # opens on this computer's public (WAN) IP address, from ipinfo.io
outils dropbox    # opens on the Dropbox app's state and the files synced last
outils sound      # opens on the sound outputs and microphones
outils wifi       # opens on the Wi-Fi networks
outils life       # opens on the Game of Life
outils snake      # opens on the game of snake
```

Each command opens on its own tab, so a status-bar block can open the one it is about. Click a
tab or press `Tab` to switch. `?` shows the shortcuts, `t` picks a theme, `y` copies the text selected with the mouse, and `q`, `Esc` or the **Close** button at the bottom left quits.
Click the name in the header to open the shortcuts too.

## Configuration

Nothing is required. Press `t` to browse the themes: each one applies as the cursor moves,
`enter` keeps it and `esc` restores the one you started on. The choice is written to
`~/.config/outils/config.yaml`, which you can also edit by hand:

```yaml
theme: one-light
week_start: sunday       # the calendar's first column; monday by default
location: Victoria, BC   # where the weather opens; Portland, OR by default
units: imperial          # metric by default; °C and °F on the Weather tab set it
clocks:                  # the Time tab, top to bottom: a name, then its time zone
  Home: America/Vancouver
  UTC: UTC
  Tokyo: Asia/Tokyo
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
