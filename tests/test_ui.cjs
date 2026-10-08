// Optional DOM interaction checks: npm install --prefix /tmp/k1-ui-check jsdom
// NODE_PATH=/tmp/k1-ui-check/node_modules node tests/test_ui.cjs
const {JSDOM}=require('jsdom'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const web=path.join(__dirname,'../k1_ecowalk_game/web');
(async()=>{
let status={result:null};const dom=new JSDOM(fs.readFileSync(path.join(web,'index.html'),'utf8'),{url:'http://localhost:8090',runScripts:'outside-only',pretendToBeVisual:true}),w=dom.window;
w.setTimeout=()=>0;w.fetch=async url=>({ok:true,json:async()=>url==='/status'?status:{ok:true}});w.document.hasFocus=()=>true;
w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({},{get:(o,k)=>o[k]||(()=>{}),set:(o,k,v)=>(o[k]=v,true)});
w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');};
w.eval(fs.readFileSync(path.join(web,'controls.js'),'utf8'));w.eval(fs.readFileSync(path.join(web,'minimap.js'),'utf8')+'\n'+fs.readFileSync(path.join(web,'game.js'),'utf8')+'\nwindow.TestUI={start,refresh,readCommand};\n'+fs.readFileSync(path.join(web,'archive.js'),'utf8'));
await w.TestUI.start(3);assert.match(w.document.querySelector("#stageTitle").textContent,/S-CURVE/);assert.equal(w.document.querySelector("#minimapPanel").hidden,false);assert.equal(w.document.querySelector('#welcome').hidden,true);assert.equal(w.document.querySelector('#controls').hidden,false);assert.match(w.document.querySelector('#view').src,/stream.mjpg/);
const run={stage:1,outcome:'playing',energy_wh:.8,average_power_w:120,elapsed_s:24,collisions:0,inside_goal:true,goal_hold_s:.4,score:0,prediction:{energy_8h_wh:960,swaps_8h:null}};status={result:run,sim:{x:20,y:0,yaw:0,mode:'stand'},course:{title:'S-CURVE',bounds:[-2,30,-6.3,6.3],goal:[28,0],goal_half_size:[.75,1],obstacles:[],walls:[],centerline:[[-2,0],[30,0]],corridor_half_width:2.5},render_fps:30};await w.TestUI.refresh();assert.equal(w.document.querySelector('#goalWaiting').hidden,false);assert.equal(w.document.querySelector('#goalProgress').value,.4);
w.dispatchEvent(new w.KeyboardEvent('keydown',{key:'w'}));w.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Shift'}));assert.equal(w.TestUI.readCommand().v,4);w.dispatchEvent(new w.KeyboardEvent('keyup',{key:'w'}));assert.equal(w.TestUI.readCommand().v,0);
w.document.querySelector('#joystickMode').click();assert.equal(w.document.querySelector('#joystickPanel').hidden,false);assert.equal(w.document.querySelector('#keyboardHelp').hidden,true);
w.document.querySelector('#brake').click();assert.equal(w.TestUI.readCommand().brake,true);w.document.querySelector('#stop').click();assert.equal(w.TestUI.readCommand().brake,false);
run.outcome='finished';run.score=2400;await w.TestUI.refresh();assert.equal(w.document.querySelector('#resultDialog').open,true);assert.equal(w.document.querySelector('#resultTitle').textContent,'ゴール！！');assert.match(w.document.querySelector('#resultMetrics').textContent,/0.800 Wh/);assert.equal(w.document.querySelector('#goalWaiting').hidden,true);
w.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape'}));assert.equal(w.document.querySelector('#resultDialog').open,false);
await w.EcoArchive.watch('/replay-local',{id:'test'});status.replay={name:'player',paused:false,speed:1,time:2,duration:20,fraction:.1};run.outcome='playing';await w.TestUI.refresh();assert.equal(w.document.querySelector('#replayControls').hidden,false);assert.equal(w.document.querySelector('#controls').hidden,true);assert.equal(w.TestUI.readCommand().v,0);assert.match(w.document.querySelector('#replayTime').textContent,/2.0 \/ 20.0/);run.outcome='finished';await w.TestUI.refresh();assert.equal(w.document.querySelector('#resultDialog').open,false);
console.log('title / stage / Shift / mode switch / brake / goal overlays / replay controls OK');w.close();
})();
