(() => {
  const slide=document.querySelector('#slide-demo');
  const poster=slide.querySelector('.demo-poster');
  const scenes=[...poster.querySelectorAll('.demo-scene')];
  const motion=matchMedia('(prefers-reduced-motion: reduce)');
  const people=[{label:'Older adult',contact:'Relative',share:true},{label:'Young adult',contact:'Trusted contact',share:false},{label:'New to Spain',contact:'Social worker',share:true}];
  let index=0,stage=0,playing=!motion.matches,ready=false,timer=null;
  function paint(){
    const person=people[index];
    scenes.forEach((image,i)=>{image.classList.toggle('current',i===index);image.setAttribute('aria-hidden',String(i!==index));});
    poster.dataset.stage=String(stage);poster.dataset.share=String(person.share);
    poster.classList.toggle('demo-paused',!playing||slide.inert||document.hidden);
    document.querySelector('#demo-person-label').textContent=person.label;
    document.querySelector('#demo-contact-label').textContent=person.contact;
    const social=poster.querySelector('.demo-social-contact');
    social.classList.toggle('current',index===2);
    social.setAttribute('aria-hidden',String(index!==2));
  }
  function schedule(){
    clearTimeout(timer);timer=null;paint();
    if(!ready||!playing||slide.inert||document.hidden)return;
    timer=setTimeout(()=>{index=(index+1)%scenes.length;stage=(stage+1)%4;schedule();},800);
  }
  new MutationObserver(schedule).observe(slide,{attributes:true,attributeFilter:['inert']});
  document.addEventListener('visibilitychange',schedule);
  motion.addEventListener('change',()=>{playing=!motion.matches;schedule();});
  Promise.all([...scenes,poster.querySelector('.demo-social-contact')].map(scene=>new Promise(resolve=>{const image=new Image();image.onload=()=>resolve(true);image.onerror=()=>resolve(false);image.src=scene.getAttribute('src');}))).then(results=>{ready=results.every(Boolean);if(!ready){playing=false;}schedule();});
  paint();
})();
