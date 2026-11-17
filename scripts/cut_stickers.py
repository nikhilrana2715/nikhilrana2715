"""One-off: cut chibi stickers out of the collage with GrabCut -> transparent PNGs."""
import cv2, numpy as np
from PIL import Image

SRC = "assets/src/chibi-collage.jpg"
BOXES = {  # x0, y0, x1, y1 in source px
    "wink":  (2, 30, 178, 228),
    "jump":  (372, 0, 612, 232),
    "drink": (428, 255, 612, 432),
    "think": (2, 322, 182, 540),
    "peace": (448, 498, 612, 702),
}
img = cv2.imread(SRC)
H, W = img.shape[:2]
for name, (x0, y0, x1, y1) in BOXES.items():
    x0, y0, x1, y1 = max(0, x0), max(0, y0), min(W, x1), min(H, y1)
    crop = img[y0:y1, x0:x1].copy()
    mask = np.zeros(crop.shape[:2], np.uint8)
    rect = (4, 4, crop.shape[1] - 8, crop.shape[0] - 8)
    bgd, fgd = np.zeros((1, 65), np.float64), np.zeros((1, 65), np.float64)
    cv2.grabCut(crop, mask, rect, bgd, fgd, 8, cv2.GC_INIT_WITH_RECT)
    m = np.where((mask == 1) | (mask == 3), 255, 0).astype(np.uint8)
    # keep largest blob, smooth edge
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n > 1:
        big = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        m = np.where(lab == big, 255, 0).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    m = cv2.GaussianBlur(m, (3, 3), 0)
    rgba = cv2.cvtColor(crop, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = m
    Image.fromarray(rgba).save(f"assets/src/sticker-{name}.png")
    print(name, crop.shape)
