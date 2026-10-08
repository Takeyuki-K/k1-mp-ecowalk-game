const assert=require('node:assert/strict');const c=require('../k1_ecowalk_game/web/controls.js');
assert.deepEqual(c.keyboard(new Set(['w','shift']),.9),{v:4,w:0,brake:false});
assert.deepEqual(c.keyboard(new Set(),4),{v:0,w:0,brake:false});
assert.equal(c.joystick(0,-1).v,4.5);assert.equal(c.joystick(-1,0).w,1);assert.equal(c.joystick(1,0).w,-1);assert.equal(c.joystick(0,1).v,0);
assert.equal(c.gamepad({mapping:'standard',axes:[0,-1],buttons:[]}).v,4.5);
assert.deepEqual(c.gamepad({mapping:'standard',axes:[0,-1],buttons:[{pressed:true}]}),{v:0,w:0,brake:false});
assert.deepEqual(c.gamepad(null),{v:0,w:0,brake:false});console.log('input mappings OK');
