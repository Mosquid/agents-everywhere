const svg=document.querySelector('#europe-map');
const countrySelect=document.querySelector('#country-select');
const NS='http://www.w3.org/2000/svg';
const BASE_YEAR=2022,END_YEAR=2035;
// Deterministic pseudo-random demo rates; these are not country forecasts.
const scenarioCodes=EUROPE_DATA.filter(d=>d.lonely).map(d=>d.code).sort((a,b)=>{
 const rank=code=>((code.charCodeAt(0)*31+code.charCodeAt(1))*7919)%104729;
 return rank(a)-rank(b)||a.localeCompare(b);
});
const annualChanges=new Map(scenarioCodes.map((code,i)=>[code,0.10+i*0.015]));
let selected='ES',year=BASE_YEAR,playback=null,autoPending=false;
const loneColors=['#f6dccd','#eeba9d','#da976e','#bc7045','#93441f'];
const byCode=new Map(EUROPE_DATA.map(d=>[d.code,d]));
const delta=d=>Math.round((year-BASE_YEAR)*(annualChanges.get(d.code)??0)*10)/10;
const format=v=>Number(v.toFixed(1)).toString();
function estimate(d){return d.lonely?d.lonely[1]+delta(d):null;}
function rangeLabel(d){return d.lonely?d.lonely[0].replace(/\d+(?:\.\d+)?/g,n=>format(Number(n)+delta(d))):null;}
function color(d){const v=estimate(d);return v==null?'#e1e2e9':loneColors[[10,13,14,17].filter(x=>v>=x).length];}
for(const d of [...EUROPE_DATA].sort((a,b)=>a.name.localeCompare(b.name))){const o=document.createElement('option');o.value=d.code;o.textContent=d.name;countrySelect.append(o);}
const countries=document.createElementNS(NS,'g');countries.setAttribute('class','countries');svg.append(countries);
const bubbles=document.createElementNS(NS,'g');bubbles.setAttribute('class','bubbles');svg.append(bubbles);
const bubbleNodes=new Map();
for(const d of EUROPE_DATA){
 const p=document.createElementNS(NS,'path');p.setAttribute('d',d.path);p.setAttribute('data-country',d.code);p.setAttribute('role','button');p.setAttribute('tabindex','0');p.setAttribute('aria-label',d.name);p.append(document.createElementNS(NS,'title'));p.addEventListener('click',()=>choose(d.code));p.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(d.code);}});countries.append(p);
 if(d.lonely&&d.lonely[1]>=14){const g=document.createElementNS(NS,'g');g.setAttribute('class','map-bubble');g.setAttribute('transform',`translate(${d.x} ${d.y})`);g.setAttribute('aria-hidden','true');const c=document.createElementNS(NS,'circle');const t=document.createElementNS(NS,'text');t.setAttribute('text-anchor','middle');t.setAttribute('dy','.35em');g.append(c,t);bubbles.append(g);bubbleNodes.set(d.code,{c,t});}
}
const dot=document.createElementNS(NS,'circle');dot.setAttribute('r','5');dot.setAttribute('class','selected-point');bubbles.append(dot);
function choose(code){selected=code;render();}
function stop(){clearInterval(playback);playback=null;}
function render(){
 const data=byCode.get(selected),scenario=year>BASE_YEAR;countrySelect.value=selected;
 countries.querySelectorAll('path').forEach(p=>{const d=byCode.get(p.dataset.country),label=rangeLabel(d);p.style.fill=color(d);p.classList.toggle('chosen',d.code===selected);const description=`${d.name}: ${label==null?'No value included':label+'% frequently lonely'} · ${year}${scenario?' illustrative scenario':' survey'}`;p.setAttribute('aria-label',description);p.querySelector('title').textContent=description;});
 for(const [code,node] of bubbleNodes){const d=byCode.get(code);node.c.setAttribute('r',String((d.lonely[1]>=17?28:24)+delta(d)*1.4));node.t.textContent=year>BASE_YEAR&&d.lonely[0].includes('–')?'≈'+Math.round(estimate(d))+'%':rangeLabel(d)+'%';}
 dot.setAttribute('cx',data.x);dot.setAttribute('cy',data.y);
 const v=rangeLabel(data);document.querySelector('#country-value').replaceChildren(document.createTextNode(v??'—'));if(v!=null){const unit=document.createElement('span');unit.textContent='%';document.querySelector('#country-value').append(unit);}
 document.querySelector('#map-source').href='https://joint-research-centre.ec.europa.eu/scientific-activities/survey-methods-and-analysis-centre/loneliness/loneliness-prevalence-eu_en';
 document.querySelector('#map-source').textContent=scenario?'JRC 2022 baseline · simulated country growth ↗':'JRC survey · 2022 ↗';
 document.querySelector('#legend-title').textContent='Frequent loneliness · ages 16+';
 document.querySelector('#legend-items').innerHTML=['<10%','10–13%','13–14%','14–17%','17%+'].map((l,i)=>`<span><i style="background:${loneColors[i]}"></i>${l}</span>`).join('')+'<span><i style="background:#e1e2e9"></i>No data</span>';
 for(const code of ['FR','SE','PT','IT','PL'])document.querySelector('#comparison-'+code.toLowerCase()).textContent=rangeLabel(byCode.get(code))+'%';
 document.querySelector('#projection-year').textContent=year;
 document.querySelector('#projection-year').setAttribute('aria-label',year+(scenario?' illustrative scenario':' observed survey'));
 document.querySelector('#projection-year').title=scenario?`Illustrative scenario: +${(annualChanges.get(selected)??0).toFixed(3)} percentage points/year; simulated, not a forecast`:'2022 survey baseline';
}
function startAnimation(reset=false){
 stop();if(reset||year===END_YEAR)year=BASE_YEAR;render();
 if(document.hidden){autoPending=true;return;}
 autoPending=false;
 playback=setInterval(()=>{if(document.querySelector('#slide-europe').inert){stop();return;}year=year===END_YEAR?BASE_YEAR:year+1;render();},350);
}
countrySelect.addEventListener('change',()=>choose(countrySelect.value));
new MutationObserver(()=>{if(document.querySelector('#slide-europe').inert){autoPending=false;stop();}else startAnimation(true);}).observe(document.querySelector('#slide-europe'),{attributes:true,attributeFilter:['inert']});
document.addEventListener('visibilitychange',()=>{if(document.hidden){autoPending=Boolean(playback);stop();}else if(autoPending&&!document.querySelector('#slide-europe').inert)startAnimation();});
render();if(!document.querySelector('#slide-europe').inert)startAnimation(true);
