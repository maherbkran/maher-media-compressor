'use strict';
const $=id=>document.getElementById(id);
const icon=name=>`<svg class="ic" aria-hidden="true" focusable="false" viewBox="0 0 256 256"><use href="#ph-${name}"></use></svg>`;
const defaults={image:{quality:85,cap:0,width:1080,height:1920},video:{quality:80,cap:0,width:1920,height:1920}};
const opts=structuredClone(defaults);
let state=null,native=null,queue=[],active=null,demos={},chosenKind='image',mode='compare',job=null,previewTimer=0,toastTimer=0,previewToken=0;
const itemMap=new Map();
let advancedDraft=null,advancedKind='image';
function updateDraftPresets(){for(const button of document.querySelectorAll('[data-cap]'))button.setAttribute('aria-pressed',Boolean(advancedDraft&&advancedDraft.cap===Number(button.dataset.cap)));}
function send(action,args={}){if(native)native.action(JSON.stringify({action,...args}));}
function setHidden(id,hidden){$(id).hidden=hidden;}
function notify(text){$('tip').textContent=text;setHidden('tip',false);clearTimeout(toastTimer);toastTimer=setTimeout(()=>setHidden('tip',true),4300);$('nativeStatus').textContent=text;}
function busy(){return Boolean(state&&(state.running||state.importing));}
function formatBytes(bytes){if(!Number.isFinite(bytes))return '—';const units=['B','KB','MB','GB','TB'];let i=0;while(bytes>=1024&&i<4){bytes/=1024;i++;}return (bytes>=100?Math.round(bytes):Number(bytes.toFixed(bytes<10?2:1)))+' '+units[i];}
function settings(){return {image_quality:opts.image.quality,image_max_mb:opts.image.cap,image_max_width:opts.image.width,image_max_height:opts.image.height,video_quality:opts.video.quality,video_max_mb:opts.video.cap,video_max_width:opts.video.width,video_max_height:opts.video.height};}
function keyFor(kind){return JSON.stringify(opts[kind]);}
function displayItem(){return active||demos[chosenKind];}
function resultMatches(item){const r=item?.result;if(!r)return false;if(!r.settings)return true;const cfg=opts[item.kind],p=item.kind+'_';return cfg.quality===r.settings[p+'quality']&&cfg.cap===r.settings[p+'max_mb']&&cfg.width===r.settings[p+'max_width']&&cfg.height===r.settings[p+'max_height'];}
function previewResult(item){return resultMatches(item)?item.result:(item?.preview?.key===keyFor(item.kind)?item.preview:null);}
function showDialog(id){const d=$(id);if(!d.open){d.showModal();d.scrollTop=0;}requestAnimationFrame(syncNativeVideo);}
function closeDialog(id){if($(id).open)$(id).close();requestAnimationFrame(syncNativeVideo);}
function showReturnControl(){if($('runDialog').open)return;pauseGames();if(job){setHidden('resumeJob',false);$('resumeJob').focus({preventScroll:true});}}
function setTheme(theme,save=true){document.documentElement.dataset.theme=theme;const dark=theme==='dark';$('themeIcon').innerHTML=icon(dark?'sun':'moon-stars');$('themeLabel').textContent=dark?'الوضع الفاتح':'الوضع الداكن';$('themeShort').textContent=dark?'فاتح':'داكن';$('themeBtn').setAttribute('aria-label',dark?'التبديل إلى الوضع الفاتح':'التبديل إلى الوضع الداكن');if(save)send('preference',{theme});}
function showSettings(){const cfg=opts[chosenKind],image=chosenKind==='image';$('kindImage').setAttribute('aria-pressed',image);$('kindVideo').setAttribute('aria-pressed',!image);
 const fields={A:{label:image?'جودة الصورة':'جودة الفيديو',min:1,max:100,step:1,val:cfg.quality,unit:'%',lo:'1%',hi:'100%'},B:{label:'الحجم الأقصى',min:0,max:Math.max(image?10:100,cfg.cap),step:.01,val:cfg.cap,unit:'MB',lo:'0 · بدون حد',hi:Math.max(image?10:100,cfg.cap)+' MB'}};
 for(const suffix of ['A','B']){const f=fields[suffix],r=$('range'+suffix),n=$('num'+suffix);$('label'+suffix).textContent=f.label;$('unit'+suffix).textContent=f.unit;$('min'+suffix).textContent=f.lo;$('max'+suffix).textContent=f.hi;
  r.min=f.min;r.max=f.max;r.step=f.step;r.value=f.val;n.min=f.min;n.max=suffix==='B'?1000:f.max;n.step=f.step;n.value=f.val;n.style.width=Math.max(3.1,String(n.value).length+.8)+'ch';n.setAttribute('aria-label','قيمة '+f.label);r.setAttribute('aria-valuetext',suffix==='B'&&f.val===0?'بدون حد حجم':f.val+' '+f.unit);
  const p=(f.val-f.min)/(f.max-f.min);$('rail'+suffix).style.setProperty('--v',100*p+'%');$('rail'+suffix).style.setProperty('--shift',(.5-p)*32+'px');
 }
}
function changeSetting(suffix,source){if(busy())return;const node=$(source+suffix);if(!node.value.trim()){showSettings();return;}let value=Number(node.value);if(!Number.isFinite(value)){showSettings();return;}
 value=Math.max(suffix==='A'?1:0,Math.min(suffix==='A'?100:1000,value));if(suffix==='B'&&value>0&&value<.01)value=.01;
 opts[chosenKind][suffix==='A'?'quality':'cap']=suffix==='A'?Math.round(value):Math.round(value*100)/100;
 showSettings();send('settings',{settings:settings()});refreshPreview(false);
}
function chooseKind(kind){if(busy())return;chosenKind=kind;active=queue.find(item=>item.id===active?.id&&item.kind===kind)||queue.find(item=>item.kind===kind)||null;mode=kind==='image'?'compare':'original';showSettings();renderQueue();selectNative();refreshPreview();}
function selectNative(){const item=displayItem();if(item)send('select',{id:item.id,kind:item.demo?item.kind:undefined});}
function selectItem(item){if(!item)return;active=item;chosenKind=item.kind;mode=item.kind==='image'?'compare':'original';showSettings();renderQueue();selectNative();refreshPreview();}
function updateSplit(){const value=$('compareRange').value;$('stage').style.setProperty('--split',value+'%');$('compareRange').setAttribute('aria-valuetext',value+' بالمئة من عرض الصورة بعد الضغط');}
function drawStage(){const item=displayItem();if(!item)return;const image=item.kind==='image',candidate=previewResult(item),result=candidate&&(candidate.url||candidate.thumb)?candidate:null;const stage=$('stage');stage.dataset.kind=item.kind;stage.dataset.demo=String(Boolean(item.demo));
 setHidden('demoFlag',!item.demo);$('originalBytes').textContent=formatBytes(item.size);$('resultBytes').textContent=formatBytes(result?.size);
 const saving=result?Math.round((1-result.size/item.size)*100):null;$('savedPct').textContent=saving===null?'—':Math.abs(saving)+'%';const saved=$('savedPct').closest('.readout');saved.classList.toggle('increase',saving<0);saved.querySelector('span').textContent=saving<0?'زيادة الحجم':'التوفير';saved.querySelector('.ic').style.transform=saving<0?'rotate(180deg)':'';
 const view=mode==='compare'&&(!image||!result)?'original':mode==='result'&&!result?'original':mode;stage.dataset.view=view;
 for(const [id,m] of [['modeCompare','compare'],['modeOriginal','original'],['modeResult','result']]){$(id).setAttribute('aria-pressed',view===m);$(id).disabled=(m==='compare'&&!image)||(m!=='original'&&!result);}
 setHidden('imageStack',!image);setHidden('previewVideo',true);setHidden('nativeVideoControls',image);setHidden('compareControl',!image||view!=='compare');setHidden('compareTags',!image||view!=='compare');setHidden('stageNote',true);setHidden('nativeOpenOriginal',true);
 $('resultLayer').hidden=!image;
 if(image){const video=$('previewVideo');if(video.hasAttribute('src')){video.pause();video.removeAttribute('src');video.load();}
  if(item.url){if($('origImg').getAttribute('src')!==item.url)$('origImg').src=item.url;}else{$('origImg').removeAttribute('src');$('stageNote').textContent=item.previewError?'تعذّرت المعاينة. يمكنك تجربة الضغط.':'جارٍ تجهيز المعاينة…';setHidden('stageNote',false);}
  $('origImg').alt=item.demo?'كثبان رملية، مثال تجريبي':item.name;
  if(result){const url=result.thumb||result.url;if(url&&$('outImg').getAttribute('src')!==url)$('outImg').src=url;}else $('outImg').removeAttribute('src');
 }else{setHidden('imageStack',false);$('resultLayer').hidden=true;
  const poster=item.poster||(item.demo?demos.image.url:'');if(poster)$('origImg').src=poster;else $('origImg').removeAttribute('src');
  stage.dataset.view='original';

 }
 requestAnimationFrame(syncNativeVideo);
}
function refreshPreview(immediate=true){clearTimeout(previewTimer);drawStage();const item=displayItem();if(!item||item.kind!=='image'||resultMatches(item)||item.preview?.key===keyFor('image')||busy())return;
 previewTimer=setTimeout(()=>send('preview',{id:item.id,kind:item.demo?'image':undefined,settings:settings(),key:keyFor('image')}),immediate?0:320);
}
let virtualStart=-1;
function renderQueue(force=true){const list=$('fileList'),oldScroll=list.scrollTop;const start=queue.length>200?Math.max(0,Math.floor(oldScroll/54)-3):0,end=queue.length>200?Math.min(queue.length,start+18):queue.length;
 if(!force&&virtualStart===start)return;virtualStart=start;list.replaceChildren();$('queueCount').textContent=queue.length;list.closest('.queue').classList.toggle('has-files',queue.length>0);
 $('removeBtn').disabled=busy()||!active;$('clearBtn').disabled=busy()||!queue.length;$('reportBtn').disabled=busy()||!(state?.results);$('destinationBtn').disabled=busy();
 if(start){const spacer=document.createElement('div');spacer.style.height=start*54+'px';spacer.setAttribute('aria-hidden','true');list.append(spacer);}
 for(const item of queue.slice(start,end)){const row=document.createElement('div');row.className='file-row';const btn=document.createElement('button');btn.className='file-pick';btn.dataset.item=item.id;btn.setAttribute('aria-pressed',item.id===active?.id);btn.disabled=busy();btn.onclick=()=>selectItem(item);
  const thumb=document.createElement('span');thumb.className='file-thumb';if(item.kind==='image'&&item.url){const img=document.createElement('img');img.src=item.url;img.alt='';img.loading='lazy';thumb.append(img);}else thumb.innerHTML=icon(item.kind==='image'?'image':'film-strip');
  const info=document.createElement('span');info.className='file-info';const name=document.createElement('bdi');name.dir='auto';name.textContent=item.name;name.title=(item.folder?item.folder+' / ':'')+item.name;const small=document.createElement('small');small.dir='ltr';small.textContent=formatBytes(item.size);info.append(name,small);
  const status=document.createElement('span');status.className='file-state'+(item.error?' error':'');status.textContent=({idle:'جاهز',running:'جارٍ الضغط…',compressed:'تم الضغط',converted:'تم التحويل',error:'تعذّرت المعالجة',skipped:'تم التجاوز',cancelled:'متوقف'})[item.status]||'جاهز';if(item.result&&!resultMatches(item))status.textContent='تغيّرت الإعدادات';status.title=item.error||'';
  btn.append(thumb,info,status);row.append(btn);
  if(item.result){const open=document.createElement('button');open.className='btn mini';open.innerHTML=icon('folder-open')+'مجلده';open.setAttribute('aria-label','فتح مجلد نتيجة '+item.name);open.onclick=()=>send('openFolder',{id:item.id});row.append(open);}
  list.append(row);
 }
 if(end<queue.length){const spacer=document.createElement('div');spacer.style.height=(queue.length-end)*54+'px';spacer.setAttribute('aria-hidden','true');list.append(spacer);}
 list.scrollTop=oldScroll;
}
function applyState(next){const selected=active?.id;state=next;queue=next.items;itemMap.clear();queue.forEach(i=>itemMap.set(i.id,i));demos=next.demos;
 active=itemMap.get(next.selected)||itemMap.get(selected)||null;if(active)chosenKind=active.kind;
 for(const kind of ['image','video']){const p=kind+'_';opts[kind]={quality:next.settings[p+'quality'],cap:next.settings[p+'max_mb'],width:next.settings[p+'max_width'],height:next.settings[p+'max_height']};}
 job=next.job;setTheme(next.theme,false);document.documentElement.dataset.effects=next.effects?'on':'off';$('fxCheck').checked=!next.effects;
 $('nativeAutoOutput').checked=next.autoOutput;$('nativeDestination').textContent=next.destination||'بجانب كل أصل تلقائياً';$('destinationBtn').title=next.destination;
 for(const id of ['addBtn','dropBtn','kindImage','kindVideo','rangeA','rangeB','numA','numB','advancedBtn','startBtn'])$(id).disabled=busy();
 $('dropBtn').querySelector('strong').textContent=next.importing?'جارٍ إضافة الملفات…':'اسحب ملفاتك إلى هنا';
 $('startBtn').querySelector('span').textContent=next.running?'جارٍ الضغط…':'ابدأ الضغط';showSettings();renderQueue();drawStage();updateJobUI();
 if(!busy())refreshPreview();document.body.classList.remove('native-loading');window.nativeReady=true;
}
function receive(raw){const message=JSON.parse(raw);if(message.type==='state')applyState(message.state);
 else if(message.type==='added'){for(const item of message.items){if(!itemMap.has(item.id)){queue.push(item);itemMap.set(item.id,item);}}renderQueue();}
 else if(message.type==='item'){const item=message.item,old=itemMap.get(item.id);if(old){Object.assign(old,item);if(active?.id===item.id)active=old;}else if(item.demo)demos[item.kind]=item;
  renderQueue();drawStage();}
 else if(message.type==='media'){mediaState=message;updateNativeControls();}
 else if(message.type==='progress'){job=message.job;updateJobUI();}
 else if(message.type==='started'){openJob();chooseGame(null);}
 else if(message.type==='notice')notify(message.text);
}
function updateJobUI(){if(!job)return;const percent=Math.min(100,Math.max(0,Math.floor(job.percent)));$('jobPct').textContent=percent+'%';$('jobBar').value=percent;$('resumePct').textContent=percent+'%';$('resumeLabel').textContent=job.running?'تقدّم الضغط والألعاب':'النتائج والألعاب';
 $('runTitle').textContent=job.running?'تقدّم الضغط':job.stopped?'تم الإيقاف':job.errors.length?'اكتملت المعالجة':'اكتمل الضغط';$('jobCaption').textContent=job.running?(job.name||'جارٍ تحضير الملفات…'):job.outputs?'النتائج محفوظة وجاهزة للمعاينة':'لم تُحفظ نتائج لهذه الدفعة';$('jobCaption').dir=job.running&&job.name?'auto':'rtl';
 $('jobCount').textContent=`اكتمل ${job.finished} من ${job.total}`;setHidden('saveJob',job.running||!job.outputs);$('saveJob').querySelector('span').textContent='فتح مجلد النتائج';setHidden('stopJob',!job.running);setHidden('jobErrors',!job.errors.length);$('jobErrors').textContent=job.errors.join(' / ');
 if(!$('runDialog').open)setHidden('resumeJob',false);
}
function openJob(){if(!job)return;setHidden('resumeJob',true);updateJobUI();showDialog('runDialog');resumeGames();}
function previewZoom(){if($('zoomDialog').open){closeDialog('zoomDialog');return;}$('zoomDialog').append($('previewPanel'));showDialog('zoomDialog');$('expandBtn').innerHTML=icon('arrows-in')+'<span>تصغير</span>';}
function openCloseDialog(){pauseGames();showDialog('nativeCloseDialog');}
function initializeDesktop(){
 document.body.classList.add('native-loading');
 const openPick=()=>{if(!busy())showDialog('pickDialog');};$('addBtn').onclick=openPick;$('dropBtn').onclick=openPick;
 $('pickFiles').onclick=()=>{closeDialog('pickDialog');send('pickFiles');};$('pickFolder').onclick=()=>{closeDialog('pickDialog');send('pickFolder');};
 for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>closeDialog(button.dataset.close);
 $('authorLink').onclick=event=>{event.preventDefault();showDialog('aboutDialog');};$('helpBtn').onclick=()=>showDialog('helpDialog');
 for(const link of document.querySelectorAll('a[href="https://wa.me/971543386217"]'))link.onclick=event=>{event.preventDefault();send('contact');};
 $('themeBtn').onclick=()=>setTheme(document.documentElement.dataset.theme==='dark'?'light':'dark');$('fxCheck').onchange=()=>{document.documentElement.dataset.effects=$('fxCheck').checked?'off':'on';send('preference',{effects:!$('fxCheck').checked});};
 $('kindImage').onclick=()=>chooseKind('image');$('kindVideo').onclick=()=>chooseKind('video');
 for(const suffix of ['A','B']){ $('range'+suffix).oninput=()=>changeSetting(suffix,'range');$('num'+suffix).onchange=()=>changeSetting(suffix,'num');}
 $('advancedBtn').onclick=()=>{advancedKind=chosenKind;advancedDraft=structuredClone(opts[chosenKind]);updateDraftPresets();const cfg=advancedDraft;$('nativeWidth').value=cfg.width;$('nativeHeight').value=cfg.height;$('nativeSettingsTitle').textContent=chosenKind==='image'?'خيارات الصور':'خيارات الفيديو';$('nativeFormatNote').textContent=chosenKind==='image'?'JPEG دائماً · الشفافية بيضاء · أول إطار للصور المتحركة.':'MP4 دائماً · لا حد لحجم الإدخال · الكادر كاملاً.';showDialog('nativeSettingsDialog');};
 $('nativeApply').onclick=()=>{const width=Number($('nativeWidth').value),height=Number($('nativeHeight').value);if(!Number.isInteger(width)||!Number.isInteger(height)||Math.min(width,height)<16||Math.max(width,height)>16384){notify('الأبعاد من 16 إلى 16384 بكسل.');return;}Object.assign(opts[advancedKind],advancedDraft,{width,height});showSettings();send('settings',{settings:settings()});closeDialog('nativeSettingsDialog');refreshPreview(false);};
 $('nativeReset').onclick=()=>{advancedDraft=structuredClone(defaults[advancedKind]);$('nativeWidth').value=advancedDraft.width;$('nativeHeight').value=advancedDraft.height;updateDraftPresets();};
 for(const button of document.querySelectorAll('[data-cap]'))button.onclick=()=>{if(advancedDraft)advancedDraft.cap=Number(button.dataset.cap);updateDraftPresets();};
 $('destinationBtn').onclick=()=>showDialog('destinationDialog');$('nativeAutoOutput').onchange=()=>send('destination',$('nativeAutoOutput').checked?{automatic:true}:{choose:true});$('nativeChooseDestination').onclick=()=>send('destination',{choose:true});$('reportBtn').onclick=()=>send('report');
 $('removeBtn').onclick=()=>{if(active)send('remove',{id:active.id});};$('clearBtn').onclick=()=>showDialog('clearDialog');$('confirmClear').onclick=()=>{closeDialog('clearDialog');send('clear');};
 for(const [id,m] of [['modeCompare','compare'],['modeOriginal','original'],['modeResult','result']])$(id).onclick=()=>{mode=m;drawStage();};$('compareRange').oninput=updateSplit;$('expandBtn').onclick=previewZoom;
 $('zoomDialog').addEventListener('close',()=>{$('previewSlot').append($('previewPanel'));$('expandBtn').innerHTML=icon('arrows-out')+'<span>توسيع</span>';$('expandBtn').focus();});
 $('previewVideo').onerror=drawStage;$('nativeOpenOriginal').onclick=()=>{const item=displayItem();if(item)send('openFile',{id:item.id});};
 $('startBtn').onclick=()=>{if(!busy()){if(document.activeElement===$('numA'))changeSetting('A','num');if(document.activeElement===$('numB'))changeSetting('B','num');}if(!busy())send('start',{settings:settings(),kind:chosenKind});else openJob();};$('stopJob').onclick=()=>send('stop');$('hideRun').onclick=()=>closeDialog('runDialog');$('resumeJob').onclick=openJob;$('saveJob').onclick=()=>send('openFolder',{id:active?.id});
 $('runDialog').addEventListener('close',showReturnControl);$('nativeConfirmClose').onclick=()=>{closeDialog('nativeCloseDialog');send('closeAfterStop');};
 $('fileList').addEventListener('scroll',()=>renderQueue(false),{passive:true});
 document.addEventListener('visibilitychange',()=>{if(document.hidden)pauseGames();else if($('runDialog').open)resumeGames();});window.addEventListener('blur',()=>pauseGames());
 document.addEventListener('keydown',event=>{if(event.ctrlKey&&event.key.toLowerCase()==='o'){event.preventDefault();openPick();}else if(event.ctrlKey&&event.key==='Enter'){event.preventDefault();if($('nativeSettingsDialog').open)$('nativeApply').click();else if(!document.querySelector('dialog[open]'))$('startBtn').click();}else if(event.key==='Delete'&&event.target.closest('.file-list')){event.preventDefault();$('removeBtn').click();}});
 bindGames();bindNativeControls();updateSplit();
 new QWebChannel(qt.webChannelTransport,channel=>{native=channel.objects.desktop;native.getState(raw=>{applyState(JSON.parse(raw));selectNative();});});
}

let mediaState={position:0,duration:0,playing:false,muted:false,error:''},seeking=false,lastMediaGeometry='';
function syncNativeVideo(){const item=displayItem();const dialog=[...document.querySelectorAll('dialog[open]')].some(d=>d.id!=='zoomDialog');
 const visible=item?.kind==='video'&&!dialog&&!document.hidden;const rect=$('stage').getBoundingClientRect();const output=mode==='result'&&Boolean(previewResult(item));
 const value={visible,id:item?.id,output,rect:{x:Math.round(rect.x+1),y:Math.round(rect.y+1),width:Math.round(rect.width-2),height:Math.round(rect.height-43)}};
 const encoded=JSON.stringify(value);if(encoded!==lastMediaGeometry){lastMediaGeometry=encoded;send('media',{command:'geometry',...value});}
}
function updateNativeControls(){const value=mediaState;$('nativePlay').innerHTML=icon(value.playing?'pause':'play')+'<span>'+(value.playing?'إيقاف مؤقت':'تشغيل')+'</span>';
 $('nativeMute').innerHTML=icon('music-note');$('nativeMute').setAttribute('aria-pressed',value.muted);$('nativeMute').title=value.muted?'تشغيل الصوت':'كتم الصوت';
 const seek=$('nativeSeek');seek.max=value.duration||1;if(!seeking)seek.value=value.position;const percent=value.duration?100*value.position/value.duration:0;$('nativeSeekRail').style.setProperty('--v',percent+'%');
 const stamp=ms=>{const sec=Math.floor(ms/1000);return Math.floor(sec/60).toString().padStart(2,'0')+':'+(sec%60).toString().padStart(2,'0');};$('nativeTime').textContent=stamp(value.position)+' / '+stamp(value.duration);
 if(value.error&&displayItem()?.kind==='video'){$('stageNote').textContent=value.error;setHidden('stageNote',false);setHidden('nativeOpenOriginal',false);}
}
function bindNativeControls(){
 $('nativePlay').onclick=()=>{syncNativeVideo();send('media',{command:'play'});};$('nativeMute').onclick=()=>send('media',{command:'mute'});
 $('nativeSeek').onpointerdown=()=>seeking=true;$('nativeSeek').onchange=()=>{seeking=false;send('media',{command:'seek',position:Number($('nativeSeek').value)});};
 new ResizeObserver(()=>requestAnimationFrame(syncNativeVideo)).observe($('stage'));
 window.addEventListener('scroll',()=>requestAnimationFrame(syncNativeVideo),{passive:true});window.addEventListener('resize',()=>requestAnimationFrame(syncNativeVideo));
 for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('close',()=>requestAnimationFrame(syncNativeVideo));
}
