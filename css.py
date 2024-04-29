import os


def combine_css(directory, output_file):
    css_contents = ""
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith(".css"):
                file_path = os.path.join(root, file)
                with open(file_path, "r", encoding="utf-8") as css_file:
                    css_contents += css_file.read() + "\n"

    with open(output_file, "w", encoding="utf-8") as output_css:
        output_css.write(css_contents)
    print(f"All CSS combined into {output_file}")


# Set the path to your design-system directory and the output file path
design_system_path = "/Users/glennsorrentino/Nextcloud/Git/hushline-website/design-system"
output_css_path = "/Users/glennsorrentino/Nextcloud/Git/hushline/hushline/static/css/combined.css"

combine_css(design_system_path, output_css_path)
