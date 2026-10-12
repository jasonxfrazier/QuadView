"""Pure physical-pixel geometry for one through four browser windows."""

from .models import Rect


def quadrants(area: Rect) -> tuple[Rect, Rect, Rect, Rect]:
    """Split a native monitor work area, assigning odd pixels right and down."""
    if any(type(value) is not int for value in (area.left, area.top, area.right, area.bottom)):
        raise ValueError("Monitor coordinates must be integer pixels.")
    if area.width < 2 or area.height < 2:
        raise ValueError("The monitor work area is too small for a 2 by 2 layout.")
    middle_x = area.left + area.width // 2
    middle_y = area.top + area.height // 2
    return (
        Rect(area.left, area.top, middle_x, middle_y),
        Rect(middle_x, area.top, area.right, middle_y),
        Rect(area.left, middle_y, middle_x, area.bottom),
        Rect(middle_x, middle_y, area.right, area.bottom),
    )


def regions_for_count(area: Rect, count: int) -> tuple[Rect, ...]:
    """First selection has priority: full screen, left half, or top left.

    Three windows give the first the full left half; the others share the
    right half vertically. Odd pixels go to right/bottom regions.
    """
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("Select between one and four links.")
    if any(type(value) is not int for value in (area.left, area.top, area.right, area.bottom)):
        raise ValueError("Monitor coordinates must be integer pixels.")
    if area.width < (2 if count > 1 else 1) or area.height < (2 if count > 2 else 1):
        raise ValueError("The monitor work area is too small for this layout.")
    if count == 1:
        return (area,)
    middle_x = area.left + area.width // 2
    left = Rect(area.left, area.top, middle_x, area.bottom)
    right = Rect(middle_x, area.top, area.right, area.bottom)
    if count == 2:
        return left, right
    if count == 3:
        middle_y = area.top + area.height // 2
        return left, Rect(middle_x, area.top, area.right, middle_y), Rect(middle_x, middle_y, area.right, area.bottom)
    return quadrants(area)
