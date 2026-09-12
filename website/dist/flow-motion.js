(() => {
  const slide = document.querySelector('#slide-solution');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  let playing = !motion.matches;
  let ready = false;
  const sequences = [...slide.querySelectorAll('.flow-sequence')].map(element => ({
    element,
    frames:[...element.querySelectorAll('.flow-frame')],
    dots:[...element.querySelectorAll('.flow-frame-dots i')],
    durations:element.dataset.durations.split(',').map(Number),
    index:0,
    timer:null
  }));
  function paint(sequence) {
    sequence.frames.forEach((frame,i) => {
      frame.classList.toggle('is-active',i === sequence.index);
      frame.setAttribute('aria-hidden',String(i !== sequence.index));
      sequence.dots[i].classList.toggle('current',i === sequence.index);
    });
  }
  function schedule(sequence) {
    clearTimeout(sequence.timer);
    sequence.timer = null;
    if (!ready || !playing || document.hidden || slide.inert) return;
    sequence.timer = setTimeout(() => {
      sequence.index = (sequence.index+1)%sequence.frames.length;
      paint(sequence);
      schedule(sequence);
    },sequence.durations[sequence.index]);
  }
  function sync() {
    sequences.forEach(schedule);
  }
  new MutationObserver(sync).observe(slide,{attributes:true,attributeFilter:['inert']});
  document.addEventListener('visibilitychange',sync);
  motion.addEventListener('change',() => { playing=!motion.matches; sync(); });
  const sources=[...new Set([...slide.querySelectorAll('.flow-frame img')].map(img=>img.getAttribute('src')))];
  Promise.all(sources.map(src=>new Promise(resolve=>{
    const image=new Image();image.onload=()=>resolve(true);image.onerror=()=>resolve(false);image.src=src;
  }))).then(loaded=>{
    ready=loaded.every(Boolean);
    if(!ready){playing=false;return;}
    sync();
  });
  sync();
})();
