'use strict';
const EcoMap={draw(canvas,course,robot){
 const c=canvas.getContext('2d'),W=canvas.width,H=canvas.height,b=course.bounds,pad=24;
 const scale=Math.min((W-2*pad)/(b[1]-b[0]+1),(H-2*pad)/(b[3]-b[2]+1));
 const point=(x,y)=>[W/2+(x-(b[0]+b[1])/2)*scale,H/2-(y-(b[2]+b[3])/2)*scale];
 const polygon=(points,color)=>{c.fillStyle=color;c.beginPath();points.forEach(([x,y],i)=>{const p=point(x,y);i?c.lineTo(...p):c.moveTo(...p);});c.closePath();c.fill();};
 const box=(x,y,hx,hy,color)=>polygon([[x-hx,y-hy],[x+hx,y-hy],[x+hx,y+hy],[x-hx,y+hy]],color);
 c.clearRect(0,0,W,H);c.fillStyle='#08171d';c.fillRect(0,0,W,H);
 if(course.corridor_half_width){const h=course.corridor_half_width;polygon([...course.centerline.map(([x,y])=>[x,y+h]),...course.centerline.slice().reverse().map(([x,y])=>[x,y-h])],'#25443f');}
 else box((b[0]+b[1])/2,(b[2]+b[3])/2,(b[1]-b[0])/2,(b[3]-b[2])/2,'#25443f');
 c.strokeStyle='#92b2ac';c.lineWidth=1;c.setLineDash([5,6]);c.beginPath();course.centerline.forEach(([x,y],i)=>{const p=point(x,y);i?c.lineTo(...p):c.moveTo(...p);});c.stroke();c.setLineDash([]);
 for(const [x1,y1,x2,y2,width] of course.walls){const a=Math.atan2(y2-y1,x2-x1),dx=Math.cos(a)*width/2,dy=Math.sin(a)*width/2,nx=-dy,ny=dx;polygon([[x1-dx+nx,y1-dy+ny],[x2+dx+nx,y2+dy+ny],[x2+dx-nx,y2+dy-ny],[x1-dx-nx,y1-dy-ny]],'#9ab0b8');}
 for(const [x,y,hx,hy] of course.obstacles)box(x,y,hx,hy,'#e79863');
 box(...course.goal,...course.goal_half_size,'#91f5c0');
 c.font='bold 15px system-ui';c.textAlign='center';c.fillStyle='#91f5c0';const g=point(...course.goal);c.fillText('GOAL',g[0],g[1]-course.goal_half_size[1]*scale-7);
 const start=point(0,0);c.fillStyle='#d7e7e1';c.beginPath();c.arc(...start,3,0,Math.PI*2);c.fill();c.fillText('START',start[0],start[1]+23);
 const r=point(robot.x,robot.y),yaw=robot.yaw||0;c.save();c.translate(...r);c.rotate(-yaw);c.fillStyle='#ffd166';c.strokeStyle='#142027';c.lineWidth=2;c.beginPath();c.moveTo(12,0);c.lineTo(-8,-7);c.lineTo(-4,0);c.lineTo(-8,7);c.closePath();c.fill();c.stroke();c.restore();
}};
