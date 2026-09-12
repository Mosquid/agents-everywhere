(() => {
  const slide = document.querySelector('#slide-problem');
  const game = document.querySelector('.connection-game');
  const agent = game.querySelector('.phone-agent');
  const buttons = [...game.querySelectorAll('[data-person]')];
  const paths = [...game.querySelectorAll('[data-call-path]')];
  const steps = [...game.querySelectorAll('[data-story-step]')];
  const speaker = document.querySelector('#story-speaker');
  const message = document.querySelector('#story-message');
  const family = document.querySelector('#family-update');
  const support = document.querySelector('#support-update');
  const motion = matchMedia('(prefers-reduced-motion: reduce)');
  const people = [
    {name:'Carmen',question:'Carmen, how has your week been?',reply:'I miss my daughter. I’d love to tell her about my garden.',connection:'A familiar story. A reason to reconnect.',update:'Carmen: garden catch-up.'},
    {name:'Luis',question:'Luis, is there anything you’d like help with?',reply:'Getting out is harder lately. Could someone check in?',connection:'Luis has been heard. Support can follow.',update:'Luis: check-in requested.',help:true},
    {name:'Lucía',question:'Lucía, what would make this week a little better?',reply:'I’ve been studying alone. Coffee with a friend would be nice.',connection:'A small plan. Something to look forward to.',update:'Lucía: coffee catch-up.'},
    {name:'Alex',question:'Alex, shall we catch up on your week?',reply:'Working from home gets lonely. I’d love to hear from my brother.',connection:'One conversation opens the door to another.',update:'Alex: call from his brother.'},
    {name:'Amir',question:'Amir, how are you settling into your new city?',reply:'I’m still finding my feet. It helps to have someone to talk to.',connection:'New city. A growing circle of connection.',update:'Amir: meet local people.'}
  ];
  const durations = [500,950,1100,800,1200];
  const connected = new Set();
  let person = 0, phase = 0, timer = null, ready = false;
  let wantsPlay = !motion.matches;
  function clear() { clearTimeout(timer); timer = null; }
  function active() { return ready && wantsPlay && !slide.inert && !document.hidden; }
  function render() {
    const p = people[person];
    if (phase >= 3) connected.add(person);
    game.dataset.phase = String(phase);
    agent.style.left = `${phase === 0 || phase === 4 ? 50 : 14 + person * 18}%`;
    agent.style.top = phase === 0 || phase === 4 ? '23%' : '39%';
    agent.classList.toggle('talking', phase === 1 || phase === 2);
    buttons.forEach((button,i) => {
      button.classList.toggle('is-connected', connected.has(i));
      button.classList.toggle('is-calling', i === person && phase < 4);
      button.setAttribute('aria-pressed', String(i === person));
      const mood = connected.has(i) ? 'More connected' : i === person && phase > 0 && phase < 3 ? 'On a call' : 'Feeling alone';
      button.querySelector('.person-mood').textContent = mood;
      button.setAttribute('aria-label', `Call ${people[i].name}: ${mood}`);
    });
    paths.forEach((path,i) => path.classList.toggle('active', i === person && phase < 4));
    steps.forEach((step,i) => step.classList.toggle('active', i === (phase === 0 ? 0 : phase <= 2 ? 1 : phase === 3 ? 2 : 3)));
    game.classList.toggle('sharing-family', phase === 4);
    game.classList.toggle('sharing-support', phase === 4 && Boolean(p.help));
    if (phase === 0) { speaker.textContent='HOLA AGENT'; message.textContent=`A friendly call is on its way to ${p.name}.`; }
    if (phase === 1) { speaker.textContent='HOLA AGENT'; message.textContent=p.question; }
    if (phase === 2) { speaker.textContent=p.name.toUpperCase(); message.textContent=`“${p.reply}”`; }
    if (phase === 3) { speaker.textContent='A MOMENT OF CONNECTION'; message.textContent=p.connection; }
    if (phase === 4) {
      speaker.textContent='SHARED WITH PERMISSION';
      message.textContent=p.help ? 'Luis’s check-in request shared.' : 'Approved update shared.';
      family.textContent=p.update;
      if (p.help) support.textContent='Luis: check-in requested.';
    }
  }
  function schedule() {
    clear();
    if (!active()) return;
    timer=setTimeout(() => {
      if (phase < 4) phase++;
      else {
        phase=0; person=(person+1)%people.length;
        if (person === 0) { connected.clear(); family.textContent='Awaiting updates'; support.textContent='Here when needed'; }
      }
      render(); schedule();
    }, durations[phase]);
  }
  buttons.forEach((button,i) => button.addEventListener('click', () => {
    person=i; phase=0; connected.delete(i); wantsPlay=true; render(); schedule();
  }));
  new MutationObserver(schedule).observe(slide,{attributes:true,attributeFilter:['inert']});
  document.addEventListener('visibilitychange',schedule);
  motion.addEventListener('change', () => { if (motion.matches) wantsPlay=false; render(); schedule(); });
  const image = new Image();
  image.onload=() => { ready=true; render(); schedule(); };
  image.src='assets/connection-characters.png';
  render();
})();
