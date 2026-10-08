/* Original pad concept: k1-mp-ecowalk-teleop (Apache-2.0), Takeyuki-K.
   Nonlinear forward axis gamma=1.7; left drag -> positive yaw; release -> zero. */
(function(root){
'use strict';
const clamp=(n,lo,hi)=>Math.max(lo,Math.min(hi,n));
function joystick(x,y){return {v:4.5*Math.pow(clamp(-y,0,1),1.7),w:clamp(-x,-1,1),brake:false};}
function keyboard(keys,speed){const forward=keys.has('w')||keys.has('arrowup');return {v:forward?(keys.has('shift')?4:clamp(speed,.3,4.5)):0,w:(keys.has('a')||keys.has('arrowleft')?.6:0)-(keys.has('d')||keys.has('arrowright')?.6:0),brake:keys.has('b')};}
function gamepad(pad){if(!pad||pad.mapping!=='standard')return {v:0,w:0,brake:false};const dead=v=>Math.abs(v)<.12?0:Math.sign(v)*(Math.abs(v)-.12)/.88;let cmd=joystick(dead(pad.axes[0]||0),dead(pad.axes[1]||0));if(pad.buttons[0]?.pressed)return {v:0,w:0,brake:false};if(pad.buttons[1]?.pressed)return {v:0,w:0,brake:true};return cmd;}
const api={joystick,keyboard,gamepad};root.EcoControls=api;if(typeof module!=='undefined')module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
