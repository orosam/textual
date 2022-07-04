from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Callable, Iterable

from rich.segment import Segment
from rich.style import Style

from ._border import get_box, render_row
from ._segment_tools import line_crop, line_pad, line_trim
from ._types import Lines
from .color import Color
from .geometry import Spacing, Region, Size
from .renderables.opacity import Opacity
from .renderables.tint import Tint

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:  # pragma: no cover
    from typing_extensions import TypeAlias


if TYPE_CHECKING:
    from .css.styles import StylesBase
    from .widget import Widget


RenderLineCallback: TypeAlias = Callable[[int], list[Segment]]


class StylesCache:
    """Responsible for rendering CSS Styles and keeping a cached of rendered lines.

    ```
    ┏━━━━━━━━━━━━━━━━━━━━━━┓◀── A. border
    ┃                      ┃◀┐
    ┃                      ┃ └─ B. border + padding +
    ┃   Lorem ipsum dolor  ┃◀┐         border
    ┃   sit amet,          ┃ │
    ┃   consectetur        ┃ └─ C. border + padding +
    ┃   adipiscing elit,   ┃     content + padding +
    ┃   sed do eiusmod     ┃           border
    ┃   tempor incididunt  ┃
    ┃                      ┃
    ┃                      ┃
    ┗━━━━━━━━━━━━━━━━━━━━━━┛
    ```

    """

    def __init__(self) -> None:
        self._cache: dict[int, list[Segment]] = {}
        self._dirty_lines: set[int] = set()
        self._width = 1

    def set_dirty(self, *regions: Region) -> None:
        """Add a dirty regions."""
        if regions:
            for region in regions:
                self._dirty_lines.update(region.line_range)
        else:
            self.clear()

    def is_dirty(self, y: int) -> bool:
        """Check if a given line is dirty (needs to be rendered again).

        Args:
            y (int): Y coordinate of line.

        Returns:
            bool: True if line requires a render, False if can be cached.
        """
        return y in self._dirty_lines

    def clear(self) -> None:
        """Clear the styles cache (will cause the content to re-render)."""
        self._cache.clear()
        self._dirty_lines.clear()

    def render_widget(self, widget: Widget, crop: Region) -> Lines:
        """Render the content for a widget.

        Args:
            widget (Widget): A widget.
            region (Region): A region of the widget to render.

        Returns:
            Lines: Rendered lines.
        """
        (base_background, base_color), (background, color) = widget.colors
        padding = widget.styles.padding + widget.scrollbar_gutter
        lines = self.render(
            widget.styles,
            widget.region.size,
            base_background,
            background,
            widget.render_line,
            content_size=widget.content_region.size,
            padding=padding,
            crop=crop,
        )
        return lines

    def render(
        self,
        styles: StylesBase,
        size: Size,
        base_background: Color,
        background: Color,
        render_content_line: RenderLineCallback,
        content_size: Size | None = None,
        padding: Spacing | None = None,
        crop: Region | None = None,
    ) -> Lines:
        """Render a widget content plus CSS styles.

        Args:
            styles (StylesBase): CSS Styles object.
            size (Size): Size of widget.
            base_background (Color): Background color beneath widget.
            background (Color): Background color of widget.
            render_content_line (RenderLineCallback): Callback to render content line.
            content_size (Size | None, optional): Size of content or None to assume full size. Defaults to None.
            padding (Spacing | None, optional): Override padding from Styles, or None to use styles.padding. Defaults to None.
            crop (Region | None, optional): Region to crop to. Defaults to None.

        Returns:
            Lines: Rendered lines.
        """
        if content_size is None:
            content_size = size
        if padding is None:
            padding = styles.padding
        if crop is None:
            crop = size.region

        width, height = size
        if width != self._width:
            self.clear()
            self._width = width
        lines: Lines = []
        add_line = lines.append
        simplify = Segment.simplify

        is_dirty = self._dirty_lines.__contains__
        render_line = self.render_line
        for y in crop.line_range:
            if is_dirty(y) or y not in self._cache:
                line = render_line(
                    styles,
                    y,
                    size,
                    content_size,
                    padding,
                    base_background,
                    background,
                    render_content_line,
                )
                line = list(simplify(line))
                self._cache[y] = line
            else:
                line = self._cache[y]
            add_line(line)
        self._dirty_lines.difference_update(crop.line_range)

        if crop.column_span != (0, width):
            _line_crop = line_crop
            x1, x2 = crop.column_span
            lines = [_line_crop(line, x1, x2, width) for line in lines]

        return lines

    def render_line(
        self,
        styles: StylesBase,
        y: int,
        size: Size,
        content_size: Size,
        padding: Spacing,
        base_background: Color,
        background: Color,
        render_content_line: RenderLineCallback,
    ) -> list[Segment]:
        """Render a styled line.

        Args:
            styles (StylesBase): Styles object.
            y (int): The y coordinate of the line (relative to widget screen offset).
            size (Size): Size of the widget.
            content_size (Size): Size of the content area.
            padding (Spacing): Padding.
            base_background (Color): Background color of widget beneath this line.
            background (Color): Background color of widget.
            render_content_line (RenderLineCallback): Callback to render a line of content.

        Returns:
            list[Segment]: _description_
        """

        gutter = styles.gutter
        width, height = size
        content_width, content_height = content_size

        pad_top, pad_right, pad_bottom, pad_left = padding

        (
            (border_top, border_top_color),
            (border_right, border_right_color),
            (border_bottom, border_bottom_color),
            (border_left, border_left_color),
        ) = styles.border

        (
            (outline_top, outline_top_color),
            (outline_right, outline_right_color),
            (outline_bottom, outline_bottom_color),
            (outline_left, outline_left_color),
        ) = styles.outline

        from_color = Style.from_color

        rich_style = styles.rich_style
        inner = from_color(bgcolor=background.rich_color) + rich_style
        outer = from_color(bgcolor=base_background.rich_color)

        def post(segments: Iterable[Segment]) -> list[Segment]:
            """Post process segments to apply opacity and tint.

            Args:
                segments (Iterable[Segment]): Iterable of segments.

            Returns:
                list[Segment]: New list of segments
            """
            if styles.opacity != 1.0:
                segments = Opacity.process_segments(segments, styles.opacity)
            if styles.tint.a:
                segments = Tint.process_segments(segments, styles.tint)
            return segments if isinstance(segments, list) else list(segments)

        line: Iterable[Segment]
        # Draw top or bottom borders (A)
        if (border_top and y == 0) or (border_bottom and y == height - 1):
            border_color = border_top_color if y == 0 else border_bottom_color
            box_segments = get_box(
                border_top if y == 0 else border_bottom,
                inner,
                outer,
                from_color(color=border_color.rich_color),
            )
            line = render_row(
                box_segments[0 if y == 0 else 2],
                width,
                border_left != "",
                border_right != "",
            )

        # Draw padding (B)
        elif (pad_top and y < gutter.top) or (
            pad_bottom and y >= height - gutter.bottom
        ):
            background_style = from_color(
                color=rich_style.color, bgcolor=background.rich_color
            )
            left_style = from_color(color=border_left_color.rich_color)
            left = get_box(border_left, inner, outer, left_style)[1][0]
            right_style = from_color(color=border_right_color.rich_color)
            right = get_box(border_right, inner, outer, right_style)[1][2]
            if border_left and border_right:
                line = [left, Segment(" " * (width - 2), background_style), right]
            elif border_left:
                line = [left, Segment(" " * (width - 1), background_style)]
            elif border_right:
                line = [Segment(" " * (width - 1), background_style), right]
            else:
                line = [Segment(" " * width, background_style)]
        else:
            # Content with border and padding (C)
            content_y = y - gutter.top
            if content_y < content_height:
                line = render_content_line(y - gutter.top)
            else:
                line = [Segment(" " * content_width, inner)]
            if inner:
                line = Segment.apply_style(line, inner)
            line = line_pad(line, pad_left, pad_right, inner)

            if border_left or border_right:
                # Add left / right border
                left_style = from_color(border_left_color.rich_color)
                left = get_box(border_left, inner, outer, left_style)[1][0]
                right_style = from_color(border_right_color.rich_color)
                right = get_box(border_right, inner, outer, right_style)[1][2]

                if border_left and border_right:
                    line = [left, *line, right]
                elif border_left:
                    line = [left, *line]
                else:
                    line = [*line, right]

        # Draw any outline
        if (outline_top and y == 0) or (outline_bottom and y == height - 1):
            # Top or bottom outlines
            outline_color = outline_top_color if y == 0 else outline_bottom_color
            box_segments = get_box(
                outline_top if y == 0 else outline_bottom,
                inner,
                outer,
                from_color(color=outline_color.rich_color),
            )
            line = render_row(
                box_segments[0 if y == 0 else 2],
                width,
                outline_left != "",
                outline_right != "",
            )

        elif outline_left or outline_right:
            # Lines in side outline
            left_style = from_color(outline_left_color.rich_color)
            left = get_box(outline_left, inner, outer, left_style)[1][0]
            right_style = from_color(outline_right_color.rich_color)
            right = get_box(outline_right, inner, outer, right_style)[1][2]
            line = line_trim(list(line), outline_left != "", outline_right != "")
            if outline_left and outline_right:
                line = [left, *line, right]
            elif outline_left:
                line = [left, *line]
            else:
                line = [*line, right]

        return post(line)
