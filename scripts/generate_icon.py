"""Generate the File Memory Windows icon with Pillow.

The icon is deliberately generated during a build instead of committed as a
binary-only asset.  This keeps the design reproducible and makes it possible
to regenerate the exact ICO on a clean machine.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


INDIGO = (42, 43, 181, 255)
CHARTREUSE = (205, 255, 18, 255)
BLACK = (4, 4, 8, 255)
SIZES = (16, 24, 32, 48, 64, 128, 256)


def _font(size: int) -> ImageFont.ImageFont:
    candidates = []
    windir = os.getenv("WINDIR")
    if windir:
        candidates.append(Path(windir) / "Fonts" / "arialbd.ttf")
    candidates.extend((Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),))
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), max(8, size))
    return ImageFont.load_default()


def make_icon(output: Path) -> Path:
    """Write a multi-resolution ICO containing the File Memory mark."""

    output.parent.mkdir(parents=True, exist_ok=True)
    images: list[Image.Image] = []
    for size in SIZES:
        image = Image.new("RGBA", (size, size), INDIGO)
        draw = ImageDraw.Draw(image)
        # The supplied reference mark: blue field, lime outer keyline,
        # sixteen lime tiles, and a black FM monogram over the middle.
        border = max(1, size // 18)
        draw.rectangle((border, border, size - border - 1, size - border - 1), outline=CHARTREUSE, width=border)
        inset = max(2, size // 8)
        gap = max(1, size // 28)
        grid_size = size - inset * 2
        tile = max(1, (grid_size - gap * 3) // 4)
        for row in range(4):
            for column in range(4):
                left = inset + column * (tile + gap)
                top = inset + row * (tile + gap)
                draw.rectangle((left, top, left + tile, top + tile), fill=CHARTREUSE)
        font_size = max(8, int(size * 0.43))
        font = _font(font_size)
        label = "FM"
        box = draw.textbbox((0, 0), label, font=font, stroke_width=0)
        label_width, label_height = box[2] - box[0], box[3] - box[1]
        draw.text(
            ((size - label_width) / 2 - box[0], (size - label_height) / 2 - box[1] + size * 0.01),
            label,
            fill=BLACK,
            font=font,
        )
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
