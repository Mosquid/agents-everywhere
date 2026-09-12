(() => {
 const slide=document.querySelector('#slide-architecture'), flow=slide.querySelector('.arch-flow');
 const nodes=Object.fromEntries([...flow.querySelectorAll('[data-arch-node]')].map(n=>[n.dataset.archNode,n]));
 const ns='http://www.w3.org/2000/svg', svg=document.createElementNS(ns,'svg');
 svg.classList.add('arch-connections');svg.setAttribute('aria-hidden','true');flow.prepend(svg);
 const edges=[['phone','livekit'],['browser','livekit'],['livekit','agent'],['agent','context'],['agent','openai']];
 const paths=edges.map(([a,b])=>{const p=document.createElementNS(ns,'path');p.dataset.from=a;p.dataset.to=b;svg.append(p);return p;});
 const dot=document.createElementNS(ns,'circle');dot.setAttribute('r','4');dot.classList.add('arch-packet');svg.append(dot);
 const motion=matchMedia('(prefers-reduced-motion: reduce)');let frame=null,start=0,step=0,browser=false;
 const sequence=()=>[[browser?'browser':'phone','livekit'],['livekit','agent'],['agent','context'],['context','agent'],['agent','openai'],['openai','agent'],['agent','livekit'],['livekit',browser?'browser':'phone']];
 function layout(){
  const base=flow.getBoundingClientRect();svg.setAttribute('viewBox',`0 0 ${base.width} ${base.height}`);
  paths.forEach((p,i)=>{const [a,b]=edges[i],r=nodes[a].getBoundingClientRect(),t=nodes[b].getBoundingClientRect();
   let x1,y1,x2,y2;
   if(a==='agent'&&b==='context'||innerWidth<=760){x1=r.left+r.width/2-base.left;y1=r.bottom-base.top;x2=t.left+t.width/2-base.left;y2=t.top-base.top;const mid=(y1+y2)/2;p.setAttribute('d',`M${x1} ${y1} C${x1} ${mid},${x2} ${mid},${x2} ${y2}`);}
   else{x1=r.right-base.left;y1=r.top+r.height/2-base.top;x2=t.left-base.left;y2=t.top+t.height/2-base.top;const mid=(x1+x2)/2;p.setAttribute('d',`M${x1} ${y1} C${mid} ${y1},${mid} ${y2},${x2} ${y2}`);}
  });
 }
 function tick(now){
  if(!start)start=now;let progress=(now-start)/950;
  if(progress>=1){step++;if(step===8){step=0;browser=!browser;}start=now;progress=0;}
  const [from,to]=sequence()[step];const p=paths.find(p=>p.dataset.from===from&&p.dataset.to===to||p.dataset.from===to&&p.dataset.to===from);
  paths.forEach(path=>path.classList.toggle('active',path===p));Object.entries(nodes).forEach(([id,n])=>n.classList.toggle('arch-active',id===from||id===to));
  const point=p.getPointAtLength(p.getTotalLength()*(p.dataset.from===from?progress:1-progress));dot.setAttribute('cx',point.x);dot.setAttribute('cy',point.y);frame=requestAnimationFrame(tick);
 }
 function sync(){cancelAnimationFrame(frame);frame=null;start=0;dot.style.display='none';paths.forEach(p=>p.classList.remove('active'));Object.values(nodes).forEach(n=>n.classList.remove('arch-active'));if(slide.inert||document.hidden||motion.matches)return;layout();dot.style.display='';frame=requestAnimationFrame(tick);}
 new ResizeObserver(layout).observe(flow);new MutationObserver(sync).observe(slide,{attributes:true,attributeFilter:['inert']});document.addEventListener('visibilitychange',sync);motion.addEventListener('change',sync);sync();
})();
