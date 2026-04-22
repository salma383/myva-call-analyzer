"""
Run this ONCE to convert your logo PNG into an app .ico file.

Steps:
  1. Save your MyVA logo as:  assets/icons/logo.png
  2. Run:  python create_icon.py
  3. The file  assets/icons/app.ico  will be created.
  4. Then run:  python build_config.py  to rebuild the exe with the icon.
"""
import os
from PIL import Image

SRC = os.path.join("assets", "icons", "logo.png")
DST = os.path.join("assets", "icons", "app.ico")


def create_ico():
    if not os.path.exists(SRC):
        print(f"ERROR: logo not found at {SRC}")
        print("Save your MyVA logo PNG as assets/icons/logo.png and try again.")
        return

    img = Image.open(SRC).convert("RGBA")

    # Generate all standard Windows icon sizes
    sizes = [16, 24, 32, 48, 64, 128, 256]
    icons = []
    for size in sizes:
        resized = img.resize((size, size), Image.LANCZOS)
        icons.append(resized)

    # Save as multi-size .ico
    icons[0].save(
        DST,
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=icons[1:],
    )
    print(f"Icon created: {DST}")
    print("Now run: python build_config.py")


if __name__ == "__main__":
    create_ico()
