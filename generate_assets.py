import os
from PIL import Image, ImageDraw

def generate_icon():
    print("Generowanie ikony...")
    size = 256
    # Przezroczyste tło dla ikony
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Rysujemy zaokrąglony kwadrat dla tła (ciemny)
    draw.rounded_rectangle([16, 16, 240, 240], radius=40, fill=(10, 10, 10, 255))
    
    # Kropki układające się w minimalistyczne S
    dots = [
        (2,1), (3,1), (4,1), (5,1),
        (1,2), (1,3), 
        (2,4), (3,4), (4,4),
        (5,5), (5,6),
        (1,7), (2,7), (3,7), (4,7)
    ]
    
    offset_x = 36
    offset_y = 36
    spacing = 26
    
    for row in range(1, 8):
        for col in range(1, 7):
            x = offset_x + col * spacing
            y = offset_y + row * spacing
            if (col, row) in dots:
                # Główne kropki
                draw.ellipse([x-10, y-10, x+10, y+10], fill=(255, 42, 42, 255))
            else:
                # Tło kropek
                draw.ellipse([x-4, y-4, x+4, y+4], fill=(40, 40, 40, 255))
                
    img.save("icon_nothing.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32)])
    print("Zapisano icon_nothing.ico")

if __name__ == "__main__":
    generate_icon()
