import os
from typing import List
from PIL import Image, ImageOps, ImageDraw

def create_pinterest_collage(image_paths: List[str], output_path: str, width: int = 1200, height: int = 600) -> str:
    """
    Arranges 1 to 3 images side-by-side with rounded card styling and spacing.
    Returns the absolute path to the generated composite PNG.
    """
    card_count = min(len(image_paths), 3)
    if card_count == 0:
        raise ValueError("At least one image is required for a collage.")

    margin = 20
    spacing = 15
    total_spacing = spacing * (card_count - 1) + (margin * 2)
    card_width = (width - total_spacing) // card_count
    card_height = height - (margin * 2)

    collage = Image.new("RGBA", (width, height), (255, 245, 247, 255)) # Soft blossom tint

    for i in range(card_count):
        with Image.open(image_paths[i]) as img:
            img = ImageOps.fit(img, (card_width, card_height), Image.Resampling.LANCZOS)
            mask = Image.new("L", (card_width, card_height), 0)
            draw = ImageDraw.Draw(mask)
            draw.rounded_rectangle([(0, 0), (card_width, card_height)], radius=24, fill=255)
            
            x = margin + i * (card_width + spacing)
            y = margin
            collage.paste(img, (x, y), mask=mask)

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    collage.save(output_path, "PNG")
    return os.path.abspath(output_path)
