import sys
from waveshare_epd import epd2in7_V2
from PIL import Image

def clear_screen(epd):
    print("Clearing the screen")
    image = Image.new('1', (epd.height, epd.width), 255)
    image_rotated = image.rotate(90, expand=True)
    epd.display(epd.getbuffer(image_rotated))
    epd.sleep()

def main():
    print("Starting clear_display script")
    epd = epd2in7_V2.EPD()
    epd.init()
    clear_screen(epd)

if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)