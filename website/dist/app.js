const track=document.querySelector('.track');
const slides=[...document.querySelectorAll('.slide')];
const tabs=[...document.querySelectorAll('[data-slide]')];
const dots=[...document.querySelectorAll('[data-go]')];
const hashes=['#problem','#metrics','#europe','#solution','#future','#demo','#story','#architecture'];
let current=0;
function show(index){
 current=Math.max(0,Math.min(slides.length-1,index));
 track.style.transform=`translateX(-${current*100}%)`;
 slides.forEach((s,i)=>{s.inert=i!==current;});
 [...tabs,...dots].forEach(b=>{const selected=Number(b.dataset.slide??b.dataset.go)===current;b.classList.toggle('active',selected);if(selected)b.setAttribute('aria-current','step');else b.removeAttribute('aria-current');});
 document.querySelector('#count').innerHTML=`0${current+1} <em>/ 0${slides.length}</em>`;
 history.replaceState(null,'',hashes[current]);
 requestAnimationFrame(()=>track.style.height=slides[current].offsetHeight+'px');
}
tabs.forEach(b=>b.addEventListener('click',()=>show(Number(b.dataset.slide))));
dots.forEach(b=>b.addEventListener('click',()=>show(Number(b.dataset.go))));
document.querySelector('.brand').addEventListener('click',e=>{e.preventDefault();show(0)});
document.addEventListener('keydown',e=>{if(e.altKey||e.ctrlKey||e.metaKey||e.target.closest('select,input,textarea,[data-country]'))return;if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();show(e.key==='Home'?0:e.key==='End'?slides.length-1:current+(e.key==='ArrowRight'?1:-1));}});
let start=null;const deck=document.querySelector('#deck');
deck.addEventListener('touchstart',e=>{if(e.target.closest('.map-canvas,.connection-game,select'))return;start={x:e.changedTouches[0].clientX,y:e.changedTouches[0].clientY}},{passive:true});
deck.addEventListener('touchend',e=>{if(!start)return;const dx=e.changedTouches[0].clientX-start.x,dy=e.changedTouches[0].clientY-start.y;if(Math.abs(dx)>60&&Math.abs(dx)>Math.abs(dy)*1.4)show(current+(dx<0?1:-1));start=null},{passive:true});
show(Math.max(0,hashes.indexOf(location.hash)));
window.addEventListener('load',()=>window.scrollTo(0,0));

const slideObserver=new ResizeObserver(()=>{track.style.height=slides[current].offsetHeight+'px';});slides.forEach(s=>slideObserver.observe(s));
