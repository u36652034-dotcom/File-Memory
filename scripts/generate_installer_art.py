"""Generate the branded Inno Setup wizard images from the File Memory palette."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


INDIGO = (42, 43, 181)
LIME = (205, 255, 18)
BLACK = (4, 4, 8)
WHITE = (249, 248, 240)


def font(size: int):
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    for path in candidates:
        if path.is_file():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def draw_mark(draw: ImageDraw.ImageDraw, origin: tuple[int, int], size: int) -> None:
    x, y = origin
    tile = max(5, size // 7)
    gap = max(3, size // 24)
    start = x + tile // 2
    for row in range(4):
        for col in range(4):
            left = start + col * (tile + gap)
            top = y + row * (tile + gap)
            draw.rectangle((left, top, left + tile, top + tile), fill=LIME)
    label = "FM"
    fnt = font(max(20, size // 3))
    box = draw.textbbox((0, 0), label, font=fnt)
    draw.text(
        (x + size // 2 - (box[2] - box[0]) // 2, y + size // 2 - (box[3] - box[1]) // 2),
        label,
        fill=BLACK,
        font=fnt,
    )


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    installer = root / "installer"
    installer.mkdir(parents=True, exist_ok=True)

    wide = Image.new("RGB", (164, 314), INDIGO)
    wide_draw = ImageDraw.Draw(wide)
    draw_mark(wide_draw, (17, 38), 130)
    wide_draw.text((18, 198), "FILE", fill=WHITE, font=font(22))
    wide_draw.text((18, 226), "MEMORY", fill=LIME, font=font(22))
    wide_draw.text((18, 277), "LOCAL · SOLO", fill=WHITE, font=font(10))
    wide.save(installer / "wizard.bmp")

    small = Image.new("RGB", (55, 55), INDIGO)
    draw_mark(ImageDraw.Draw(small), (4, 4), 47)
    small.save(installer / "wizard-small.bmp")
    print(f"Generated installer art in {installer}")


if __name__ == "__main__":
    main()
