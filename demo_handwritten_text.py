import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from handwrite.cli import converters


DEFAULT_SAMPLE = Path(__file__).resolve().parent / "tests" / "test_data" / "sheettopng" / "excellent.jpg"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "demo_output"


def generate_font(sample_path: str, output_dir: str, font_name: str = "MyFont") -> str:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {"filename": font_name}
    converters(sample_path, str(out_dir), config=None, metadata=metadata)
    font_path = out_dir / f"{font_name}.ttf"
    if not font_path.exists():
        raise FileNotFoundError(f"Expected generated font at {font_path}")
    return str(font_path)


def render_text_to_image(text: str, font_path: str, output_path: str, font_size: int = 120):
    margin = 60
    padding = 30
    canvas = Image.new("RGB", (1800, 700), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.truetype(font_path, font_size)

    words = text.splitlines() or [text]
    wrapped_lines = []
    for line in words:
        if not line:
            wrapped_lines.append("")
            continue
        if len(line) < 26:
            wrapped_lines.append(line)
            continue
        chunks = [line[i : i + 24] for i in range(0, len(line), 24)]
        wrapped_lines.extend(chunks)

    start_y = margin
    for line in wrapped_lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        line_height = bbox[3] - bbox[1]
        x = margin
        y = start_y
        draw.text((x, y), line, font=font, fill="black")
        start_y += line_height + padding

    canvas = canvas.crop((0, 0, canvas.width, max(start_y + margin, canvas.height)))
    canvas.save(output_path)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Turn pasted text into a handwritten-style PNG using a generated font.")
    parser.add_argument("text", nargs="?", default=None, help="Text to render. If omitted, you will be prompted interactively.")
    parser.add_argument("--sample", default=str(DEFAULT_SAMPLE), help="Path to the handwriting sample sheet image.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR / "handwritten_text.png"), help="Output PNG path.")
    parser.add_argument("--font-name", default="MyFont", help="Font name used when generating the handwritten font.")
    parser.add_argument("--font-size", type=int, default=120, help="Font size for the final rendered text.")
    args = parser.parse_args()

    if args.text is None:
        args.text = input("Paste the text you want to convert to handwriting: ")

    sample_path = str(Path(args.sample).expanduser())
    output_path = str(Path(args.output).expanduser())
    out_dir = Path(output_path).resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)

    font_path = generate_font(sample_path, str(out_dir), args.font_name)
    image_path = render_text_to_image(args.text, font_path, output_path, args.font_size)
    print(f"Handwritten image saved to: {image_path}")


if __name__ == "__main__":
    main()
