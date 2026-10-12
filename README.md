# QuadView

A small Windows controller for one through four LibreWolf windows, selected from
the stream links discovered on a source page.
Uses your installed browser and its normal profile, including your existing
extensions and privacy settings. The selected windows share that profile and its logins.

## Run

Requires Windows 10/11, Python 3.12+, [uv](https://docs.astral.sh/uv/), and an existing
LibreWolf installation. This checkout uses Python 3.13 for development.

```powershell
uv sync
uv run playwright install chromium
uv run quadview
```

Dependencies and their resolved versions are managed in `pyproject.toml` and
`uv.lock`. No administrator privileges are required for ordinary use.

1. Select the target monitor. QuadView uses its work area, leaving the taskbar available.
2. Confirm the detected LibreWolf executable, or use **Browse**.
3. Enter the source page address and click **Fetch Links**. A temporary Chromium
   window loads it and closes after extracting the visible links.
   The default source is `https://crackstreams.mx/league/nflstreams`; saved custom
   source addresses remain available.
4. Check one to four stream links, in your preferred order. Completely close
   LibreWolf, then click **Launch QuadView**.
5. Use **Reapply Layout** after moving windows. **Close QuadView Session** requests
   normal closure of the managed windows; browser confirmation dialogs remain yours to answer.

Avoid opening extra LibreWolf windows while the launch requests are being
associated. New browser windows opened after startup remain unmanaged. Manually
closing a managed window rearranges the survivors according to their remaining
count, preserving their selection order.

| Selected links | Layout |
| --- | --- |
| 1 | Whole usable monitor area |
| 2 | Equal left/right halves |
| 3 | First selection fills the left half; second and third stack on the right |
| 4 | Top left, top right, bottom left, bottom right |

Checkmarks show selection numbers. Uncheck a link and pick another to change the
selection before launching; close the current session before choosing a new set.
The picker starts empty on every launch and every fetch. Previously selected
links are never checked automatically.

Discovery uses the supplied `a[href], area[href]` visibility/deduplication logic.
It keeps URLs whose path contains the case-sensitive segment `/stream/`, and derives names with
`' '.join(link.split('/')[-1].split('-')).title()`. Query strings, fragments,
repeated hyphens and trailing slashes are preserved by that logic. If two links
yield the same name, the later URL wins, as in the supplied script.
Matches in hostnames, query parameters or fragments do not qualify. The fetch
worker and picker share this same filter.

Chromium is used only for discovery, with a disposable context. It does not share
LibreWolf cookies, logins or extensions. Pages requiring authentication or links
that appear after the page's load event may require site-specific handling; this
version matches the supplied script's load timing. Chromium installation is an
explicit setup command, never an automatic download by the running app.

Closing the controller during a session hides it to the system tray when available.
The tray's **Exit QuadView — leave browsers open** action releases management and
keeps browsing windows open. Without a tray, the controller offers an explicit exit choice.
Existing browser windows cannot be reattached after exiting QuadView; close them
normally before starting another session.

## Video fullscreen

In your normal LibreWolf profile, open `about:config`, search for
`full-screen-api.ignore-widgets`, record its old value, then set the existing Boolean
to `true`. Close LibreWolf and launch your QuadView session. Use each player's own
fullscreen button. QuadView never changes this preference or writes browser profile files.

Use each player?s fullscreen button manually after launching. QuadView only
opens and arranges the browser windows.

## Settings and privacy

Settings: `%LOCALAPPDATA%\QuadView\config.json`. Saves the source page and selected URLs,
monitor choice, executable path, controller size/position. Invalid configuration
files are preserved in a dated backup before being replaced. Unsupported versions
load defaults with a visible notice.

Bounded diagnostic logs live in `%LOCALAPPDATA%\QuadView\logs`. They contain session
events and counts, not URLs, page titles, contents, cookies or credentials. QuadView
has no telemetry or proxy and never modifies LibreWolf pages or profiles. The
user-requested Playwright scraper evaluates the link-reading expression in its
own temporary browser. Selected website traffic is handled by LibreWolf normally.

## Checks

```powershell
uv run python -m unittest discover -v
uv run python -m quadview.diagnostics
```

The first command runs automated tests without launching a browser. The second
inspects the installed browser and connected monitors without changing windows.
For an explicitly requested desktop smoke test:

```powershell
uv run python -m quadview.diagnostics --smoke --close --output reports/native-smoke.json
```

This opens four public test pages, checks native quadrant positions and reapplication,
checks refusal to launch while LibreWolf runs, then requests normal closure of only
its managed test windows. It does not prove page rendering or video fullscreen.
Add `--count 1`, `--count 2`, or `--count 3` to test the corresponding adaptive layout.
`--exercise` additionally checks both monitors, minimize/maximize recovery, and
rearrangement after manual closure. Link extraction also has an opt-in real-browser
fixture check:

```powershell
$env:QUADVIEW_DESKTOP_TESTS = "1"
uv run python -m unittest tests.test_link_discovery_desktop -v
```

The first native desktop test passed on the primary monitor's 2560 × 1392 work area:
four visible frames at 1280 × 696, sharing one browser process. See
[technical findings](docs/technical-validation.md) for source evidence, limitations,
and the distinction between automated and manual validation.

## Structure

- `quadview/ui/`: PySide6 controller and background worker.
- `quadview/core/`: browser adapter, native window adapter, session lifecycle,
  geometry, URL validation and settings.
- `quadview/utils/`: local diagnostic logging.
- `tests/`: pure policy tests, native API contracts and UI checks.
- `docs/`: technical findings and manual acceptance procedure.

Window-to-URL association is sequential and conservative. Win32 does not expose a
browser URL identity contract; restored windows or concurrent user window creation
can be ambiguous. QuadView rejects detected ambiguity and leaves unassigned windows
untouched. It does not claim that timing alone proves the requested URL. Profile
choosers and restore dialogs may need to be resolved in LibreWolf before retrying.
