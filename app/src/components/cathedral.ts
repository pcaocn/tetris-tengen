import { drawForeground } from "./cathedralForeground";
// Architecture landmarks use the 825 × 1032 reference photograph as a coordinate plane.
type Context = CanvasRenderingContext2D;
type Paint = string | CanvasGradient;
type Stone = readonly [string, string, string, string, string];

const brick: Stone = ["#782728", "#c43b23", "#f16b32", "#ffab65", "#ba3f26"];
const ivory: Stone = ["#743e2d","#d6a576","#fff0c9","#fff9df","#ad724e"];
const jade: Stone = ["#0c5044", "#048960", "#26b778", "#b3df86", "#176c52"];
const gilt = ["#683710", "#b97a27", "#ffe89a", "#cc9037", "#764217"];

function horizontal(c: Context, x: number, width: number, colors: readonly string[]) {
  const g = c.createLinearGradient(x, 0, x + width, 0);
  colors.forEach((color, i) => g.addColorStop(i / (colors.length - 1), color));
  return g;
}

function ellipse(c: Context, x: number, y: number, rx: number, ry: number, fill: Paint) {
  c.fillStyle = fill;
  c.beginPath();
  c.ellipse(x, y, rx, ry, 0, 0, 2 * Math.PI);
  c.fill();
}

function band(c: Context, x: number, y: number, w: number, h: number, colors: readonly string[] = gilt) {
  c.fillStyle = horizontal(c, x, w, colors);
  c.fillRect(x, y, w, h);
  c.fillStyle = "#fff4c58f";
  c.fillRect(x, y, w, Math.min(1.15, h / 4));
  c.fillStyle = "#20120fc9";
  c.fillRect(x, y + h - 1, w, 1);
}

function beads(c: Context, x: number, y: number, w: number, n: number) {
  for (let i = 0; i < n; i++) {
    const px = x + (i + 0.5) * w / n;
    ellipse(c, px, y, 1.7, 2, "#986023");
    ellipse(c, px - 0.35, y - 0.5, 0.95, 1.15, "#ffe19a");
  }
}

function arch(c: Context, x: number, y: number, w: number, h: number, stone: Stone) {
  const r = w / 2;
  c.beginPath();
  c.moveTo(x-r, y+h);
  c.arc(x, y+r, r, Math.PI, 2*Math.PI);
  c.lineTo(x+r,y+h);
  c.closePath();
  c.fillStyle = horizontal(c,x-r,w,["#070a10","#10151c","#392927"]);
  c.fill();
  for (const [thickness,color] of [[5,stone[0]],[3.4,stone[3]],[1.4,stone[1]]] as const) {
    c.lineWidth=thickness;
    c.strokeStyle=color;
    c.stroke();
  }
  c.fillStyle="#b88247a8";
  c.fillRect(x-.55,y+2,1.1,h-2);
  c.fillRect(x-r+1,y+h*.62,w-2,.85);
  band(c,x-r-2,y+h,w+4,2.5,stone);
}

type Point = readonly [number, number];
function face(c: Context, points: Point[], fill: Paint, edge?: string, weight=1) {
  c.beginPath();
  points.forEach(([x,y],i) => i ? c.lineTo(x,y) : c.moveTo(x,y));
  c.closePath(); c.fillStyle=fill; c.fill();
  if(edge){c.strokeStyle=edge;c.lineWidth=weight;c.stroke();}
}

type Pattern = "gold"|"green"|"blue"|"scales"|"net"|"plaid"|"cheat";
function onion(c:Context,x:number,y:number,r:number,h:number,tip:number,pattern:Pattern){
  const palette = {
    gold:["#b06812","#ffdd68"],cheat:["#167640","#afdf65"],
    green:["#007b54","#ffe5a1"],blue:["#065ab0","#fff8d8"],
    scales:["#dd2924","#13924c"],net:["#ad931e","#efcb48"],plaid:["#1c6859","#ad3b3c"],
  }[pattern];
  // Horizontal radii measured from onion base (t=0) to neck (t=1).
  function radius(t:number){
    return r*(.74*(1-t)+.62*Math.sin(Math.PI*Math.pow(t,.72))*(1-t)+.035*t);
  }
  function point(t:number,longitude:number,twist:number):Point{
    return [x+radius(t)*Math.sin(longitude+twist*t),y-h*t];
  }
  const outline:Point[]=[];
  for(let i=0;i<=60;i++)outline.push([x-radius(i/60),y-h*i/60]);
  for(let i=60;i>=0;i--)outline.push([x+radius(i/60),y-h*i/60]);
  c.save();face(c,outline,palette[0]);c.clip();
  if(pattern==="green"||pattern==="blue"||pattern==="plaid"){
    const stripes=pattern==="blue"?17:15,twist=pattern==="blue"?-.42:1.50;
    // Sweep each ribbon over the visible hemisphere; narrow bands at the edges
    // turn away from the light. Projecting both edges avoids horizontal seams.
    const step=2*Math.PI/stripes;
    const edge=(k:number,t:number)=>point(t,Math.max(-Math.PI/2,Math.min(Math.PI/2,k*step+twist*t)),0);
    for(let k=-stripes;k<stripes;k++){
      if(k*step+Math.min(0,twist)>Math.PI/2 || (k+1)*step+Math.max(0,twist)<-Math.PI/2)continue;
      const ribbon:Point[]=[];
      for(let i=0;i<=64;i++)ribbon.push(edge(k,i/64));
      for(let i=64;i>=0;i--)ribbon.push(edge(k+1,i/64));
      const [lx]=edge(k,.28),[rx]=edge(k+1,.28);
      const colors=k%2?[palette[1],pattern==="blue"?"#ffffff":"#ffefb6",palette[1]]:
        [palette[0],pattern==="blue"?"#188ed4":"#179b61",palette[0]];
      face(c,ribbon,horizontal(c,lx,Math.max(1,rx-lx),colors),"#835f251a",.55);
      // A slender reflected light follows the raised enamel rib.
      if(k%2===0){
        c.beginPath();
        for(let j=0;j<=42;j++){
          const t=.035+.92*j/42;
          const [px,py]=edge(k+.72,t);
          if(j===0)c.moveTo(px,py);else c.lineTo(px,py);
        }
        c.strokeStyle=pattern==="blue"?"#a7e4ff8a":"#a2f3bb85";
        c.lineWidth=r*.023;
        c.stroke();
      }
    }
  }else if(pattern==="scales"||pattern==="net"){
    face(c,outline,palette[1]);
    for(let j=0;j<8;j++)for(let k=-7;k<=7;k++){
      const a=(k+.5*(j%2))*Math.PI/6;
      if(Math.abs(a)>Math.PI/2+.01)continue;
      const t=j/8,mid=(j+.5)/8,top=(j+1)/8;
      const tile=[point(t,a,0),point(mid,a+Math.PI/12,0),point(top,a,0),point(mid,a-Math.PI/12,0)];
      face(c,tile,pattern==="net"?"#ffd144":palette[(k+18)%2],pattern==="net"?"#118048":"#cfab56",pattern==="net"?2.2:.8);
      if(pattern==="scales"){
        face(c,[tile[0],tile[1],tile[2]],"#49181c77");
        face(c,[tile[0],tile[3],point(mid,a-.12,0)],"#ffd569a8");
      }
    }
  }
  if(pattern==="plaid"){
    for(let j=1;j<11;j++){
      c.beginPath();
      for(let i=0;i<=40;i++){
        const lon=-Math.PI/2+i*Math.PI/40;
        const t=j/11+.14*lon;
        const [px,py]=point(Math.min(1,Math.max(0,t)),lon,0);
        if(i===0)c.moveTo(px,py);else c.lineTo(px,py);
      }
      c.lineWidth=2.2;c.strokeStyle="#a96258";c.stroke();
    }
  }
  if(pattern==="gold"||pattern==="cheat"){
    const light=c.createRadialGradient(x+r*.45,y-h*.31,0,x+r*.35,y-h*.32,r*1.3);
    light.addColorStop(0,"#fff2b6");light.addColorStop(.35,palette[1]);light.addColorStop(1,palette[0]);face(c,outline,light);
  }
  const shade=c.createLinearGradient(x-r,0,x+r,0);
  for(const [pos,col] of [[0,"#51312368"],[.26,"#3a210d24"],[.53,"#fff2ab12"],[.76,"#fff6cf55"],[1,"#2b150b63"]] as const)shade.addColorStop(pos,col);
  face(c,outline,shade);
  c.restore();
  band(c,x-r*.76,y-1,r*1.52,4);
  const neck=y-h;
  band(c,x-1,tip,2,neck-tip);
  ellipse(c,x,neck-4,3.8,5.1,horizontal(c,x-4,8,gilt));
  band(c,x-4,tip+4,8,1.4);
}

function fan(c:Context,x:number,y:number,r:number,color:Stone){
  c.beginPath();c.arc(x,y,r,Math.PI,Math.PI*2);c.closePath();c.fillStyle=color[1];c.fill();
  c.lineWidth=2.8;c.strokeStyle=color[3];c.stroke();
  c.beginPath();c.arc(x,y,r*.67,Math.PI,Math.PI*2);c.strokeStyle=color[2];c.lineWidth=3;c.stroke();
  face(c,[[x-r*.42,y-.7],[x,y-r*.52],[x+r*.42,y-.7]],color[0],color[2],1);
  rosette(c,x,y-r*.28,Math.max(1.3,r*.14));
  for(let k=1;k<8;k++)ellipse(c,x+Math.cos(k*Math.PI/8)*r*.83,y-Math.sin(k*Math.PI/8)*r*.83,1.1,1.3,"#ffe3a1");
}
function brickwork(c:Context,x:number,y:number,w:number,h:number){
  c.save();c.beginPath();c.rect(x,y,w,h);c.clip();
  for(let row=0;row<h/5;row++){
    const py=y+row*5;
    c.fillStyle="#350f222e";c.fillRect(x,py,w,.65);
    for(let dx=(row%2)*7;dx<w;dx+=14)c.fillRect(x+dx,py, .75,5);
  }
  c.restore();
}
function rosette(c:Context,x:number,y:number,r:number){
  ellipse(c,x,y,r,r,"#a47331");ellipse(c,x,y,r*.79,r*.79,"#144e4b");
  for(let i=0;i<8;i++){
    const a=i*Math.PI/4;ellipse(c,x+Math.cos(a)*r*.45,y+Math.sin(a)*r*.45,r*.18,r*.18,"#ffdfa0");
  }
  ellipse(c,x,y,r*.19,r*.19,"#ed673b");
}
function tower(c:Context,x:number,roof:number,w:number,bottom:number,small=false){
  const left=x-w/2, h=bottom-roof;
  c.fillStyle=horizontal(c,left,w,brick);c.fillRect(left,roof,w,h);

  const shoulder=roof+h*.46;
  for(const frac of [-.33,0,.33])arch(c,x+frac*w,roof+h*.105,w*.085,h*.20,ivory);
  band(c,left-2,roof+5,w+4,5,ivory);beads(c,left,roof+14,w,16);
  band(c,left-3,roof+19,w+6,3,ivory);
  const spread=w*.63;
  c.fillStyle=horizontal(c,x-spread,spread*2,small?jade:brick);c.fillRect(x-spread,shoulder,spread*2,bottom-shoulder);

  for(let k=-1;k<=1;k++)fan(c,x+k*w*.39,shoulder+1,w*.197,small?brick:ivory);
  band(c,x-spread-3,shoulder+2,spread*2+6,7,ivory);
  for(let k=-1;k<=1;k++){
    const px=x+k*w*.39;
    if(small){fan(c,px,bottom-5,w*.19,brick);continue;}
    face(c,[[px-w*.16,bottom-7],[px,shoulder+15],[px+w*.16,bottom-7]],"#c74625","#ffddad",2.6);
    for(const side of [-1,1]){
      const pilaster=px+side*w*.175;
      band(c,pilaster-1.5,shoulder+11,3,bottom-shoulder-17,ivory);
      band(c,pilaster-3,shoulder+12,6,3);
    }
    rosette(c,px,shoulder+10,3);
    arch(c,px,bottom-h*.24,w*.077,h*.20,ivory);
  }
  // The projecting cornice casts a narrow band across each brick pier.
  const shadow=c.createLinearGradient(0,shoulder+8,0,shoulder+25);
  shadow.addColorStop(0,"#380f2099");shadow.addColorStop(1,"#380f2000");
  c.fillStyle=shadow;c.fillRect(x-spread,shoulder+8,spread*2,17);
  face(c,[[left,roof+21],[left+w*.19,roof+21],[left+w*.12,shoulder-17],[left,shoulder-7]],"#23112545");
  band(c,x-spread-3,bottom-4,spread*2+6,8,ivory);
}
function central(c:Context,cheat:boolean){
  const x=470;
  tower(c,x,410,146,820);
  for(let j=0;j<4;j++){
    const y=550-j*29, radius=26-j*3;
    for(let k=-2;k<=2;k++)fan(c,x+k*(radius*1.65),y,radius,j%2?jade:brick);
  }
  // The arched belfry gives the chief tower a readable center below its tiers.
  for(const offset of [-1,0,1]){
    const px=x+offset*36;
    arch(c,px,606+Math.abs(offset)*4,offset===0?19:12,46,ivory);
  }
  band(c,x-62,658,124,7,jade);
  for(let i=0;i<8;i++){
    const a=404+i*16;
    face(c,[[454+i*4,248],[a,407],[a+16.4,407],[458+i*4,248]],horizontal(c,a,20,brick),"#ddb257",.65);
    for(let k=2;k<16;k+=3){
      const t=k/16;
      const px=(454+i*4)*(1-t)+(a+3)*t,py=248+159*t;
      ellipse(c,px,py,1+t*.8,1.5+t*.8,"#eebd61");
      if(k%3===0){
        face(c,[[px+3,py-3],[px+5+t,py],[px+3,py+3],[px+1,py]],"#812c25","#ffd784",.65);
      }
    }
  }
  for(let i=-3;i<=3;i++){
    const px=x+i*16;
    face(c,[[px-10,408],[px,372+Math.abs(i)*4],[px+10,408]],jade[1],ivory[2],1.7);
    fan(c,px,405,7,brick);
  }
  band(c,388,409,157,7,jade);band(c,394,416,145,6,ivory);
  c.fillStyle=horizontal(c,451,38,brick);c.fillRect(451,182,38,68);
  for(const y of [185,194,202,239,248])band(c,449,y,42,3,ivory);
  for(const dx of [-12,0,12])arch(c,x+dx,226,6,10,ivory);
  onion(c,x,183,31,72,55,cheat?"cheat":"gold");
}
function porch(c:Context,x:number,y:number,w:number,h:number){
  face(c,[[x-w/2,y],[x,y-h],[x+w/2,y]],horizontal(c,x-w/2,w,jade),ivory[2],2);
  for(const dx of [-.27,.18])face(c,[[x,y-h],[x+w*dx,y],[x+w*dx+3,y]],ivory[2]);
  band(c,x-w/2-2,y,w+4,5,jade);
}
function gallery(c:Context){
  const left=117,width=647;
  c.fillStyle=horizontal(c,left,width,brick);c.fillRect(left,833,width,173);
  for(let i=0;i<33;i++){
    const x=left+10+i*19.4;
    arch(c,x,883,10,22,ivory);
    if(i%2===0)arch(c,x,943,12,53,ivory);
  }
  for(const y of [847,876,910,919,1004])band(c,left-2,y,width+4,5,ivory);
  for(let i=0;i<31;i++)band(c,left+7+i*20.8,927,11,7,ivory);
  for(const x of [320,445,666])porch(c,x,875,166,43);
  for(const [x,y,w,h] of [[608,882,90,96],[558,901,111,101]]){
    c.fillStyle=horizontal(c,x-w/2,w,ivory);c.fillRect(x-w/2,y,w,1007-y);
    brickwork(c,x-w/2,y,w,1007-y);
    porch(c,x,y,w+4,h);
    const entry=y+32;
    for(const side of [-1,1])arch(c,x+side*w*.175,entry,w*.34,1003-entry,ivory);
    const stepY=entry+23;
    for(let j=0;j<8;j++){
      const sy=stepY+(1005-stepY)*j/8, sw=w*(.52+.021*j);
      band(c,x-sw/2,sy,sw,(1005-stepY)/8,["#3e2d2e","#95715a","#b9906d","#654e42"]);
    }
    for(const offset of [-.37,.37])band(c,x+w*offset-4,y+8,8,1000-y-8,ivory);
    for(const dy of [7,15,23])band(c,x-w/2,y+dy,w,2.5,ivory);
  }
}
export function drawSaintBasilsScene(c:Context,width:number,height:number,cheat=false){
  c.save();c.fillStyle="#000";c.fillRect(0,0,width,height);
  const scale=Math.min(width*.96/660,height*.83/954);
  c.translate(width/2-437*scale,height*.98-1009*scale);c.scale(scale,scale);
  central(c,cheat);
  porch(c,155,806,95,219);
  tower(c,225,603,100,832);onion(c,225,603,83,153,360,"green");
  tower(c,658,577,87,832);onion(c,658,577,61,121,372,"scales");
  tower(c,273,697,53,831,true);onion(c,273,697,42,87,548,"plaid");
  tower(c,360,600,94,832);onion(c,360,600,70,127,392,"blue");
  tower(c,539,684,71,832,true);onion(c,539,684,57,98,531,"net");
  gallery(c);drawForeground(c);c.restore();
}
