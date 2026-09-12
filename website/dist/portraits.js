(() => {
  const slide = document.querySelector('#slide-problem');
  const journey = document.querySelector('.connection-journey');
  const buttons = [...journey.querySelectorAll('[data-connection]')];
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  let timer;
  let entered = false;
  function setMoment(moment) {
    clearTimeout(timer);
    journey.classList.toggle('connected', moment === 'after');
    buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.connection === moment)));
  }
  function sync() {
    if (slide.inert || document.hidden) {
      clearTimeout(timer);
      entered = false;
      return;
    }
    if (entered) return;
    entered = true;
    setMoment('before');
    if (!reducedMotion.matches) timer = setTimeout(() => setMoment('after'), 3500);
  }
  buttons.forEach(button => button.addEventListener('click', () => setMoment(button.dataset.connection)));
  new MutationObserver(sync).observe(slide, { attributes: true, attributeFilter: ['inert'] });
  document.addEventListener('visibilitychange', sync);
  reducedMotion.addEventListener('change', () => { clearTimeout(timer); });
  const portraits = new Image();
  portraits.onload = sync;
  portraits.src = 'assets/connection-portraits.png';
})();
