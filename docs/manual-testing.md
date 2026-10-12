# Manual Windows testing

Last updated: 2026-10-11.

The user reports that the manual fullscreen setup works. Native desktop tests have
passed for the adaptive layouts on both monitors, reapplication, minimize/maximize
recovery, manual closure/reflow, running-browser refusal and graceful closure.
The real Chromium extraction fixture also passed. Site-specific extraction,
visually checked page addresses, and video-player fullscreen remain manual checks.
Rows below describe the full user workflows; a native API test does not establish
every observation in those rows.

## Link picker and adaptive-layout checks

Enter a source page address, click **Fetch Links**, and verify the stream names
against the supplied splitting rule. Chromium should close after extraction.
Check links in a non-list order and verify that the displayed selection numbers
follow click order. The fifth check must be refused without changing the first
four selections. Unchecking and rechecking a link puts it last in the order.

Launch selections of each size: one fills the work area, two split left/right,
three put selection 1 on the full left half with selections 2 and 3 top/bottom
on the right, and four use quadrants. Manually close one managed window and
verify that the remaining windows adapt to their new count. An unrelated new
browser window must remain unmanaged. Save/restart should restore the source
page, but every fetch must leave all links unchecked, including previously selected
URLs. Fetched page content and the complete link list are not saved.

## Record the environment

Record the date, tester, QuadView revision, Windows version, LibreWolf version, selected monitor, monitor resolution, work-area rectangle, and display scaling. Note whether session restoration is already enabled, whether fullscreen-related extensions are installed, and the current value of `full-screen-api.ignore-widgets`. Do not copy browser history, cookies, credentials, or private page contents into the test record.

Initial read-only discovery found LibreWolf 157.0 at `C:\Program Files\LibreWolf\librewolf.exe`. Recheck the version for each test run; do not treat this as a fixed support requirement.

## Enable the proposed fullscreen preference manually

If the setting is already `true`, record it and leave it unchanged.

1. Open the existing LibreWolf installation normally, using the profile intended for QuadView.
2. Enter `about:config` in the address bar and press Enter.
3. If shown, select **Accept the Risk and Continue**.
4. Search for the exact name `full-screen-api.ignore-widgets`.
5. Record the current Boolean value and whether it has a custom value. If no existing preference is found, stop and report the browser version; creating an arbitrary name does not prove that the browser implements it.
6. If its value is `false`, use the toggle button to set it to `true`. If the preference is locked, report that condition rather than bypassing it.
7. Close LibreWolf normally, including every window, before launching QuadView. Do not force-stop a remaining browser process.

The change applies to the profile, not just to QuadView's four windows. QuadView offers this setup with explicit confirmation on first launch of the Windows package and through Fullscreen setup. It writes the supported user overrides file and does not edit profile files. To undo it later, return to the same preference and restore the value recorded in step 5. Use **Reset** only if the intention is to restore the browser's default; resetting and restoring a previously customized value are different operations. [Mozilla's configuration-editor instructions](https://support.mozilla.org/en-US/kb/about-config-editor-firefox).

## Fullscreen player tests

Use a normal YouTube watch page and the player on the [official Video.js site](https://videojs.org/). Record the actual public test page and player version when visible. If a demo changes, select another ordinary HTML5 video player and record which one was used. Do not install an extension, inject JavaScript, use developer-console commands, or change privacy/security settings to make a test pass.

1. Configure four pages and launch QuadView after LibreWolf is completely closed. Check each quadrant's actual address visually in the browser UI; a title match is insufficient.
2. Record the four visible window bounds and confirm that they occupy the selected monitor's work area.
3. Start a video in the first quadrant by clicking its ordinary player controls. Manually click the player's fullscreen button, not F11 or theater mode.
4. Check whether the video stays inside that window. Record its visible bounds, any browser chrome that remains, the fullscreen notification, and whether adjacent quadrants remain visible.
5. Enter fullscreen in the second player. Click between the two windows and then repeat with all four quadrants. Also switch focus to QuadView and an unrelated application. Record whether any previous player exits fullscreen when focus moves. Do not describe all-four simultaneous fullscreen as passed if only one window was tested.
6. Press Escape or use the player control to leave fullscreen. Confirm that the same window remains associated with its quadrant and that ordinary browser controls return as expected.
7. Repeat entry/exit, use Reapply Layout, and repeat on each available scaling/monitor combination. Test F11 separately and label its result as browser fullscreen.

If a player takes over the physical monitor, Escape should be the first normal exit action. Record the failure and preserve the user's settings. Do not hide it by repeatedly resizing a native fullscreen window or changing fullscreen permissions and warnings.

| Case | Expected observation | Result |
| --- | --- | --- |
| YouTube player fullscreen | Video stays inside its assigned window; other quadrants remain visible. | Not run |
| Video.js player fullscreen | Same confinement using an independent HTML5 player. | Not run |
| Four windows and focus changes | Record which players remain fullscreen after each focus change. | Not run |
| Escape and repeated entry/exit | Ordinary browsing returns without losing window association. | Not run |
| Reapply while/after fullscreen | Bounds remain correct or the limitation is reported clearly. | Not run |
| F11 | Record separately; does not substitute for the video-player cases. | Not run |
| Existing extensions/protections | Player behavior is observed with the user's settings preserved. | Not run |

If the profile already uses LibreWolf letterboxing, record any content margins without disabling the protection. Distinguish those margins from native window bounds extending beyond a quadrant. [LibreWolf settings](https://librewolf.net/docs/settings/).

An optional `false`/`true` comparison can isolate the preference's effect, but only change the setting manually if the tester chooses to do that comparison. Record and restore the original setting afterward. It is not necessary to alter an already-working setup merely to run the main matrix.

## Launch, ownership, and lifecycle tests

Keep an unrelated application window visible and record its bounds. Where a scenario creates additional LibreWolf windows, leave them unmanaged and verify that session commands do not move or close them. Native-only temporal association has known uncertainty around restoration and concurrent creation; see [technical-validation.md](technical-validation.md).

| Case | Procedure and required outcome | Result |
| --- | --- | --- |
| Existing LibreWolf | Open LibreWolf first, then click Launch. No new browser starts; the required close-LibreWolf message is shown. | Not run |
| Background LibreWolf | Leave a naturally occurring browser process without a visible browser window, if reproducible. Launch is still refused. Do not force a hang to manufacture this case. | Not run |
| Four URLs | Start from a closed browser. Verify the actual address and quadrant for each of four distinct public URLs. | Not run |
| Duplicate titles | Select different URLs with identical page titles. Association must not depend on unique titles; duplicate URL selections are rejected. | Not run |
| Restored windows | With the existing restoration behavior, observe startup. Unexpected or ambiguous windows must not be automatically moved or closed. | Not run |
| Popup or extra user window | Open another window during startup and another after activation. Ambiguity is reported; unrelated windows remain unmanaged. | Not run |
| Concurrent startup | Start LibreWolf independently at nearly the same time as Launch. Check that QuadView does not claim unrelated windows. Record any unresolved race. | Not run |
| Missing/invalid executable | Select an invalid path. Validation explains the problem without launching another browser. | Not run |
| Slow/failed startup | Observe a genuine delayed or failed launch. GUI stays responsive, timeout is finite, and already-created windows are handled explicitly. | Not run |
| Partial session | Close a discovered window during startup. QuadView reports the incomplete session; it does not close arbitrary windows to recover. | Not run |
| Manual close and replacement | Close a managed window, then open a new browser window. Reapply/Close must not adopt the replacement merely by title, PID, or a recycled handle. | Not run |
| Reapply | Move a managed window manually. Reapply restores surviving managed windows and leaves unrelated windows unchanged. | Not run |
| Graceful Close Session | Request closure. Managed windows receive normal close requests; no process is force-killed. | Not run |
| Close confirmation | If LibreWolf presents its normal close/unsaved-work prompt, cancel it. QuadView retains the surviving session and reports incomplete closure. | Not run |
| Controller exit | Close the control application while a session is active. Its documented tray/exit choice preserves browser windows unless explicitly requested otherwise. | Not run |

## Display and configuration tests

| Case | Required outcome | Result |
| --- | --- | --- |
| 100%, 125%, 150%, and 200% scaling, where available | Visible frames align with quadrants in physical pixels; record actual bounds and any mismatch. | Not run |
| Mixed DPI and negative monitor origin | Moving to the selected monitor applies its correct work area and scale. | Not run |
| Odd work-area dimensions | No uncovered row/column or overlapping visible frame due to rounding; right/bottom cells can differ by one pixel. | Not run |
| Taskbar on each available edge | Layout respects the selected monitor's usable work area. | Not run |
| Monitor unplug/reconfigure | No stale coordinates are applied silently; unavailable selection is reported or the documented fallback is used. | Not run |
| Minimum browser dimensions | An unachievable quadrant size is reported instead of falsely confirming exact layout. | Not run |
| URL normalization | A missing scheme gains HTTPS; explicit HTTP remains HTTP; invalid or unsupported schemes receive a clear validation error. | Not run |
| Save/restart | Source page, browser path, target monitor, and controller geometry are restored; fetched links start unchecked. | Not run |
| Missing/corrupt/old configuration | Defaults or a documented migration/error are used without overwriting unrelated files. | Not run |
| Profile preservation | Existing extensions, logins, and protections still work; QuadView has not created a profile or written browser preference files. Normal browser-maintained changes are expected. | Not run |
| Privacy of diagnostics | Logs contain no page contents, cookies, credentials, or unnecessary URL query/fragment data. | Not run |

## Result record

For each performed case, record: date, environment, steps, observed result, pass/fail/blocked, and any limitation. Separate an assertion such as "four HWNDs were discovered" from the visually checked result "each of the four correct pages occupied its assigned quadrant."

Do not attach screenshots containing private pages. Record a failed site's public name and symptom without copying account details. Link the relevant automated test run separately; do not use it to mark a manual row passed.
