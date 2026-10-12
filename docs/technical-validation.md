# Technical validation

Last updated: 2026-10-11.

This document separates source inspection, local observations, user reports, and runtime tests. A supported command or an existing preference does not establish that the complete QuadView workflow works on a Windows desktop.

## Current evidence

| Area | Evidence | Status |
| --- | --- | --- |
| Installed browser | Discovery found `C:\Program Files\LibreWolf\librewolf.exe`, version 157.0. | Application adapter detection passed locally. |
| Existing process check | No process named LibreWolf was found during initial inspection. | Point-in-time observation; every launch needs a fresh check. |
| New-window command | Sequential requests opened one through four windows in the installed browser. | Native desktop tests passed; page addresses still require visual verification. |
| Process ownership | Mozilla documents a separate Windows launcher and main browser process. | Source-confirmed; never infer an HWND from `Popen.pid`. |
| Fullscreen preference | Mozilla source skips native widget fullscreen when `full-screen-api.ignore-widgets` is enabled. | Source evidence supports the approach; independent player testing pending. |
| Manual fullscreen result | The user reports that the manual setup works. | User-reported success; specific site, monitor, and focus-transition results have not been independently reproduced. |
| Native window management | One through four windows matched exact work-area regions on both 2560 × 1440 displays, including the negative-origin monitor. | Desktop tests passed for reapply, minimize/maximize recovery, manual closure/reflow, and graceful closure. |
| Link discovery | User-supplied Playwright visibility filter and exact stream-name splitting. | Real Chromium fixture passed: hidden/transparent links excluded, absolute URLs deduplicated, below-fold visible links retained. |
| Automated tests | `uv run python -m unittest discover -v` | 62 automated tests passed; the opt-in Chromium visibility fixture passed separately before the path-filter refinement. |

No acceptance criterion is marked passed solely on this table. Record desktop results in [manual-testing.md](manual-testing.md).

## Link picker and adaptive layouts

The user explicitly approved a separate, disposable Playwright Chromium browser
for source-page discovery and provided the read-only link extraction expression.
It is closed after navigation and extraction. LibreWolf remains the browsing
environment for the selected links; its profile is not used by the scraper.
The app never installs Chromium automatically; setup uses
`uv run playwright install chromium`.

The `/stream/` filter is case-sensitive and applies only to the parsed URL path,
excluding matches in hostnames, query parameters and fragments. The fetch worker,
and picker use one shared predicate. Every fetch clears all selections. Names use the supplied literal expression
`' '.join(link.split('/')[-1].split('-')).title()`, including its treatment of
query strings, fragments, repeated hyphens and trailing slashes. Duplicate names
retain the last matching URL, exactly as the supplied dictionary does.

The picker permits one through four checked links. Check order determines browser
order. One window fills the monitor work area, two share equal left/right halves,
three give the first selection the left half with two stacked on the right, and
four use quadrants. Manually closed windows are retired and the survivors reflow
in their original selection order. Newly opened unrelated windows remain unmanaged.

Native test reports are in the ignored local `reports/adaptive-1.json` through
`reports/adaptive-4.json`; they verify actual visible bounds on both monitors,
not the rendered page addresses or fullscreen video. The real scraper test used
a local fixture; no specific target page was supplied for a live-site test.

## Existing-profile launch behavior

Use the installed executable and its normal profile selection. Invoke `--new-window` once per configured URL, with an argument list and `shell=False`. Four independent top-level windows can share the browser parent process, cookies, logins, extensions, and profile. They are not isolated profiles or four independent browser processes.

Do not use `--no-remote` or `--new-instance` for sequential commands into that instance. Mozilla documents that `--no-remote` prevents both sending and accepting remote commands and implies `--new-instance`. Later normal invocations can pass commands to the running browser. [Command-line parameters](https://firefox-source-docs.mozilla.org/browser/CommandLineParameters.html), [remote-service interface](https://searchfox.org/firefox-main/source/toolkit/components/remote/nsIRemoteService.idl).

The Windows launcher can start the main browser process and exit. Its PID is therefore not a reliable browser-window owner. [Mozilla process model](https://firefox-source-docs.mozilla.org/dom/ipc/process_model.html).

Read-only inspection of the installed `browser\omni.ja` found:

- `modules/BrowserContentHandler.sys.mjs` handles each `new-window` parameter by calling `openBrowserWindow` with the supplied URI.
- Its initial-launch path can replace a startup window rather than create an entirely new native window at the time the URL is handled.
- `chrome/browser/content/browser/browser-init.js` coordinates asynchronous session restoration separately from initial window startup.

These observations are version-specific and should be checked again after a browser update. They did not require launching the browser or reading its profile contents.

## Window association and its limits

The initial native strategy is sequential launch plus window snapshots: record the baseline, request one new window, and examine new eligible windows before requesting the next. Candidate checks include executable identity, owner PID and process creation time, top-level browser characteristics, visibility, and absence from the baseline. Timeouts and a bounded stabilization period are required.

**This is a conservative temporal association, not a browser-provided URL-to-HWND identifier.** A stable, single new HWND does not independently establish which URL it contains. Window titles are not reliable URL identifiers. A late restored window, extension popup, blocked request, or simultaneous user action can invalidate an otherwise plausible association. Firefox can restore previous windows at startup. [Mozilla session restoration](https://support.mozilla.org/en-US/kb/how-do-i-restore-my-tabs-last-time).

The prototype must reject an ambiguous result rather than sort all LibreWolf windows and take the first four. Unexpected windows stay unmanaged. An incomplete session retains only its established managed-window records; it must not close all windows owned by a shared browser process. If native-only association cannot meet the required reliability, stop and present an alternative for approval. No extension, script injection, remote-debugging service, new profile, or hidden network service is an implicit fallback.

The initial running-process check cannot atomically prevent another program or the user from starting LibreWolf a moment later. Concurrent-start and concurrent-window tests are required. A process with no visible window still counts as running.

## Managed-window lifetime

Retain HWND, owner PID, process creation time, executable identity, and observed lifecycle information for each managed window. Revalidate identity immediately before moving or closing it. A destroyed or uncertain window must be dropped from management, not rediscovered by matching its old number or title.

Process creation time guards against PID reuse. It does not by itself detect an HWND reused by the same browser process. Destroy/create observation and snapshot reconciliation improve detection, but external window operations are not atomic. Microsoft explicitly warns that foreign HWNDs can be destroyed or recycled after validation. [GetProcessTimes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-getprocesstimes), [IsWindow](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-iswindow).

Close requests must use normal window closure. Browser confirmation dialogs and unsaved work can delay or prevent closure. A timeout is a reported incomplete close, never permission to kill a process. Unmanaged windows and newly opened replacement windows remain untouched.

## Fullscreen hypothesis and status

Automatic player fullscreen activation was removed at the user?s request.
Fullscreen is entered manually using each player?s own controls.

Firefox 157's `ProcessWidgetFullscreenRequest` checks `full_screen_api_ignore_widgets()` before requesting native widget fullscreen, then completes the browser fullscreen state transition. The source comments describe keeping fullscreen content within an existing application window. This supports the proposed mechanism but does not establish compatibility with every LibreWolf build or website. [Version-matched Mozilla fullscreen implementation](https://raw.githubusercontent.com/mozilla-firefox/firefox/FIREFOX_157_0_RELEASE/dom/base/nsGlobalWindowOuter.cpp).

The upstream 157 preference defaults to `false`. Trusted fullscreen requests and protections against fullscreen window opening/raising are separate settings; enabling `ignore-widgets` is not a reason to change them. An upstream default does not establish the effective value in the user's LibreWolf profile. [Firefox 157 preference definitions](https://raw.githubusercontent.com/mozilla-firefox/firefox/FIREFOX_157_0_RELEASE/modules/libpref/init/StaticPrefList.yaml).

The user reports successful manual use. QuadView still needs independent tests with YouTube and a second HTML5 player, including focus changes among all four windows, repeated entry/exit, and geometry measurements. Browser fullscreen through F11 and a video's fullscreen control are separate test cases; a successful F11 test is not a successful HTML5 video test.

Do not assume that losing focus must exit fullscreen: Mozilla changed that behavior in Firefox 22, with fullscreen warnings on refocus. The required four-window behavior still needs a current desktop test, including focus changes to QuadView and unrelated applications. [Mozilla issue 724554](https://bugzilla.mozilla.org/show_bug.cgi?id=724554).

The preference is a browser/profile setting, not a QuadView-only per-window switch. Its effect on browser chrome, fullscreen prompts, focus changes, and unrelated later browsing must be observed. Keep existing fullscreen permission, warning, tracking-protection, TLS, and extension settings intact. If the desired behavior fails, document it and propose alternatives before changing the approach.

LibreWolf's existing letterboxing can leave margins inside the browser content area. Preserve that protection and distinguish content margins from an incorrectly positioned native window. [LibreWolf settings](https://librewolf.net/docs/settings/).

QuadView must not write `prefs.js`, `user.js`, or other profile files. The user can make the one documented change through the browser UI; instructions are in [manual-testing.md](manual-testing.md). Normal LibreWolf operation may itself update history, session data, cookies, and preferences, so a byte-for-byte unchanged profile is not an appropriate preservation test.

## Monitor and frame geometry

Use the selected monitor's work area in virtual-screen coordinates, including negative origins. Split at `left + width // 2` and `top + height // 2`; the right and bottom quadrants receive any extra pixel. [MONITORINFO](https://learn.microsoft.com/en-us/windows/win32/api/winuser/ns-winuser-monitorinfo).

Establish DPI awareness before creating application windows. Keep native layout measurements in a consistent physical-pixel coordinate space instead of mixing Qt logical geometry with Win32 rectangles. Microsoft recommends declaring the intended process DPI awareness in the application manifest. [DPI-awareness guidance](https://learn.microsoft.com/en-us/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process).

`GetWindowRect` can include invisible resize borders and is DPI-virtualized. DWM extended frame bounds describe the visible frame and are not DPI-adjusted. Measure the difference, compensate the requested outer rectangle, and remeasure after a move to a monitor with different scaling. Do not assume fixed border widths. [GetWindowRect](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-getwindowrect).

Recheck the resulting visible rectangles. Browser minimum sizes, fullscreen transitions, monitor removal, and DPI changes can prevent an exact requested layout; report a mismatch instead of declaring success. Do not remove browser window styles or repeatedly force geometry to disguise a fullscreen failure.

## Validation gates

1. Verify process refusal, sequential creation, and association on the installed browser. Include startup restoration, duplicate titles, popups, and concurrent user activity.
2. Verify visible-frame positioning, layout reapplication, identity loss, partial sessions, and graceful closure on the Windows desktop.
3. Verify YouTube and another HTML5 player with the user's manually enabled preference. Record all-four-window focus behavior as well as individual entry and exit.
4. Complete GUI, persistence, and automated checks, then rerun the affected desktop cases.

A failed core gate requires a documented limitation or an approved alternative. Source inspection and user reports remain useful evidence, but neither substitutes for the recorded runtime result.
