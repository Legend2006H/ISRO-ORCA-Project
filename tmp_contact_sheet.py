from pathlib import Path

from PIL import Image, ImageDraw


files = sorted(Path("tmp_pdf_images").glob("*.jpg"))
thumb_size = (430, 600)
sheet = Image.new("RGB", (thumb_size[0] * 3, (thumb_size[1] + 35) * 2), "white")
draw = ImageDraw.Draw(sheet)
for index, path in enumerate(files):
    with Image.open(path) as image:
        image.thumbnail(thumb_size)
        x = (index % 3) * thumb_size[0]
        y = (index // 3) * (thumb_size[1] + 35)
        sheet.paste(image, (x, y + 30))
        draw.text((x + 8, y + 8), path.stem, fill="black")
sheet.save("tmp_pdf_images/contact_sheet.jpg", quality=85)
