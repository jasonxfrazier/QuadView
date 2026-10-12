# Windows installer

Friends install LibreWolf, run `QuadViewSetup-0.1.0.exe`, and open the QuadView
desktop shortcut. Python, Qt and the Chromium used to fetch links are bundled;
users do not need uv.
The installer runs for the current user without requiring administrator access.

First launch asks whether to configure confined manual video fullscreen. Accepting
adds only `pref("full-screen-api.ignore-widgets", true);` to
`%USERPROFILE%\.librewolf\librewolf.overrides.cfg`. Existing contents are preserved
and backed up once as `librewolf.overrides.cfg.quadview-backup`. Restart LibreWolf
after accepting. Fullscreen setup can also be opened from the controller.
Automatic fullscreen activation is not included.

Build on Windows x64 with uv and the Inno Setup compiler:

```powershell
.\packaging\build.ps1 -Compiler 'C:\Program Files\Inno Setup 7\ISCC.exe'
```

The locked build group supplies PyInstaller. Preparation uses the browser revision
required by the locked Playwright package, downloading it if missing. Distribute
the setup executable in `dist`; the complete `dist\QuadView` folder is also portable.
Do not distribute `QuadView.exe` alone.

Release checks include unit tests and `QuadView.exe --package-check <report.json>`:
the latter opens the Qt controller and uses the shipped Chromium against a local
fixture to verify visible links and the `/stream/` filter. It does not inspect
personal browsing or edit LibreWolf settings. Test installation and uninstallation
in an isolated directory. A clean Windows computer without Python remains the final
external compatibility check; testing on a developer computer is not equivalent.

The build is unsigned. Windows may show an unknown-publisher/SmartScreen prompt.
A signed release requires a separately obtained signing certificate. Uninstall
removes app files and shortcuts; user settings and the accepted LibreWolf override
are preserved. Remove the QuadView line from the override file to undo that setting.
