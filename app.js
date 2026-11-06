const state={records:[],folders:[],editing:null,playing:null,lastProgress:null,lastProgressSave:0,loadSequence:0,progressQueue:Promise.resolve(),closingPlayer:false};
const $=selector=>document.querySelector(selector);
const list=$('#list'),search=$('#search'),filter=$('#filter'),folderFilter=$('#folderFilter'),editor=$('#editor');
const themeToggle=$('#themeToggle');
const playerDialog=$('#playerDialog'),videoPlayer=$('#videoPlayer');

function esc(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function formatBytes(bytes){if(!bytes)return '0 B';const units=['B','KB','MB','GB'];const i=Math.min(Math.floor(Math.log(bytes)/Math.log(1024)),3);return `${(bytes/1024**i).toFixed(i>1?2:0)} ${units[i]}`;}
function formatWatched(value){if(!value)return '';const date=new Date(value);return Number.isNaN(date.getTime())?'':date.toLocaleString('it-IT',{dateStyle:'short',timeStyle:'short'});}
function formatTime(value){const seconds=Math.max(0,Math.floor(Number(value)||0)),hours=Math.floor(seconds/3600),minutes=Math.floor((seconds%3600)/60),rest=seconds%60;return hours?`${hours}:${String(minutes).padStart(2,'0')}:${String(rest).padStart(2,'0')}`:`${minutes}:${String(rest).padStart(2,'0')}`;}
function standardName(record){if(record.is_special||record.is_movie)return record.current_name;const number=String(record.number).padStart(2,'0');return `MeitanteiConan_Ep_${number}_SUB_ITA${record.extension}`;}
function hasTitleOverride(record){return Object.values(record.title_overrides||{}).some(Boolean);}
function displayNumber(record){return String(record.display_number||record.number).replace(/^FILM\s*/i,'');}

async function load(options={}){
  const silent=Boolean(options.silent), sequence=++state.loadSequence;
  if(!silent){$('#error').classList.add('hidden');list.setAttribute('aria-busy','true');}
  try{
    const response=await fetch('/api/episodes',{cache:'no-store'});const data=await response.json();
    if(!response.ok)throw new Error(data.error||'Impossibile leggere le cartelle');
    if(sequence!==state.loadSequence||(silent&&(state.editing||state.playing)))return;
    state.records=data.records;state.folders=data.folders;state.lastProgress=data.last_progress||null;
    $('#folders').innerHTML=data.folders.length?data.folders.map(f=>`<div class="folder-item"><div class="folder-symbol"><svg aria-hidden="true"><use href="#i-folder"/></svg></div><div class="folder-info"><strong>${esc(f.label||f.key)} · ${f.kind==='movies'?'Film':'Episodi'} · ${esc(f.count)} video</strong><span>${esc(f.path)}</span>${f.error?`<em>${esc(f.error)}</em>`:''}</div><button class="folder-remove" type="button" data-remove-folder="${esc(f.key)}" aria-label="Rimuovi raccolta ${esc(f.label||f.key)}" title="Rimuovi raccolta">×</button></div>`).join(''):'<div class="folder-empty">Nessuna raccolta aggiunta. Aggiungi una cartella per iniziare.</div>';
    const selectedFolder=folderFilter.value;folderFilter.innerHTML='<option value="all">Tutte le raccolte</option>'+data.folders.map(f=>`<option value="${esc(f.key)}">${esc(f.label||f.key)} · ${esc(f.count)} video</option>`).join('');if([...folderFilter.options].some(o=>o.value===selectedFolder))folderFilter.value=selectedFolder;
    $('#fileCount').textContent=data.counts.files;$('#mp4Count').textContent=data.counts.mp4;$('#movCount').textContent=data.counts.mov;$('#watchedCount').textContent=data.counts.watched;renderContinue();render();
    if(data.unrecognized.length){const examples=data.unrecognized.slice(0,5).map(x=>`[${x.folder_key}] ${x.name}`).join(', ');showError(`${data.unrecognized.length} file non riconosciuti: ${examples}${data.unrecognized.length>5?'…':''}`);}else $('#error').classList.add('hidden');
  }catch(error){if(sequence===state.loadSequence){showError(`Impossibile aggiornare la libreria: ${error.message}`);if(!state.records.length)list.innerHTML='<div class="empty"><strong>Archivio non disponibile</strong>Controlla che il server sia in esecuzione e riprova.</div>';}}
  finally{if(sequence===state.loadSequence)list.setAttribute('aria-busy','false');}
}

function visibleRecords(){
  const q=search.value.trim().toLocaleLowerCase(),f=filter.value,folder=folderFilter.value;
  return state.records.filter(r=>{
    const hay=[r.number,r.display_number,r.num_int,r.current_name,r.manual_title,r.name_ita,r.name_eng,r.name_jap,r.title_card_observed,r.folder_key,r.folder_label].join(' ').toLocaleLowerCase();
    const type=f==='all'||(f==='anime_orig'&&r.anime_orig)||(f==='watched'&&r.watched)||(f==='unwatched'&&!r.watched)||(f==='custom'&&r.current_name!==standardName(r))||(f==='plain'&&r.current_name===standardName(r))||(f==='mov'&&r.extension==='.mov');
    return type&&(folder==='all'||r.folder_key===folder)&&hay.includes(q);
  });
}

function render(){
  const records=visibleRecords();$('#visibleCount').textContent=records.length;
  if(!records.length){list.innerHTML=state.records.length?'<div class="empty"><strong>Nessun risultato</strong>Prova a modificare la ricerca o i filtri.</div>':'<div class="empty"><strong>La tua prossima storia inizia qui</strong>Aggiungi una cartella di episodi o film per riempire la libreria.</div>';return;}
  list.innerHTML=records.map(r=>`<article class="episode" data-key="${esc(r.folder_key)}:${esc(r.number)}">
    <div class="number"><small>${r.is_movie?'FILM':'EPISODIO'}</small>${esc(displayNumber(r))}</div>
    <div class="episode-content"><div class="titles"><strong>${esc(r.manual_title||r.name_ita||r.title_card_observed||(r.is_movie?r.current_name:'Titolo italiano non disponibile'))}</strong><span>${esc(r.manual_title&&(r.name_ita||r.title_card_observed)?`Titolo di riferimento: ${r.name_ita||r.title_card_observed}`:(r.name_eng||r.name_jap||''))}</span></div><div class="file-name">${esc(r.current_name)}</div><div class="badges"><span class="badge folder-badge">${esc(r.season_folder||r.folder_label)}</span><span class="badge">${esc(r.extension.slice(1).toUpperCase())} · ${formatBytes(r.size)}</span>${r.playback?.position&&!r.playback?.completed?`<span class="badge progress">IN CORSO · ${formatTime(r.playback.position)}</span>`:''}${r.is_special?'<span class="badge manual">SPECIALE CANONICO · INT 1134</span>':''}${r.watched?`<span class="badge watched">✓ VISTO ${esc(formatWatched(r.watched_at))}</span>`:''}${r.manual_title?'<span class="badge manual">TITOLO PERSONALE</span>':''}${hasTitleOverride(r)?'<span class="badge manual">TITOLI MODIFICATI</span>':''}${r.anime_orig?'<span class="badge filler">ANIME ORIG</span>':''}</div></div>
    <div class="episode-actions"><button class="play" type="button" data-action="play" data-folder="${esc(r.folder_key)}" data-path="${esc(r.relative_path)}" data-number="${esc(r.number)}"><svg aria-hidden="true"><use href="#i-play"/></svg> Riproduci</button><button class="watch-toggle" type="button" data-action="watch" data-folder="${esc(r.folder_key)}" data-path="${esc(r.relative_path)}" data-number="${esc(r.number)}">${r.watched?'Segna non visto':'Segna visto'}</button>${r.is_movie?'':`<button class="edit" type="button" data-action="edit" data-folder="${esc(r.folder_key)}" data-path="${esc(r.relative_path)}" data-number="${esc(r.number)}">Modifica</button>`}</div>
  </article>`).join('');
}

function renderContinue(){
  const panel=$('#continuePanel'),record=state.lastProgress;
  panel.classList.toggle('hidden',!record);
  if(!record)return;
  $('#continueTitle').textContent=`${record.is_movie?'Film':'Episodio'} ${displayNumber(record)} · ${record.manual_title||record.name_ita||record.current_name}`;
  $('#continueTime').textContent=`Riprendi da ${formatTime(record.playback?.position)}${record.playback?.duration?` su ${formatTime(record.playback.duration)}`:''}`;
}

function openPlayer(record){
  if(playerDialog.open)return;
  state.loadSequence++;state.playing=record;state.lastProgressSave=0;state.closingPlayer=false;
  $('#playerTitle').textContent=`${record.is_movie?'Film':'Episodio'} ${displayNumber(record)}`;
  $('#playerSubtitle').textContent=record.manual_title||record.name_ita||record.name_eng||record.current_name;
  $('#playerTime').textContent='00:00 / 00:00';
  videoPlayer.onloadedmetadata=()=>{if(state.playing!==record)return;const saved=Number(record.playback?.position)||0;if(saved>0&&saved<videoPlayer.duration-10)videoPlayer.currentTime=saved;videoPlayer.play().catch(()=>{});};
  videoPlayer.src=`/api/media?folder_key=${encodeURIComponent(record.folder_key)}&path=${encodeURIComponent(record.relative_path)}`;
  playerDialog.showModal();videoPlayer.load();
}

function savePlayback(force=false,completed=false){
  const record=state.playing;if(!record||videoPlayer.readyState<1||!Number.isFinite(videoPlayer.currentTime))return Promise.resolve();
  const now=Date.now();if(!force&&now-state.lastProgressSave<5000)return Promise.resolve();state.lastProgressSave=now;
  const payload={folder_key:record.folder_key,relative_path:record.relative_path,number:record.number,position:videoPlayer.currentTime,duration:Number.isFinite(videoPlayer.duration)?videoPlayer.duration:0,completed};
  state.progressQueue=state.progressQueue.catch(()=>{}).then(async()=>{
    const response=await fetch('/api/progress',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const data=await response.json();if(!response.ok)throw new Error(data.error||'Salvataggio non riuscito');
    record.playback=data.playback;if(data.playback.completed){record.watched=true;$('#watchedCount').textContent=state.records.filter(r=>r.watched).length;}state.lastProgress=data.playback.completed?null:record;renderContinue();return true;
  }).catch(error=>{showError(`Impossibile salvare il punto di visione: ${error.message}`);return false;});
  return state.progressQueue;
}

async function closePlayer(){
  if(state.closingPlayer)return;state.closingPlayer=true;
  const completed=videoPlayer.ended;videoPlayer.pause();await savePlayback(true,completed);
  videoPlayer.onloadedmetadata=null;videoPlayer.removeAttribute('src');videoPlayer.load();state.playing=null;playerDialog.close();state.closingPlayer=false;render();
}

function openEditor(record){
  if(!record)return;state.loadSequence++;state.editing=record;
  $('#dialogTitle').textContent=record.is_special?'Speciale JAP R133 · INT 1134':`Episodio JAP ${record.number}`;$('#currentFolder').textContent=[record.folder_path,record.season_folder].filter(Boolean).join(' · ');$('#episodeNumber').value=record.number;$('#episodeNumber').disabled=Boolean(record.is_special);$('#excelTitle').textContent=record.name_ita||record.title_card_observed||'Non disponibile';$('#englishTitle').textContent=record.name_eng||'Da inserire';$('#japaneseTitle').textContent=record.name_jap||'Da inserire';$('#currentName').textContent=record.current_name;
  const cardPanel=$('#titleCardPanel'),cardImage=$('#titleCardImage'),cardLink=$('#titleCardLink');
  cardPanel.classList.toggle('hidden',!record.title_card_url);
  if(record.title_card_url){cardImage.src=record.title_card_url;cardLink.href=record.title_card_url;$('#titleCardCaption').textContent=[record.title_card_observed,record.title_card_time?`fotogramma ${record.title_card_time}`:'',record.title_card_certainty].filter(Boolean).join(' · ');}
  else{cardImage.removeAttribute('src');cardLink.href='#';$('#titleCardCaption').textContent='';}
  $('#referenceIta').value=record.title_overrides?.name_ita||record.excel_name_ita||record.missing_title||record.title_card_observed||'';
  $('#referenceEng').value=record.title_overrides?.name_eng||record.excel_name_eng||'';
  $('#referenceJap').value=record.title_overrides?.name_jap||record.excel_name_jap||'';
  $('#manualTitle').value=record.manual_title||'';$('#newFileName').value=record.current_name;updatePreview();editor.showModal();setTimeout(()=>$('#referenceIta').focus(),50);
}
function updatePreview(){if(state.editing){$('#beforeName').textContent=state.editing.current_name;$('#newName').textContent=$('#newFileName').value.trim();}}
function showError(message){$('#error').textContent=message;$('#error').classList.remove('hidden');}
function toast(message){const node=$('#toast');node.textContent=message;node.classList.remove('hidden');setTimeout(()=>node.classList.add('hidden'),3500);}
function syncThemeButton(){const dark=document.documentElement.dataset.theme==='dark';themeToggle.querySelector('span').textContent=dark?'Tema chiaro':'Tema scuro';themeToggle.setAttribute('aria-label',dark?'Passa al tema chiaro':'Passa al tema scuro');themeToggle.setAttribute('aria-pressed',String(dark));}

list.addEventListener('click',async event=>{
  const button=event.target.closest('[data-action]');if(!button)return;
  const record=state.records.find(r=>r.folder_key===button.dataset.folder&&r.relative_path===button.dataset.path);if(!record)return;
  if(button.dataset.action==='edit'){openEditor(record);return;}
  if(button.dataset.action==='play'){openPlayer(record);return;}
  button.disabled=true;
  try{
    const payload={folder_key:record.folder_key,relative_path:record.relative_path,number:record.number,watched:!record.watched};
    const response=await fetch('/api/watched',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Impossibile aggiornare lo stato');
    record.watched=data.watched;record.watched_at=data.watched_at;$('#watchedCount').textContent=state.records.filter(r=>r.watched).length;render();
    toast(record.watched?'Episodio segnato come visto':'Episodio segnato come non visto');
  }catch(error){window.alert(error.message);}finally{button.disabled=false;}
});
$('#continueButton').addEventListener('click',()=>{if(state.lastProgress)openPlayer(state.lastProgress);});
$('#closePlayer').addEventListener('click',closePlayer);
playerDialog.addEventListener('cancel',event=>{event.preventDefault();closePlayer();});
videoPlayer.addEventListener('timeupdate',()=>{$('#playerTime').textContent=`${formatTime(videoPlayer.currentTime)} / ${formatTime(videoPlayer.duration)}`;savePlayback();});
videoPlayer.addEventListener('pause',()=>{if(!videoPlayer.ended&&!state.closingPlayer)savePlayback(true);});
videoPlayer.addEventListener('ended',async()=>{if(await savePlayback(true,true)){render();toast('Video completato e segnato come visto');}});
videoPlayer.addEventListener('error',()=>{if(state.playing&&videoPlayer.getAttribute('src'))showError('Impossibile riprodurre il video. Verifica che il file sia disponibile e supportato dal browser.');});
window.addEventListener('beforeunload',()=>{if(state.playing&&videoPlayer.readyState>=1&&navigator.sendBeacon){const data=new Blob([JSON.stringify({folder_key:state.playing.folder_key,relative_path:state.playing.relative_path,number:state.playing.number,position:videoPlayer.currentTime,duration:Number.isFinite(videoPlayer.duration)?videoPlayer.duration:0,completed:videoPlayer.ended})],{type:'application/json'});navigator.sendBeacon('/api/progress',data);}});
search.addEventListener('input',render);filter.addEventListener('change',render);folderFilter.addEventListener('change',render);$('#reload').addEventListener('click',load);$('#newFileName').addEventListener('input',updatePreview);
$('#chooseFolder').addEventListener('click',async()=>{const button=$('#chooseFolder');button.disabled=true;button.textContent='Scelta in corso…';try{const response=await fetch('/api/select-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const data=await response.json();if(!response.ok)throw new Error(data.error||'Impossibile scegliere la cartella');if(!data.cancelled)$('#videoFolderPath').value=data.path;}catch(error){window.alert(error.message);}finally{button.disabled=false;button.textContent='Sfoglia…';}});
$('#applyFolder').addEventListener('click',async()=>{const path=$('#videoFolderPath').value.trim(),kind=$('#libraryKind').value,label=$('#libraryLabel').value.trim(),button=$('#applyFolder');button.disabled=true;try{const response=await fetch('/api/video-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({path,kind,label})});const data=await response.json();if(!response.ok)throw new Error(data.error||'Cartella non valida');$('#videoFolderPath').value='';$('#libraryLabel').value='';toast(`Raccolta aggiunta: ${data.library.label}`);await load();}catch(error){window.alert(error.message);}finally{button.disabled=false;}});
$('#folders').addEventListener('click',async event=>{const button=event.target.closest('[data-remove-folder]');if(!button)return;const key=button.dataset.removeFolder;if(!window.confirm('Rimuovere questa raccolta dal sito? I video non verranno eliminati.'))return;button.disabled=true;try{const response=await fetch('/api/remove-folder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});const data=await response.json();if(!response.ok)throw new Error(data.error||'Rimozione non riuscita');toast('Raccolta rimossa dal sito');await load();}catch(error){window.alert(error.message);}finally{button.disabled=false;}});
$('#restoreCurrent').addEventListener('click',()=>{$('#newFileName').value=state.editing?.current_name||'';updatePreview();});
$('#standardName').addEventListener('click',()=>{$('#newFileName').value=state.editing?standardName(state.editing):'';updatePreview();});
$('#saveTitle').addEventListener('click',async()=>{
  if(!state.editing)return;
  const title=$('#manualTitle').value.trim(),button=$('#saveTitle');button.disabled=true;button.textContent='Salvataggio…';
  try{
    const response=await fetch('/api/title',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder_key:state.editing.folder_key,number:state.editing.number,title})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Salvataggio non riuscito');
    state.editing.manual_title=title;render();toast(title?'Titolo personale salvato':'Titolo personale rimosso');
  }catch(error){window.alert(error.message);}finally{button.disabled=false;button.textContent='Salva titolo personale';}
});
$('#saveReferenceTitles').addEventListener('click',async()=>{
  if(!state.editing)return;
  const values={name_ita:$('#referenceIta').value.trim(),name_eng:$('#referenceEng').value.trim(),name_jap:$('#referenceJap').value.trim()};
  const button=$('#saveReferenceTitles');button.disabled=true;button.textContent='Salvataggio…';
  try{
    const response=await fetch('/api/reference-titles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder_key:state.editing.folder_key,number:state.editing.number,...values})});
    const data=await response.json();if(!response.ok)throw new Error(data.error||'Salvataggio non riuscito');
    state.editing.title_overrides=data.titles||{};
    state.editing.name_ita=values.name_ita||state.editing.excel_name_ita||state.editing.missing_title||'';
    state.editing.name_eng=values.name_eng||state.editing.excel_name_eng||'';
    state.editing.name_jap=values.name_jap||state.editing.excel_name_jap||'';
    $('#excelTitle').textContent=state.editing.name_ita||'Non disponibile';$('#englishTitle').textContent=state.editing.name_eng||'Non disponibile';$('#japaneseTitle').textContent=state.editing.name_jap||'Non disponibile';render();toast('Titoli di riferimento salvati');
  }catch(error){window.alert(error.message);}finally{button.disabled=false;button.textContent='Salva titoli di riferimento';}
});
document.querySelectorAll('[data-close-editor]').forEach(button=>button.addEventListener('click',()=>editor.close()));
$('#editorForm').addEventListener('submit',async event=>{
  event.preventDefault();if(!state.editing)return;
  const record=state.editing,newName=$('#newFileName').value.trim(),renameChanged=newName!==record.current_name;
  const newNumber=Number($('#episodeNumber').value),numberChanged=newNumber!==record.number;
  if(!Number.isInteger(newNumber)||newNumber<1||newNumber>9999){window.alert('Inserisci un numero JAP valido.');return;}
  const titles={name_ita:$('#referenceIta').value.trim(),name_eng:$('#referenceEng').value.trim(),name_jap:$('#referenceJap').value.trim()};
  const personalTitle=$('#manualTitle').value.trim();
  if(renameChanged||numberChanged){
    const changes=[];
    if(numberChanged)changes.push(`Numero JAP: ${record.number} → ${newNumber}`);
    if(renameChanged)changes.push(`Nome file:\n${record.current_name}\n→ ${newName}`);
    const message=`Confermi queste modifiche nel ${record.folder_label}?\n\n${changes.join('\n\n')}`;
    if(!window.confirm(message))return;
  }
  const button=$('#confirmRename');button.disabled=true;button.textContent='Salvataggio…';let savedAnything=false;
  try{
    if(numberChanged){
      const numberResponse=await fetch('/api/episode-number',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder_key:record.folder_key,current_name:record.current_name,relative_path:record.relative_path,old_number:record.number,new_number:newNumber})});
      const numberData=await numberResponse.json();if(!numberResponse.ok)throw new Error(numberData.error||'Modifica del numero JAP non riuscita');
      record.number=newNumber;savedAnything=true;
    }
    const titleResponse=await fetch('/api/reference-titles',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder_key:record.folder_key,number:newNumber,...titles})});
    const titleData=await titleResponse.json();if(!titleResponse.ok)throw new Error(titleData.error||'Salvataggio titoli non riuscito');savedAnything=true;
    const personalResponse=await fetch('/api/title',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder_key:record.folder_key,number:newNumber,title:personalTitle})});
    const personalData=await personalResponse.json();if(!personalResponse.ok)throw new Error(personalData.error||'Salvataggio titolo personale non riuscito');
    if(renameChanged){
      const renameResponse=await fetch('/api/rename',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder_key:record.folder_key,current_name:record.current_name,relative_path:record.relative_path,new_name:newName,confirm:true})});
      const renameData=await renameResponse.json();if(!renameResponse.ok)throw new Error(renameData.error||'Rinomina non riuscita');
    }
    editor.close();toast(renameChanged||numberChanged?'Identità episodio e titoli aggiornati':'Titoli salvati');await load();
  }catch(error){window.alert(`${error.message}${savedAnything?'\nAlcune modifiche sono già state salvate. La libreria verrà aggiornata.':''}`);if(savedAnything){if(editor.open)editor.close();await load();}}finally{button.disabled=false;button.textContent='Salva tutte le modifiche';}
});
editor.addEventListener('close',()=>{$('#titleCardImage').removeAttribute('src');$('#episodeNumber').disabled=false;state.editing=null;});
themeToggle.addEventListener('click',()=>{const next=document.documentElement.dataset.theme==='dark'?'light':'dark';document.documentElement.dataset.theme=next;try{localStorage.setItem('conan-theme',next)}catch(e){}syncThemeButton();});
document.addEventListener('keydown',event=>{if(event.key==='/'&&!event.ctrlKey&&!event.metaKey&&!event.altKey&&!editor.open&&!playerDialog.open&&!/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)){event.preventDefault();search.focus();}});
syncThemeButton();load();setInterval(()=>{if(!document.hidden&&!state.editing&&!state.playing)load({silent:true});},15000);
