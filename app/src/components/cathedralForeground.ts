// Foreground drawn in the same photograph coordinates as the cathedral.
// Small silhouette paths keep the hands, drapery and overlapping figures legible.
type Ctx = CanvasRenderingContext2D;

function silhouette(c: Ctx, data: string, fill: string | CanvasGradient, outline?: string) {
  const path = new Path2D(data);
  c.fillStyle = fill;
  c.fill(path);
  if (outline) { c.strokeStyle = outline; c.lineWidth = .75; c.stroke(path); }
}

function bronze(c: Ctx, left: number, width: number) {
  const g = c.createLinearGradient(left, 0, left + width, 0);
  g.addColorStop(0, "#132f30"); g.addColorStop(.32, "#286359");
  g.addColorStop(.62, "#82ab85"); g.addColorStop(.82, "#446f58"); g.addColorStop(1, "#172e31");
  return g;
}

function monument(c: Ctx) {
  c.save();
  c.translate(319, 803);
  // Sloping stone plinth, inset relief panel and stepped base.
  silhouette(c, "M-24 135 L108 135 L123 207 L-34 207Z", "#8c4534");
  for (const [y,w,h,col] of [[132,137,6,"#cf8858"],[139,131,3,"#572e28"],[183,147,4,"#b37650"],[193,151,4,"#5e382c"],[203,158,5,"#c28762"]] as const) {
    c.fillStyle=col; c.fillRect(42-w/2,y,w,h);
  }
  c.fillStyle="#d19b6e"; c.fillRect(-4,148,93,31);
  c.fillStyle="#483b31"; c.fillRect(-2,150,89,27);
  for(let i=0;i<13;i++){
    const x=i*6.25+1, y=159+Math.sin(i*2.7)*2;
    silhouette(c,`M${x} 171 q1 -10 3 -10 q2 -7 4 0 l2 10z`,i%2?"#846e49":"#69715a");
    c.beginPath();c.arc(x+4,y,1.8,0,Math.PI*2);c.fill();
  }
  silhouette(c,"M-17 129 L-11 123 L94 123 L105 129 L109 134 L-22 134Z",bronze(c,-22,131));
  // Standing figure: backward leg, extended arm and hand, face, mantle, forward leg.
  silhouette(c,"M11 65 Q8 85 11 94 L7 119 L2 122 Q-1 126 9 125 L15 123 L20 95 L24 69Z",bronze(c,6,20));
  silhouette(c,"M15 36 Q8 33 3 29 L-8 21 L-19 13 L-24 8 L-28 8 L-25 12 L-31 10 L-32 12 L-26 16 L-20 18 Q-8 32 3 39 L12 45Z",bronze(c,-26,41),"#a1ad80");
  silhouette(c,"M13 28 Q11 27 9 23 L10 17 Q10 12 16 11 Q22 10 24 15 L25 19 L27 21 L24 22 L24 27 L20 28 L21 33 L14 35Z",bronze(c,9,17));
  silhouette(c,"M10 19 Q8 11 15 9 Q21 7 25 14 L22 16 L17 14 L14 19Z","#28473e");
  silhouette(c,"M13 30 Q22 27 28 35 L31 48 L34 60 L42 65 L40 70 Q30 68 26 62 L22 54 L27 74 L30 89 Q15 95 7 85 L10 69 L8 52Z",bronze(c,8,25),"#a0a982");
  silhouette(c,"M23 82 L29 85 L27 98 L31 118 L39 122 Q42 125 34 125 L26 124 L20 101 L18 91Z",bronze(c,18,17));
  silhouette(c,"M12 39 Q11 59 22 71 L16 67 L12 80 L13 61 L10 53Z","#164640");
  silhouette(c,"M23 40 Q17 59 25 78 L20 70 Q16 59 23 40Z","#98af81");
  // Seated figure, bent knee, shield rim and hand resting on the shield.
  silhouette(c,"M35 103 L79 97 L87 121 L39 123Z","#243d38");
  silhouette(c,"M55 60 Q53 54 57 49 Q62 44 68 49 L70 56 L68 60 L70 65 L59 68Z",bronze(c,54,16));
  silhouette(c,"M55 55 Q52 49 58 46 Q66 43 70 50 L68 53 L64 50Z","#26453c");
  silhouette(c,"M58 64 Q68 58 75 69 L81 86 L87 97 L83 102 Q75 96 70 81 L69 92 Q70 102 79 111 L72 116 L53 104 L44 102 L30 111 L20 110 L19 106 L34 92 L49 85Z",bronze(c,30,54),"#91a881");
  silhouette(c,"M60 68 Q55 83 49 89 Q40 91 34 84 L34 78 L38 79 L41 84 L47 82 L53 69Z",bronze(c,34,26));
  silhouette(c,"M55 94 Q44 95 34 106 L43 104 L55 102 L69 111Z","#aec09a");
  silhouette(c,"M71 114 L64 118 L48 119 L45 123 L66 123 L78 118Z",bronze(c,45,31));
  c.save();c.translate(85,107);c.rotate(-.43);
  for(const [rx,ry,col] of [[12,17,"#acb18c"],[10,15,"#355847"],[7.5,12,"#7b9876"],[6,10,"#3b6152"]] as const){
    c.fillStyle=col;c.beginPath();c.ellipse(0,0,rx,ry,0,0,2*Math.PI);c.fill();
  }
  c.restore();c.restore();
}

function shrub(c: Ctx,x:number,y:number,r:number,seed:number){
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  // Reproducible clusters: shadow mass first, then small sun-facing leaf pairs.
  for(let i=0;i<25;i++){
    const angle=random()*Math.PI*2,rad=Math.sqrt(random());
    const px=x+Math.cos(angle)*r*.74*rad, py=y+Math.sin(angle)*r*.67*rad;
    const size=r*(.13+random()*.23);
    const g=c.createRadialGradient(px+size*.25,py-size*.45,0,px,py,size);
    g.addColorStop(0,"#4e9960");g.addColorStop(.6,"#287144");g.addColorStop(1,"#102a2c");
    c.fillStyle=g;c.beginPath();c.arc(px,py,size,0,2*Math.PI);c.fill();
    for(let j=0;j<3;j++){
      const ax=px+(random()-.5)*size*1.2,ay=py-random()*size*.68;
      c.fillStyle=j%4?"#53904b":"#8ba953";
      c.beginPath();c.ellipse(ax,ay,.9+random()*1.25,.65,-.5,0,Math.PI*2);c.fill();
    }
  }
}

export function drawForeground(c:Ctx){
  shrub(c,158,946,55,17);shrub(c,214,971,42,31);shrub(c,271,981,30,53);shrub(c,468,977,29,73);
  monument(c);
}
