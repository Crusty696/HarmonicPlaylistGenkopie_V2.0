"""
Simple Icon Generator for HPG v3.0
Creates a basic but professional icon if you don't have one
Requires: pip install Pillow
"""

try:
    from PIL import Image, ImageDraw, ImageFont
    import sys
    import os
except ImportError:
    print("ERROR: Pillow not installed!")
    print("Please run: pip install Pillow")
    sys.exit(1)


def create_icon():
    """Create a simple but professional app icon"""

    print("Creating HPG v3.0 icon...")

    # Icon specifications
    size = 256
    background_color = '#1E88E5'  # Material Blue
    circle_color = '#212121'      # Dark Gray
    text_color = '#FFFFFF'        # White

    # Create image
    img = Image.new('RGB', (size, size), background_color)
    draw = ImageDraw.Draw(img)

    # Draw circle
    margin = 20
    draw.ellipse([margin, margin, size-margin, size-margin],
                 fill=circle_color, outline=background_color, width=4)

    # Try to use system font, fallback to default
    try:
        # Try different font paths (Windows)
        font_paths = [
            "C:\\Windows\\Fonts\\segoeui.ttf",      # Segoe UI
            "C:\\Windows\\Fonts\\arial.ttf",        # Arial
            "C:\\Windows\\Fonts\\calibri.ttf",      # Calibri
        ]

        font_large = None
        font_small = None

        for font_path in font_paths:
            if os.path.exists(font_path):
                font_large = ImageFont.truetype(font_path, 100)
                font_small = ImageFont.truetype(font_path, 40)
                break

        if not font_large:
            # Fallback to default
            font_large = ImageFont.load_default()
            font_small = ImageFont.load_default()

    except Exception:
        font_large = ImageFont.load_default()
        font_small = ImageFont.load_default()

    # Draw text "HPG"
    text_main = "HPG"

    # Calculate text position (centered)
    bbox = draw.textbbox((0, 0), text_main, font=font_large)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    x = (size - text_width) // 2
    y = (size - text_height) // 2 - 20

    draw.text((x, y), text_main, fill=text_color, font=font_large)

    # Draw version "v3.0"
    text_version = "v3.0"
    bbox_version = draw.textbbox((0, 0), text_version, font=font_small)
    version_width = bbox_version[2] - bbox_version[0]

    x_version = (size - version_width) // 2
    y_version = y + text_height + 10

    draw.text((x_version, y_version), text_version,
              fill='#BBBBBB', font=font_small)

    # Save as ICO with multiple sizes
    icon_sizes = [(16, 16), (32, 32), (48, 48), (256, 256)]

    try:
        img.save('icon.ico', format='ICO', sizes=icon_sizes)
        print("[SUCCESS] Icon created successfully: icon.ico")
        print(f"  Size: 256x256 pixels")
        print(f"  Format: Windows Icon (.ico)")
        print(f"  Includes: 16x16, 32x32, 48x48, 256x256")
        print()
        print("Next steps:")
        print("  1. Check icon.ico in project folder")
        print("  2. Run: build.bat")
        print("  3. Your exe will have the custom icon!")
        return True
    except Exception as e:
        print(f"[ERROR] Error saving icon: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("  HPG v3.0 - Icon Generator")
    print("=" * 60)
    print()

    # Check if icon already exists
    if os.path.exists('icon.ico'):
        response = input("icon.ico already exists. Overwrite? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            sys.exit(0)

    # Create icon
    success = create_icon()

    if not success:
        print()
        print("If icon creation failed, you can:")
        print("  1. Use online tool: https://favicon.io/favicon-converter/")
        print("  2. Download free icon: https://www.flaticon.com/")
        print("  3. Skip icon (PyInstaller will use Python default)")

    print()
    input("Press Enter to close...")
