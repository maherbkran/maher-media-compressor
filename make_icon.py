from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parent
image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
d = ImageDraw.Draw(image)
d.rounded_rectangle((8, 8, 248, 248), radius=54, fill="#172d37")
d.rounded_rectangle((68, 63, 188, 193), radius=17, fill="#b1edcf")
d.rounded_rectangle((80, 76, 176, 181), radius=8, fill="#16835b")
d.ellipse((138, 88, 157, 107), fill="#b1edcf")
d.polygon([(88, 160), (112, 121), (133, 143), (147, 129), (169, 160)], fill="#b1edcf")
d.line([(27, 128), (58, 128)], fill="white", width=10)
d.polygon([(61, 128), (43, 111), (43, 145)], fill="white")
d.line([(198, 128), (229, 128)], fill="white", width=10)
d.polygon([(195, 128), (213, 111), (213, 145)], fill="white")
image.save(root / "app.ico", sizes=[(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)])

