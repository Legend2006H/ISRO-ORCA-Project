from pathlib import Path

from pypdf import PdfReader


output = Path("tmp_pdf_images")
output.mkdir(exist_ok=True)
for path in sorted(Path(r"C:\Users\hrush\Downloads").glob("czmp_*.pdf")):
    page = PdfReader(path).pages[0]
    images = list(page.images)
    if not images:
        print(f"NO IMAGE: {path.name}")
        continue
    image = max(images, key=lambda item: len(item.data))
    destination = output / f"{path.stem}{image.name[image.name.rfind('.'):]}"
    destination.write_bytes(image.data)
    print(f"{path.name}: {len(images)} embedded image(s), selected {destination.name}, {len(image.data)} bytes")
