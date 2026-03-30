import os
from PIL import Image

def convert_to_png(input_path, output_dir=None):
    """
    Converts an image to PNG format.
    Args:
        input_path (str): Path to the input image file.
        output_dir (str, optional): Directory to save the PNG file. Defaults to the input file's directory.
    Returns:
        str: Path to the converted PNG file.
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"File not found: {input_path}")

    if output_dir is None:
        output_dir = os.path.dirname(input_path)
    os.makedirs(output_dir, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(output_dir, base_name + '.png')

    with Image.open(input_path) as img:
        img.convert('RGBA').save(output_path, 'PNG')
    return output_path

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Convert images to PNG format.")
    parser.add_argument("input", help="Path to the input image file.")
    parser.add_argument("-o", "--output-dir", help="Directory to save the PNG file.")
    args = parser.parse_args()

    try:
        result = convert_to_png(args.input, args.output_dir)
        print(f"Converted image saved to: {result}")
    except Exception as e:
        print(f"Error: {e}")
