"""Small value objects shared by the UI and native adapters."""

from dataclasses import dataclass, field
from enum import Enum

DEFAULT_SOURCE_URL = "https://crackstreams.mx/league/nflstreams"


@dataclass(frozen=True)
class Rect:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    created_at: int  # Native FILETIME ticks; zero means identity could not be read.
    image_path: str


@dataclass(frozen=True)
class WindowSnapshot:
    hwnd: int
    process: ProcessIdentity
    generation: int


@dataclass(frozen=True)
class Monitor:
    identifier: str
    name: str
    work_area: Rect
    bounds: Rect
    is_primary: bool = False

    @property
    def label(self) -> str:
        primary = " · Primary" if self.is_primary else ""
        return f"{self.name} · {self.bounds.width} × {self.bounds.height}{primary}"


@dataclass(frozen=True)
class ManagedWindow:
    quadrant: int  # Original zero-based selection position.
    window: WindowSnapshot


class SessionState(str, Enum):
    IDLE = "IDLE"
    VALIDATING = "VALIDATING"
    LAUNCHING = "LAUNCHING"
    ACTIVE = "ACTIVE"
    CLOSING = "CLOSING"
    ERROR = "ERROR"


@dataclass(frozen=True)
class SessionUpdate:
    state: SessionState
    message: str
    managed_count: int = 0


@dataclass
class AppConfig:
    version: int = 1
    urls: list[str] = field(default_factory=list)
    source_url: str = DEFAULT_SOURCE_URL
    executable_path: str = ""
    monitor_id: str = ""
    monitor_bounds: Rect | None = None
    window_geometry: Rect | None = None  # Qt logical coordinates, not native pixels.
