"""Use only the Chromium shipped beside the frozen application."""
import os
import sys
from pathlib import Path
os.environ['PLAYWRIGHT_BROWSERS_PATH'] = str(Path(sys._MEIPASS) / 'ms-playwright')
