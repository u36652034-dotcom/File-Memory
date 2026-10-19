"""Generate the File Memory Windows icon with Pillow.

The icon is deliberately generated during a build instead of committed as a
binary-only asset.  This keeps the design reproducible and makes it possible
to regenerate the exact ICO on a clean machine.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw


INDIGO = (35, 29, 83, 255)
CHARTREUSE = (205, 255, 73, 255)
PAPER = (249, 247, 238, 255)
SIZES = (16, 24, 32, 48, 64, 128, 256)


def make_icon(output: Path) -> Path:
    """Write a multi-resolution ICO containing the File Memory mark."""

    output.parent.mkdir(parents=True, exist_ok=True)
    images: list[Image.Image] = []
    for size in SIZES:
        image = Image.new("RGBA", (size, size), INDIGO)
        draw = ImageDraw.Draw(image)
        margin = max(1, size // 10)
        # A soft paper tile keeps the mark readable in the taskbar.
        draw.rounded_rectangle(
            (margin, margin, size - margin, size - margin),
            radius=max(2, size // 8),
            fill=PAPER,
        )
        # A bright feather is the File Memory mark: light, private, and easy
        # to recognize in the taskbar at 16px.
        cx, cy = size * 0.53, size * 0.54
        feather = [
            (size * 0.23, size * 0.73), (size * 0.27, size * 0.40),
            (size * 0.48, size * 0.18), (size * 0.76, size * 0.16),
            (size * 0.82, size * 0.31), (size * 0.66, size * 0.58),
            (size * 0.39, size * 0.76),
        ]
        draw.polygon(feather, fill=CHARTREUSE)
        stem = max(2, size // 12)
        draw.line((size * 0.23, size * 0.78, size * 0.73, size * 0.25), fill=INDIGO, width=stem)
        for fraction in (0.37, 0.47, 0.57, 0.67):
            x = size * fraction
            y = size * (0.50 - (fraction - 0.37) * 0.48)
            draw.line((x, y, x - size * 0.16, y + size * 0.10), fill=INDIGO, width=max(1, size // 18))
        draw.ellipse((cx - size * 0.035, cy - size * 0.035, cx + size * 0.035, cy + size * 0.035), fill=PAPER)
        images.append(image)

    images[-1].save(output, format="ICO", sizes=[(size, size) for size in SIZES], append_images=images[:-1])
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "assets" / "filememory.ico",
        help="destination ICO path (default: assets/filememory.ico)",
    )
    args = parser.parse_args()
    print(f"Generating {args.output}")
    make_icon(args.output)


if __name__ == "__main__":
    main()
