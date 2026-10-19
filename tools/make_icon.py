"""Generates assets/icon.ico (run by CI before building)."""
from pathlib import Path
from PIL import Image, ImageDraw

S = 256
k = S / 64
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, S - 1, S - 1), radius=48, fill=(18, 32, 56, 255))
d.ellipse((6*k, 14*k, 58*k, 50*k), fill=(60, 120, 200, 255))
d.polygon([(34*k, 30*k), (24*k, 46*k), (32*k, 46*k), (28*k, 58*k), (42*k, 40*k), (34*k, 40*k)],
          fill=(255, 215, 0, 255))
out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
out.parent.mkdir(exist_ok=True)
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("wrote", out)
