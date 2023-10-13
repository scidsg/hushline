import os
import sys
import time
import qrcode
from waveshare_epd import epd2in7_V2
from PIL import Image, ImageDraw, ImageFont

def generate_qr_code(data):
    print("Generating QR code...")
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill='black', back_color='white')
    img = img.convert('1')  # Convert to 1-bit image
    
    # Calculate the new size preserving aspect ratio
    base_width, base_height = img.size
    aspect_ratio = float(base_width) / float(base_height)
    new_height = int(epd2in7_V2.EPD_HEIGHT)
    new_width = int(aspect_ratio * new_height)

    if new_width > epd2in7_V2.EPD_WIDTH:
        new_width = epd2in7_V2.EPD_WIDTH
        new_height = int(new_width / aspect_ratio)

    # Calculate position to paste
    x_pos = (epd2in7_V2.EPD_WIDTH - new_width) // 2
    y_pos = (epd2in7_V2.EPD_HEIGHT - new_height) // 2
    
    img_resized = img.resize((new_width, new_height))
    
    # Create a blank (white) image to paste the QR code on
    img_blank = Image.new('1', (epd2in7_V2.EPD_WIDTH, epd2in7_V2.EPD_HEIGHT), 255)
    img_blank.paste(img_resized, (x_pos, y_pos))

    # Save to disk for debugging
    img_blank.save("debug_qr_code.png")
    
    return img_blank

def main():
    epd = epd2in7_V2.EPD()
    epd.init()

    # Generate QR code for your URL or data
    qr_code_image = generate_qr_code("https://hushline.local/setup")

    # Clear frame memory
    epd.Clear()
    
    # Display the QR code
    epd.display(epd.getbuffer(qr_code_image))

    time.sleep(2)

    # You could also put it to sleep or perform other operations on the display here
    epd.sleep()
    
if __name__ == "__main__":
    main()