'use strict';
const $ = id => document.getElementById(id);
const clone = value => JSON.parse(JSON.stringify(value));
const tabId = crypto.randomUUID();
let doc, revision, selected = null, mine = false, dirty = false, undo = [], redo = [], drag = null, busy = false;
const errors = {editor_busy:'Otro editor tiene el turno. Este plano sigue en solo lectura.',lease_required:'Tu turno de edición ha caducado. Conserva el borrador y vuelve a pedir turno.',revision_conflict:'El plano maestro cambió. No se ha sobrescrito. Conserva tu borrador antes de recargar.',save_failed:'No se pudo guardar. Comprueba el estado antes de volver a intentar.'};
function status(text) { $('status').textContent = text; }
async function api(path, data) {
  const response = await fetch('/api/' + path,{method:data === undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-KH-Editor':'1','X-KH-Tab':tabId},body:data === undefined?undefined:JSON.stringify(data)});
  const result = await response.json();
  if(!response.ok) throw new Error(errors[result.error] || 'No se pudo completar: ' + result.error);
  return result;
}
function seat() { return doc?.seats.find(s=>s.id === selected); }
function snapshot() { undo.push(clone(doc)); if(undo.length>100)undo.shift(); redo=[]; dirty=true; }
function controls() {
  for(const id of ['block','add','save','cancel']) $(id).disabled=!mine||busy;
  $('remove').disabled=!mine||!seat()||seat().locked||busy;
  $('undo').disabled=!mine||!undo.length||busy; $('redo').disabled=!mine||!redo.length||busy;
  $('take').disabled=mine||busy; $('room').disabled=!mine||busy;
  for(const id of ['label','x','y','locked']) $(id).disabled=!mine||!seat()||busy||(seat().locked&&id!=='locked');
  $('lease').textContent=mine?'Tu turno de edición':'Solo lectura';
}
function render() {
  $('roomTitle').textContent=doc.room_name; $('room').value=doc.room_name;
  $('count').textContent=doc.seats.length+' asientos · '+doc.seats.filter(s=>!s.calibrated).length+' pendientes de calibrar';
  $('plan').setAttribute('viewBox',`0 0 ${doc.screen_width} ${doc.screen_height}`);
  $('background').setAttribute('width',doc.screen_width);$('background').setAttribute('height',doc.screen_height);
  $('background').setAttribute('fill',$('snap').checked?'url(#grid)':'white');
  $('empty').hidden=doc.seats.length>0;
  $('seats').replaceChildren();
  for(const s of doc.seats.filter(s=>s.visible)) {
    const ns='http://www.w3.org/2000/svg',g=document.createElementNS(ns,'g'),r=document.createElementNS(ns,'rect'),t=document.createElementNS(ns,'text');
    g.setAttribute('transform',`translate(${s.x},${s.y})`);g.dataset.id=s.id;
    g.setAttribute('class','seat'+(s.id===selected?' selected':'')+(s.locked?' locked':''));
    r.setAttribute('width',40);r.setAttribute('height',40);r.setAttribute('rx',8);
    t.setAttribute('x',20);t.setAttribute('y',26);t.textContent=s.label;
    g.append(r,t);$('seats').append(g);
  }
  const s=seat();$('selectedText').textContent=s?'ID estable: '+s.id.slice(0,8):'Ninguno';
  $('label').value=s?.label||'';$('x').value=s?.x??'';$('y').value=s?.y??'';$('locked').checked=s?.locked||false;
  controls();
}
async function load() {
  if(dirty&&!confirm('Hay cambios sin guardar. ¿Descartarlos y recargar el maestro?'))return;
  const result=await api('layout');doc=result.document;revision=result.revision;mine=result.lease==='mine';dirty=false;undo=[];redo=[];selected=null;render();status('Maestro cargado · versión '+revision.slice(0,8));
}
function run(action){return async(...args)=>{try{await action(...args)}catch(e){status(e.message)}};}
$('take').onclick=run(async()=>{if(!dirty)await load();await api('lease',{});mine=true;controls();status('Puedes editar. El plano maestro solo cambia al guardar.');});
$('reload').onclick=run(load);
$('save').onclick=run(async()=>{
  busy=true;controls();try{const result=await api('save',{revision,document:doc});revision=result.revision;dirty=false;status('Guardado confirmado · versión '+revision.slice(0,8)+' · copia anterior conservada');}finally{busy=false;controls();}
});
$('cancel').onclick=run(async()=>{if(dirty&&!confirm('¿Descartar los cambios sin guardar?'))return;await api('release',{});dirty=false;mine=false;await load();});
$('room').onchange=()=>{if(!mine||busy)return;const name=$('room').value.trim();if(!name){render();return;}snapshot();doc.room_name=name;render();};
for(const id of ['label','x','y','locked']) $(id).onchange=()=>{const s=seat();if(!mine||busy||!s||s.locked&&id!=='locked')return;let value=$(id).value;if(id==='locked')value=$(id).checked;else if(id==='x'||id==='y'){value=Number(value);const max=doc[id==='x'?'screen_width':'screen_height']-40;if(!Number.isFinite(value)||value<0||value>max){render();return;}}else{value=value.trim();if(!value){render();return;}}snapshot();s[id]=value;render();};
function newSeat(x,y,label,row=null,column=null){return {id:crypto.randomUUID(),label:String(label),preset:0,camera_role:'comments',x,y,row,column,type:'delegate',visible:true,locked:false,calibrated:false};}
$('add').onclick=()=>{if(!mine||busy)return;snapshot();const s=newSeat(60,80,doc.seats.length+1);doc.seats.push(s);selected=s.id;render();};
$('remove').onclick=()=>{if(!mine||busy||!seat()||seat().locked)return;snapshot();doc.seats=doc.seats.filter(s=>s.id!==selected);selected=null;render();};
$('undo').onclick=()=>{if(!mine||busy||!undo.length)return;redo.push(clone(doc));doc=undo.pop();dirty=true;render();};
$('redo').onclick=()=>{if(!mine||busy||!redo.length)return;undo.push(clone(doc));doc=redo.pop();dirty=true;render();};
$('snap').onchange=()=>render();
$('zoom').onchange=()=>{$('plan').style.width=(Number($('zoom').value)*100)+'%';};
$('block').onclick=()=>{if(mine&&!busy){$('blockError').textContent='';$('blockDialog').showModal();}};
$('closeDialog').onclick=()=>$('blockDialog').close();
$('blockForm').onsubmit=event=>{
 event.preventDefault();if(!mine||busy)return;
 const groups=$('pattern').value.split('-').map(Number),rows=Number($('rows').value),dx=Number($('spacing').value),dy=Number($('rowSpacing').value);
 const columns=groups.reduce((a,b)=>a+b,0),count=rows*columns;
 if(doc.seats.length+count>1000||60+(columns-1)*dx+(groups.length-1)*40+40>doc.screen_width||100+(rows-1)*dy+40>doc.screen_height){$('blockError').textContent='El bloque no cabe en este plano. Reduce filas, grupos o separaciones.';return;}
 snapshot();let n=doc.seats.length+1;
 for(let r=0;r<rows;r++){let x=60,col=1;for(const group of groups){for(let c=0;c<group;c++){doc.seats.push(newSeat(x,100+r*dy,n++,r+1,col++));x+=dx;}x+=40;}}
 $('blockDialog').close();render();status('Bloque creado en el borrador. Pulsa Guardar plano para conservarlo.');
};
function point(event){const p=new DOMPoint(event.clientX,event.clientY);return p.matrixTransform($('plan').getScreenCTM().inverse());}
$('plan').onpointerdown=event=>{const g=event.target.closest('.seat');selected=g?.dataset.id||null;render();const s=seat();if(!mine||busy||!s||s.locked)return;const p=point(event);drag={id:s.id,start:p,x:s.x,y:s.y,before:clone(doc)};$('plan').setPointerCapture(event.pointerId);event.preventDefault();};
$('plan').onpointermove=event=>{if(!drag||!mine||busy)return;const s=doc.seats.find(s=>s.id===drag.id),p=point(event),step=$('snap').checked?10:1;s.x=Math.max(0,Math.min(doc.screen_width-40,Math.round((drag.x+p.x-drag.start.x)/step)*step));s.y=Math.max(0,Math.min(doc.screen_height-40,Math.round((drag.y+p.y-drag.start.y)/step)*step));render();};
function endDrag(){if(!drag)return;const s=seat();if(s&&(s.x!==drag.x||s.y!==drag.y)){undo.push(drag.before);redo=[];dirty=true;}drag=null;controls();}
$('plan').onpointerup=endDrag;$('plan').onpointercancel=endDrag;
$('plan').onkeydown=event=>{if(!mine||busy||!seat()||seat().locked)return;if(event.key==='Delete'){event.preventDefault();$('remove').click();return;}const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];if(!delta)return;event.preventDefault();snapshot();const s=seat(),step=(event.shiftKey?10:1)*($('snap').checked?10:1);s.x=Math.max(0,Math.min(doc.screen_width-40,s.x+delta[0]*step));s.y=Math.max(0,Math.min(doc.screen_height-40,s.y+delta[1]*step));render();};
setInterval(run(async()=>{if(!mine&&!dirty){const result=await api('layout');if(result.revision!==revision){doc=result.document;revision=result.revision;render();status('Plano actualizado desde el maestro · versión '+revision.slice(0,8));}}}),5000);
setInterval(run(async()=>{if(mine){try{await api('lease',{});}catch(e){mine=false;controls();throw e;}}}),25000);
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
run(load)();
