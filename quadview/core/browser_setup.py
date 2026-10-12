"""Optional, explicit setup of confined manual fullscreen."""
from pathlib import Path
import os

SETTING = 'pref("full-screen-api.ignore-widgets", true);'
MARKER = '// QuadView manual fullscreen setup'

def configure_manual_fullscreen(path: Path | None = None) -> bool:
    """Append one override without changing unrelated browser preferences."""
    path = path or Path(os.environ['USERPROFILE']) / '.librewolf' / 'librewolf.overrides.cfg'
    original = path.read_bytes() if path.exists() else b''
    text = original.decode('utf-8-sig')
    if SETTING in text:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    if original:
        backup = path.with_name(path.name + '.quadview-backup')
        if not backup.exists():
            backup.write_bytes(original)
    addition = ('\r\n' if original and not original.endswith(b'\n') else '') + MARKER + '\r\n' + SETTING + '\r\n'
    # Append preserves the encoding and existing contents of the overrides file.
    with path.open('ab') as output:
        output.write(addition.encode('utf-8'))
    return True

def offer_first_run_setup(parent, settings_directory: Path, *, force: bool = False) -> None:
    from PySide6.QtWidgets import QMessageBox
    marker = settings_directory / 'manual-fullscreen-setup-v1'
    if marker.exists() and not force:
        return
    answer = QMessageBox.question(parent, 'QuadView setup',
        'Keep video fullscreen inside each assigned window?\n\n'
        'QuadView can set up LibreWolf for you. This changes one browser setting '
        'and takes effect after LibreWolf restarts. You will still click each '
        'video’s fullscreen button yourself.',
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        QMessageBox.StandardButton.Yes)
    if answer == QMessageBox.StandardButton.Yes:
        try:
            configure_manual_fullscreen()
        except (OSError, UnicodeError) as error:
            QMessageBox.warning(parent, 'LibreWolf setup',
                'Could not save LibreWolf’s setting. Try Fullscreen setup again. '
                f'({type(error).__name__})')
            return
    marker.write_text('accepted' if answer == QMessageBox.StandardButton.Yes else 'declined', encoding='utf-8')
