"""Desktop controller for the approved HTML view. Files stay in native workers."""
from pathlib import Path
from dataclasses import asdict
import csv,json,os,secrets,shutil,tempfile,threading,time
from PySide6.QtCore import QObject,Signal,Slot,QThreadPool,QRunnable,QTimer,QUrl,QSettings,QStandardPaths
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFileDialog
from engine import Compressor,ExportSettings,IMAGE_EXTS,SUPPORTED,resource_dir
from medialite import BatchWorker,ImportWorker,STATUS
from media_preview import LoadPreview
from branding import VERSION,WHATSAPP_URL
from visuals import conservative_effects


class PreviewSignals(QObject):
    done=Signal(str,int,object,str)


class PreviewExport(QRunnable):
    def __init__(self,item,generation,settings,folder,key):
        super().__init__();self.item=item;self.generation=generation;self.settings=settings
        self.folder=folder;self.key=key;self.cancel=threading.Event();self.signals=PreviewSignals()
    def run(self):
        try:
            self.folder.mkdir(parents=True,exist_ok=True)
            result=Compressor(self.cancel,settings=self.settings).compress(self.item['source'],self.folder,'instagram')
            self.signals.done.emit(self.item['id'],self.generation,result,self.key)
        except Exception as error:
            self.signals.done.emit(self.item['id'],self.generation,None,str(error))


class DesktopController(QObject):
    message=Signal(str)
    closeReady=Signal()

    def __init__(self,window,server):
        super().__init__(window)
        self.window=window;self.server=server
        self.items=[];self.by_id={};self.selected=None;self.results={};self.worker=None;self.scan=None
        self.running=False;self.importing=False;self.close_after=False;self.pending=[]
        self.settings=ExportSettings();self.auto_output=True;self.custom_output=None;self.last_output=None
        self.preferences=QSettings('MaherBakran','MediaPress')
        self.theme=self.preferences.value('theme','light')
        if self.theme not in ('light','dark'):self.theme='light'
        self.effects=self.preferences.value('effects',not conservative_effects(),type=bool)
        self.cache=tempfile.TemporaryDirectory(prefix='mediapress-preview-',ignore_cleanup_errors=True)
        self.cache_root=Path(self.cache.name)
        self.pool=QThreadPool(self);self.pool.setMaxThreadCount(2)
        self.tasks={};self.thumb_counter=0;self.thumb_context={};self.preview_generation=0;self.preview_task=None
        self.job=None;self.last_progress=0.;self.disposed=False
        self.demos={}
        for kind,name in (('image','demo.jpg'),('video','demo.mp4')):
            self.demos[kind]=self._new_item(resource_dir()/'assets/ui'/name,'demo-'+kind,True)
            self.demos[kind]['url']=server.base+name

    def emit_event(self,kind,**data):
        if not self.disposed:self.message.emit(json.dumps({'type':kind,**data},ensure_ascii=False))

    def public_item(self,item):
        return {**{key:value for key,value in item.items() if key!='source'},'folder':str(item['source'].parent)}

    def _new_item(self,path,identifier=None,demo=False):
        path=Path(path).resolve()
        kind='image' if path.suffix.lower() in IMAGE_EXTS else 'video'
        return {'id':identifier or secrets.token_urlsafe(12),'source':path,'name':path.name,'size':path.stat().st_size,
                'kind':kind,'demo':demo,'url':self.server.register(path) if kind=='video' else '',
                'status':'idle','error':'','result':None,'preview':None,'poster':''}

    def snapshot(self):
        parents={str(item['source'].parent) for item in self.items}
        destination=str(self.custom_output or '') if not self.auto_output else ('بجانب كل ملف أصلي' if len(parents)!=1 else next(iter(parents)))
        return {'items':[self.public_item(i) for i in self.items],'selected':self.selected,
                'demos':{k:self.public_item(v) for k,v in self.demos.items()},'settings':asdict(self.settings),
                'theme':self.theme,'effects':self.effects,'running':self.running,'importing':self.importing,
                'autoOutput':self.auto_output,'destination':destination,'results':len(self.results),'job':self.job,'version':VERSION}

    @Slot(result=str)
    def getState(self):return json.dumps(self.snapshot(),ensure_ascii=False)

    @Slot(str)
    def action(self,raw):
        if self.disposed:return
        try:
            if len(raw)>30000:raise ValueError('طلب غير صالح')
            request=json.loads(raw);action=request.get('action')
            if action=='media':self.window.movie.handle(request);return
            if action=='contact':QDesktopServices.openUrl(QUrl(WHATSAPP_URL));return
            if action=='preference':
                if request.get('theme') in ('light','dark'):
                    self.theme=request['theme'];self.preferences.setValue('theme',self.theme)
                    self.window.set_theme(self.theme)
                if type(request.get('effects')) is bool:
                    self.effects=request['effects'];self.preferences.setValue('effects',self.effects)
                return
            if action=='stop':self.stop();return
            if action=='closeAfterStop':self.close_after=True;self.stop();return
            if action=='openFolder':self.open_folder(request.get('id'));return
            if action=='openFile':self.open_file(request.get('id'),request.get('output',False));return
            if action=='report':self.save_report();return
            if action=='select':
                item=self.by_id.get(request.get('id')) or self.demos.get(request.get('kind'))
                if item:
                    self.selected=None if item['demo'] else item['id']
                    self.request_thumbnail(item)
                return
            if self.running or self.importing:return
            if action in ('pickFiles','pickFolder'):
                self.pick(action=='pickFolder');return
            if action=='settings':
                self.settings=self.parse_settings(request['settings']);return
            if action=='preview':
                self.preview(request);return
            if action=='remove':
                item=self.by_id.get(request.get('id'))
                if item:
                    index=self.items.index(item);self.items.remove(item);self.by_id.pop(item['id']);self.results.pop(item['id'],None)
                    self.selected=self.items[min(index,len(self.items)-1)]['id'] if self.items else None
                    self.emit_event('state',state=self.snapshot())
                return
            if action=='clear':
                self.cancel_preview();self.items=[];self.by_id={};self.selected=None;self.results={}
                self.emit_event('state',state=self.snapshot());return
            if action=='destination':
                if request.get('automatic') is True:self.auto_output=True
                elif request.get('choose') is True:
                    folder=QFileDialog.getExistingDirectory(self.window,'مكان حفظ النتائج',str(self.custom_output or ''))
                    if folder:self.custom_output=Path(folder).resolve();self.auto_output=False
                self.emit_event('state',state=self.snapshot());return
            if action=='start':
                self.settings=self.parse_settings(request['settings']);self.start(request.get('kind','image'));return
        except (ValueError,TypeError,KeyError,OSError) as error:
            self.emit_event('notice',text=str(error))

    def parse_settings(self,values):
        settings=ExportSettings(**values);settings.validate();return settings

    def pick(self,folder=False):
        if self.running or self.importing:return
        if folder:
            value=QFileDialog.getExistingDirectory(self.window,'اختيار مجلد الصور والفيديوهات')
            paths=[Path(value)] if value else []
        else:
            extensions=' '.join('*'+ext for ext in sorted(SUPPORTED))
            values,_=QFileDialog.getOpenFileNames(self.window,'اختيار صور وفيديوهات','',f'ملفات الوسائط ({extensions});;كل الملفات (*)')
            paths=[Path(v) for v in values]
        self.add_paths(paths)

    def add_paths(self,paths):
        if self.running or self.importing or not paths:return
        self.importing=True;self.emit_event('state',state=self.snapshot())
        self.scan=ImportWorker(paths)
        self.scan.collected.connect(self._collected)
        self.scan.finished.connect(self._scan_finished)
        self.scan.start()

    def _collected(self,paths,ignored):
        self.pending=paths;self.import_ignored=ignored;self._import_chunk()

    def _import_chunk(self):
        known={str(i['source']).casefold() for i in self.items}
        added=[];batch,self.pending=self.pending[:75],self.pending[75:]
        for path in batch:
            if len(self.items)>=5000:break
            if str(path.resolve()).casefold() in known:continue
            try:item=self._new_item(path)
            except OSError:self.import_ignored+=1;continue
            self.items.append(item);self.by_id[item['id']]=item;known.add(str(item['source']).casefold());added.append(self.public_item(item))
        self.emit_event('added',items=added)
        if self.pending and len(self.items)<5000 and not self.scan.cancel.is_set():QTimer.singleShot(0,self._import_chunk)
        else:
            self.scan.wait();self.importing=False
            if self.selected is None and self.items:self.selected=self.items[0]['id']
            self.emit_event('state',state=self.snapshot())
            if self.import_ignored:self.emit_event('notice',text=f'تم تجاوز {self.import_ignored} ملف غير متاح.')
            if self.selected:self.request_thumbnail(self.by_id[self.selected])
            if self.close_after:self.closeReady.emit()

    def _scan_finished(self):
        if self.scan.cancel.is_set() and self.importing:
            self.pending=[];self.importing=False;self.emit_event('state',state=self.snapshot())
            if self.close_after:self.closeReady.emit()

    def request_thumbnail(self,item,output=False):
        field='resultThumb' if output else ('poster' if item['kind']=='video' else 'url')
        if item.get(field) or any(c[0]==item['id'] and c[1]==field for c in self.thumb_context.values()):return
        path=Path(item['result']['path']) if output and item.get('result') else item['source']
        self.thumb_counter+=1;token=self.thumb_counter
        task=LoadPreview(token,path);self.tasks[token]=task
        self.thumb_context[token]=(item['id'],field)
        task.signals.done.connect(self._thumbnail_ready)
        self.pool.start(task)

    def _thumbnail_ready(self,token,image,details):
        self.tasks.pop(token,None);context=self.thumb_context.pop(token,None)
        if self.disposed or not context:return
        identifier,field=context[:2];item=self.by_id.get(identifier) or next((i for i in self.demos.values() if i['id']==identifier),None)
        if not item:return
        if image is not None:
            path=self.cache_root/f'thumb-{token}.png';image.save(str(path),'PNG')
            url=self.server.register(path)
            if field=='resultThumb':
                item[field]=url
                if item.get('result'):item['result']['thumb']=url
            elif field=='previewThumb':
                if len(context)>2 and context[2]==self.preview_generation and item.get('preview'):item['preview']['url']=url
            else:item[field]=url
        else:item['previewError']=True
        self.emit_event('item',item=self.public_item(item))

    def cancel_preview(self):
        self.preview_generation+=1
        if self.preview_task:self.preview_task.cancel.set()

    def preview(self,request):
        item=self.by_id.get(request.get('id')) or self.demos.get(request.get('kind'))
        if not item or item['kind']!='image':return
        self.cancel_preview();generation=self.preview_generation
        settings=self.parse_settings(request['settings'])
        task=PreviewExport(item,generation,settings,self.cache_root/f'preview-{generation}',str(request.get('key',''))[:1000])
        self.preview_task=task;self.tasks['preview-'+str(generation)]=task
        task.signals.done.connect(self._preview_ready);self.pool.start(task)

    def _preview_ready(self,identifier,generation,result,key):
        self.tasks.pop('preview-'+str(generation),None)
        if generation!=self.preview_generation or self.disposed:return
        item=self.by_id.get(identifier) or next((i for i in self.demos.values() if i['id']==identifier),None)
        if not item:return
        if result and result.output:
            item['preview']={'size':result.after,'url':'','key':key}
            self.thumb_counter+=1;token=self.thumb_counter;task=LoadPreview(token,Path(result.output));self.tasks[token]=task
            self.thumb_context[token]=(item['id'],'previewThumb',generation)
            task.signals.done.connect(self._thumbnail_ready);self.pool.start(task)
        else:item['previewError']=True
        self.emit_event('item',item=self.public_item(item))

    def start(self,kind='image'):
        self.cancel_preview()
        self.batch=self.items.copy()
        destination=None if self.auto_output else self.custom_output
        if not self.batch:
            item=self.demos.get(kind,self.demos['image']);self.batch=[item]
            destination=destination or Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))/'MediaPress'/'Examples'
        try:
            destinations={destination} if destination is not None else {i['source'].parent for i in self.batch}
            for folder in destinations:
                folder.mkdir(parents=True,exist_ok=True)
                with tempfile.TemporaryFile(dir=folder):pass
        except OSError as error:
            self.emit_event('notice',text='مجلد الحفظ غير متاح. اختر مجلداً آخر من «الحفظ».');return
        self.results={};self.running=True
        for item in self.batch:item.update(status='idle',error='',result=None)
        self.job={'running':True,'percent':0,'finished':0,'total':len(self.batch),'name':'','errors':[],'outputs':0,'stopped':False}
        self.emit_event('state',state=self.snapshot());self.emit_event('started')
        self.worker=BatchWorker([i['source'] for i in self.batch],destination,'instagram',self.settings)
        self.worker.started_file.connect(self._started)
        self.worker.progress_file.connect(self._progress)
        self.worker.result_file.connect(self._result)
        self.worker.finished.connect(self._finished)
        self.worker.start()

    def _started(self,row,name):
        self.batch[row]['status']='running';self.job['name']=name
        self.emit_event('item',item=self.public_item(self.batch[row]));self.emit_event('progress',job=self.job)

    def _progress(self,row,fraction):
        now=time.monotonic()
        if now-self.last_progress<.08 and fraction<1:return
        self.last_progress=now;self.job['percent']=min(99.9,100*(row+fraction)/len(self.batch))
        self.emit_event('progress',job=self.job)

    def _result(self,row,result):
        item=self.batch[row];self.results[item['id']]=result
        item['status']=result.status;item['error']=result.message if result.status in ('error','skipped','cancelled') else ''
        if result.output:
            self.last_output=Path(result.output).parent
            item.pop('resultThumb',None)
            item['result']={'size':result.after,'url':self.server.register(result.output) if item['kind']=='video' else '','path':result.output,'key':'export','settings':asdict(self.settings),'status':result.status}
            if item['kind']=='image':self.request_thumbnail(item,output=True)
            self.job['outputs']+=1
        elif result.status in ('error','skipped'):self.job['errors'].append(item['name']+' — '+result.message)
        self.job['finished']=row+1;self.job['percent']=min(99.9,100*(row+1)/len(self.batch))
        self.emit_event('item',item=self.public_item(item));self.emit_event('progress',job=self.job)

    def _finished(self):
        self.running=False;stopped=self.worker.cancel.is_set()
        self.job['running']=False;self.job['stopped']=stopped
        if not stopped:self.job['percent']=100
        for item in self.batch:
            if item['status'] in ('running','idle') and stopped:item['status']='cancelled'
        self.emit_event('state',state=self.snapshot())
        if self.close_after:self.closeReady.emit()

    def stop(self):
        if self.importing and self.scan:self.scan.cancel.set()
        elif self.running and self.worker:self.worker.cancel.set();self.emit_event('notice',text='جارٍ الإيقاف؛ النتائج المكتملة محفوظة.')
        elif self.close_after:self.closeReady.emit()

    def find_item(self,identifier):
        return self.by_id.get(identifier) or next((i for i in self.demos.values() if i['id']==identifier),None)

    def open_folder(self,identifier=None):
        item=self.find_item(identifier)
        folder=Path(item['result']['path']).parent if item and item.get('result') else self.last_output
        if folder and folder.is_dir():QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def open_file(self,identifier,output=False):
        item=self.find_item(identifier)
        if not item:return
        path=Path(item['result']['path']) if output and item.get('result') else item['source']
        if path.is_file():QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def save_report(self):
        if self.running or not self.results:return
        path,_=QFileDialog.getSaveFileName(self.window,'حفظ التقرير',str((self.last_output or Path.cwd())/'MediaPress-report.csv'),'CSV (*.csv)')
        if not path:return
        def safe(value):
            value=str(value);return "'"+value if value.startswith(('=','+','-','@','\t','\r')) else value
        try:
            with open(path,'w',encoding='utf-8-sig',newline='') as output:
                writer=csv.writer(output);writer.writerow(['Source','Status','Before bytes','After bytes','Output','Details'])
                for result in self.results.values():writer.writerow([safe(result.source),STATUS[result.status],result.before,result.after,safe(result.output),safe(result.message)])
            self.emit_event('notice',text='تم حفظ التقرير.')
        except OSError:self.emit_event('notice',text='تعذّر حفظ التقرير. اختر مجلداً آخر.')

    def shutdown(self):
        self.disposed=True;self.cancel_preview()
        for task in self.tasks.values():
            if hasattr(task,'cancelled'):task.cancelled.set()
            elif hasattr(task,'cancel'):task.cancel.set()
        self.pool.clear();self.pool.waitForDone()
        if self.scan:self.scan.cancel.set();self.scan.wait()
        if self.worker:self.worker.cancel.set();self.worker.wait()
        self.cache.cleanup()
