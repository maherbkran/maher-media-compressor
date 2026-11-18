"""Import the approved reference's visual assets; the desktop adapter owns behavior."""
from pathlib import Path
import base64,re,json,hashlib,sys

def build(reference, destination):
    source=Path(reference).read_text(encoding='utf-8-sig')
    out=Path(destination); out.mkdir(parents=True,exist_ok=True)
    css='\n'.join(re.findall(r'<style[^>]*>(.*?)</style>',source,re.S))
    (out/'approved.css').write_bytes(css.encode('utf-8'))
    for identifier,name in (('sampleData','demo.jpg'),('sampleVideoData','demo.mp4')):
        match=re.search(r'<script[^>]*id="'+identifier+r'"[^>]*>(.*?)</script>',source,re.S)
        (out/name).write_bytes(base64.b64decode(match.group(1).strip()))
    body=re.search(r'<body>(.*?)</body>',source,re.S).group(1)
    body=re.sub(r'<script\b[^>]*>.*?</script>','',body,flags=re.S)
    body=re.sub(r'<input id="(?:fileInput|folderInput)"[^>]*>','',body)
    body=re.sub(r'<div id="advancedBody".*?</div>','',body,flags=re.S)
    body=body.replace('aria-controls="advancedBody"','aria-controls="nativeSettingsDialog"')
    body=body.replace('تواصل عبر LinkedIn','تواصل عبر واتساب').replace('عبر LinkedIn','عبر واتساب')
    body=body.replace('https://ae.linkedin.com/in/maher-bakran/ar','https://wa.me/971543386217')
    body=body.replace('نزّل نسخة من الملف أو حزمة ZIP للملفات المتعددة.','تُحفظ النسخ تلقائياً بجانب الأصول، ويمكنك اختيار مجلد آخر من إعدادات الحفظ.')
    body=body.replace('يستخدم ضغط الفيديو FFmpeg.wasm.','يستخدم محرّك سطح المكتب FFmpeg وPillow محلياً، دون حد برمجي لحجم الفيديو.')
    body=body.replace('https://github.com/ffmpegwasm/ffmpeg.wasm-core','https://www.ffmpeg.org/').replace('FFmpeg.wasm core source','FFmpeg')
    body=body.replace('https://github.com/ffmpegwasm/ffmpeg.wasm/tree/v0.12.10','https://pillow.readthedocs.io/').replace('Build sources','Pillow')
    body=body.replace('target="_blank"','')
    body=body.replace('<div class="queue-actions">','<div class="queue-actions"><button class="btn mini" id="reportBtn" disabled><svg class="ic"><use href="#ph-download-simple"></use></svg>التقرير</button><button class="btn mini" id="destinationBtn"><svg class="ic"><use href="#ph-folder-open"></use></svg>الحفظ</button>')
    body=body.replace('<div id="jobErrors"','<button class="btn mini danger" id="stopJob">إيقاف الضغط</button><div id="jobErrors"')
    body=body.replace('تُزال الملفات ونتائجها من هذه الجلسة فقط. تبقى أصول الملفات على جهازك.','تُزال الملفات من هذه القائمة فقط. الأصول والنتائج المحفوظة على جهازك تبقى كما هي.')
    body=body.replace('</main>','<p id="nativeStatus" class="sr" role="status" aria-live="polite"></p></main>')
    (out/'approved-body.html').write_text(body,encoding='utf-8')
    games=re.search(r"let game=null;.*?\ninitialize\(\);",re.findall(r'<script\b[^>]*>(.*?)</script>',source,re.S)[-1],re.S).group(0)
    (out/'approved-games.js').write_text(games.rsplit('initialize();',1)[0],encoding='utf-8')
    comments='\n\n'.join(c for c in re.findall(r'<!--(.*?)-->',source,re.S) if 'License' in c or 'Copyright' in c)
    (out/'APPROVED-ASSETS-LICENSES.txt').write_text(comments,encoding='utf-8')
    (out/'reference.json').write_text(json.dumps({'input_sha256':hashlib.sha256(Path(reference).read_bytes()).hexdigest(),'approved_css_sha256':hashlib.sha256(css.encode()).hexdigest(),'note':'Approved layout, fonts, icons, artwork and game presentation retained. Native adapter replaces browser-only encoding and saving.'},indent=2),encoding='utf-8')

if __name__=='__main__':build(sys.argv[1],sys.argv[2])
