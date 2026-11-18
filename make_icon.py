"""Convert the approved transparent mark into the Windows icon container."""
from pathlib import Path
from PIL import Image
root = Path(__file__).resolve().parent
with Image.open(root / 'assets' / 'maher-mark.png') as mark:
    mark.save(root / 'app.ico', sizes=[(16,16), (24,24), (32,32), (48,48), (64,64), (128,128), (256,256)])
