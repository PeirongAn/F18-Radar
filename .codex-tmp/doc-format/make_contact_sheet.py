from pathlib import Path
import sys
from PIL import Image, ImageDraw, ImageFont


def main(folder: str, out_dir: str, group_size: int = 6):
    src = Path(folder)
    dst = Path(out_dir)
    dst.mkdir(parents=True, exist_ok=True)
    pages = sorted(src.glob("page-*.png"), key=lambda p: int(p.stem.split("-")[-1]))
    thumb_w = 620
    margin = 24
    label_h = 36
    for group_no, start in enumerate(range(0, len(pages), group_size), 1):
        group = pages[start:start + group_size]
        thumbs = []
        for p in group:
            im = Image.open(p).convert("RGB")
            h = round(im.height * thumb_w / im.width)
            thumbs.append((p, im.resize((thumb_w, h), Image.Resampling.LANCZOS)))
        cols = 2
        rows = (len(thumbs) + cols - 1) // cols
        cell_h = max(im.height for _, im in thumbs) + label_h
        sheet = Image.new("RGB", (cols * thumb_w + (cols + 1) * margin, rows * cell_h + (rows + 1) * margin), "#d8d8d8")
        draw = ImageDraw.Draw(sheet)
        for i, (p, im) in enumerate(thumbs):
            row, col = divmod(i, cols)
            x = margin + col * (thumb_w + margin)
            y = margin + row * (cell_h + margin)
            draw.text((x, y), f"Page {int(p.stem.split('-')[-1])}", fill="black")
            sheet.paste(im, (x, y + label_h))
        sheet.save(dst / f"contact-{group_no:02d}.jpg", quality=92)
    print(f"pages={len(pages)} sheets={(len(pages)+group_size-1)//group_size}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 6)
