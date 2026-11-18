"""Token-scoped loopback media streaming; no uploads or arbitrary file routes."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import mimetypes,secrets,threading
from urllib.parse import urlsplit,unquote


class MediaServer:
    def __init__(self,ui_root):
        self.root=Path(ui_root)
        self.token=secrets.token_urlsafe(24)
        self.media={}; self.lock=threading.Lock(); self.index=b''; self.channel=b''
        owner=self
        class Handler(BaseHTTPRequestHandler):
            protocol_version='HTTP/1.1'
            def log_message(self,*args): pass
            def do_HEAD(self): self.serve(False)
            def do_GET(self): self.serve(True)
            def serve(self,body):
                path=unquote(urlsplit(self.path).path)
                prefix='/'+owner.token+'/'
                if not path.startswith(prefix): self.send_error(404); return
                name=path[len(prefix):]
                data=None; file=None; mime=None
                if name in ('','index.html'): data=owner.index; mime='text/html; charset=utf-8'
                elif name=='qwebchannel.js': data=owner.channel; mime='application/javascript'
                elif name.startswith('media/'):
                    with owner.lock: file=owner.media.get(name[6:])
                elif name in ('approved.css','native.css','desktop.js','approved-games.js','demo.jpg','demo.mp4'):
                    file=owner.root/name
                if data is None and (file is None or not file.is_file()): self.send_error(404); return
                try:
                    total=len(data) if data is not None else file.stat().st_size
                    mime=mime or mimetypes.guess_type(str(file))[0] or 'application/octet-stream'
                    start,end=0,total-1; status=200
                    header=self.headers.get('Range')
                    if header:
                        try:
                            if not header.startswith('bytes=') or ',' in header: raise ValueError()
                            first,last=header[6:].split('-',1)
                            if first:
                                start=int(first); end=min(int(last),total-1) if last else total-1
                            else:
                                length=int(last)
                                if length<=0: raise ValueError()
                                start=max(0,total-length)
                            if start<0 or start>=total or end<start: raise ValueError()
                            status=206
                        except (ValueError,TypeError):
                            self.send_response(416); self.send_header('Content-Range',f'bytes */{total}')
                            self.send_header('Content-Length','0'); self.end_headers(); return
                    self.send_response(status); self.send_header('Content-Type',mime)
                    self.send_header('Content-Length',str(max(0,end-start+1)))
                    self.send_header('Accept-Ranges','bytes')
                    if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Cross-Origin-Resource-Policy','same-origin')
                    self.send_header('Referrer-Policy','no-referrer')
                    self.send_header('Cache-Control','no-store' if data is not None else 'private, max-age=300')
                    if name in ('','index.html'):
                        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob: data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'")
                    self.end_headers()
                    if not body:return
                    if data is not None: self.wfile.write(data[start:end+1]); return
                    with file.open('rb') as stream:
                        stream.seek(start); remaining=end-start+1
                        while remaining>0:
                            chunk=stream.read(min(65536,remaining))
                            if not chunk:break
                            self.wfile.write(chunk); remaining-=len(chunk)
                except (OSError,ConnectionError): pass
        self.http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.http.daemon_threads=True; self.http.block_on_close=False
        self.origin=f'http://127.0.0.1:{self.http.server_port}'
        self.base=self.origin+'/'+self.token+'/'
        self.thread=threading.Thread(target=lambda:self.http.serve_forever(poll_interval=.05),daemon=True)

    def register(self,path):
        key=secrets.token_urlsafe(20)
        with self.lock:self.media[key]=Path(path)
        return self.base+'media/'+key

    def start(self):self.thread.start()
    def close(self):self.http.shutdown();self.http.server_close();self.thread.join(timeout=2)
