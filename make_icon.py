"""assets/icon_source.jpg (üretilmiş görsel) -> yuvarlatılmış köşeli, şeffaf arka planlı assets/icon.ico + icon.png"""
from PIL import Image, ImageDraw

src = Image.open("assets/icon_source.jpg").convert("RGB")
# Koyu arka plandan simgenin sınırlarını bul
w, h = src.size
px = src.load()
xs, ys = [], []
for y in range(0, h, 2):
    for x in range(0, w, 2):
        r, g, b = px[x, y]
        if b > 90 and b > r + 20:  # mavi/mor gövde
            xs.append(x)
            ys.append(y)
box = (min(xs) + 2, min(ys) + 2, max(xs) - 2, max(ys) - 2)
side = max(box[2] - box[0], box[3] - box[1])
cx, cy = (box[0] + box[2]) // 2, (box[1] + box[3]) // 2
box = (cx - side // 2, cy - side // 2, cx + side // 2, cy + side // 2)
img = src.crop(box).resize((512, 512), Image.LANCZOS).convert("RGBA")

mask = Image.new("L", (512 * 4, 512 * 4), 0)
ImageDraw.Draw(mask).rounded_rectangle((0, 0, 512 * 4 - 1, 512 * 4 - 1), radius=118 * 4, fill=255)
img.putalpha(mask.resize((512, 512), Image.LANCZOS))
img.save("assets/icon.png")
img.save("assets/icon.ico", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
print("icon ok", box)
