const $ = (id) => document.getElementById(id);
const viewNames = ['overview','forecast','live','sensors','sites','alerts','reports','integrations','settings'];
const requestedView = new URLSearchParams(location.search).get('view');
const state = {scenarios: [], scenario: 'freezer_rebound', minute: 82, seed: 17, reveal: false, fault: false, data: null, timer: null, hardware: null, chartManual:false, view:viewNames.includes(requestedView)?requestedView:'forecast'};
const labels = {temperature_c:'Temperature',humidity_pct:'Humidity',pressure_pa:'Pressure',gas_resistance_ohm:'BME680 gas resistance',mq135_adc_raw:'MQ-135 raw ADC'};
const units = {temperature_c:'°C',humidity_pct:'%',pressure_pa:'Pa',gas_resistance_ohm:'Ω',mq135_adc_raw:'raw'};
const roomThemes = {
  'Cold storage': {asset:'mountains.png',alt:'Snowy mountain illustration',icon:'i-snow',brand:'COLD CHAIN. A SAFER TOMORROW.',foot:'COLD DATA.\nBRIGHTER DAYS.',motto:'KEEP IT COLD. KEEP PEOPLE SAFE.'},
  'Laboratory': {asset:'laboratory.png',alt:'Research laboratory illustration',icon:'i-flask',brand:'LAB INSIGHT. EARLIER ACTION.',foot:'CLEAR SIGNALS.\nSAFER LABS.',motto:'WATCH THE PROCESS. SEE THE CHANGE.'},
  'Classroom': {asset:'classroom.png',alt:'Classroom illustration',icon:'i-book',brand:'LEARNING SPACES. EARLIER ACTION.',foot:'ROOM DATA.\nBETTER LEARNING.',motto:'HEALTHIER ROOMS. BETTER LEARNING.'},
  'Bakery': {asset:'bakery.png',alt:'Commercial bakery illustration',icon:'i-wheat',brand:'BAKERY CONDITIONS. EARLIER ACTION.',foot:'WARM SPACES.\nCLEAR SIGNALS.',motto:'READ THE HEAT. ACT EARLY.'},
  'Server room': {asset:'server-room.png',alt:'Data center illustration',icon:'i-server',brand:'THERMAL MONITORING. EARLIER ACTION.',foot:'COOL SYSTEMS.\nCLEAR SIGNALS.',motto:'PROTECT THE THERMAL MARGIN.'},
};
const round = (value, channel) => channel === 'temperature_c' || channel === 'humidity_pct' ? Number(value).toFixed(1) : Math.round(value).toLocaleString();
const idx = (channel) => state.data.channels.indexOf(channel);
const value = (values, channel) => values[idx(channel)];
const currentBreach = (d) => Object.entries(d.limits).find(([channel,[low,high]]) => {
  const reading = value(d.current,channel);
  return reading < low || reading > high;
})?.[0] || null;
const revealedOutcome = (d) => {
  if (!d.truth_revealed) return null;
  const actual = Boolean(currentBreach(d) || d.actual_breach);
  if (d.breach && !actual) return 'false-alert';
  if (!d.breach && !actual) return 'correct-no-alert';
  if (!d.breach && actual) return 'missed-breach';
  return 'alert-with-breach';
};
const clamp = (n, a, b) => Math.max(a, Math.min(b, n));

async function loadScenarios() {
  const response = await fetch('/api/v1/forecast/scenarios');
  if (!response.ok) throw new Error('Scenario list unavailable');
  state.scenarios = (await response.json()).scenarios;
  $('scenario-select').replaceChildren(...state.scenarios.map(s => {
    const option = document.createElement('option');
    option.value = s.key;
    option.textContent = `${s.room} · ${s.title}`;
    return option;
  }));
  $('scenario-select').value = state.scenario;
  await loadEpisode();
}

async function loadEpisode() {
  const query = new URLSearchParams({scenario:state.scenario, minute:state.minute, seed:state.seed, reveal:state.reveal});
  const response = await fetch(`/api/v1/forecast/episode?${query}`);
  if (!response.ok) throw new Error((await response.json()).detail || 'Forecast unavailable');
  state.data = await response.json();
  state.hardware = null;
  render();
}

function text(id, content) { $(id).textContent = content; }
function render() {
  const d = state.data;
  if (!d) return;
  document.body.dataset.room = d.scenario.room;
  const theme=roomThemes[d.scenario.room];
  $('room-art').src=`/forecast-assets/assets/${theme.asset}`;
  $('room-art').alt=theme.alt;
  text('brand-tagline',theme.brand);
  text('sidebar-tagline',theme.foot);
  text('room-motto',theme.motto);
  $('room-select-icon').setAttribute('href',`#${theme.icon}`);
  $('tx-room-icon').setAttribute('href',`#${theme.icon}`);
  text('top-room',d.scenario.room);
  text('top-time',`Synthetic episode · minute ${d.minute}`);
  text('scenario-title',d.scenario.title);
  text('scenario-story',d.scenario.story);
  text('scenario-clock',`Minute ${d.minute} of 151`);
  const current = d.current;
  const future = d.forecast[d.forecast.length - 1];
  const tempLimits = d.limits.temperature_c;
  const temp = value(current,'temperature_c');
  const futureTemp = value(future,'temperature_c');
  const currentInRange = !currentBreach(d);
  text('current-temp',`${round(temp,'temperature_c')} °C`);
  text('current-range',`${tempLimits[0]} to ${tempLimits[1]} °C`);
  text('current-humidity',`${round(value(current,'humidity_pct'),'humidity_pct')}%`);
  text('current-pressure',`${round(value(current,'pressure_pa'),'pressure_pa')} Pa`);
  text('current-gas',`${round(value(current,'gas_resistance_ohm'),'gas_resistance_ohm')} Ω`);
  text('current-mq',`${round(value(current,'mq135_adc_raw'),'mq135_adc_raw')} raw`);
  text('current-state',currentInRange?'WITHIN RANGE':'OUTSIDE RANGE');
  $('current-state').className=`state-pill ${currentInRange?'':'danger'}`;
  text('future-temp',`${round(futureTemp,'temperature_c')} °C`);
  text('future-temp-row',`${round(futureTemp,'temperature_c')} °C`);
  text('future-humidity',`${round(value(future,'humidity_pct'),'humidity_pct')}%`);
  text('breach-time',d.breach?`+${d.breach.at_minute} min`:'None in 30 min');
  text('breach-channel',d.breach?labels[d.breach.channel]:'No trigger');
  text('response-short','Temp · RH · BME gas');
  text('future-state',d.breach?'FORECAST ALERT':'NO BREACH');
  $('future-state').className=`state-pill ${d.breach?'danger':'neutral'}`;
  $('forecast-chart').classList.toggle('non-temperature',Boolean(d.breach&&d.breach.channel!=='temperature_c'));
  $('forecast-chart').classList.toggle('no-breach',!d.breach);
  $('future-temp').closest('.future-panel').classList.toggle('no-breach',!d.breach);
  $('future-temp').closest('.future-panel').classList.toggle('non-temperature-alert',Boolean(d.breach&&d.breach.channel!=='temperature_c'));
  if(!state.chartManual)$('chart-channel').value=d.breach?.channel||'temperature_c';
  $('alert-count').textContent=d.breach?'1':'0';
  renderRoute();
  renderChart();
  renderTimeline();
  renderStatus();
  renderDetails();
  renderWorkspace();
}

function renderRoute() {
  const d=state.data, alert=Boolean(d.breach), fault=state.fault;
  const hardware=state.hardware;
  text('route-source',hardware?'TWO-BOARD TX REPLAY':'SIMULATED DIRECT-LAPTOP ROUTE');
  text('wifi-label',hardware?'TX → RX ESP32':fault?'TX → laptop blocked':'TX → laptop');
  text('wifi-dest-name',hardware?'RX ESP32':'Laptop Wi-Fi');
  $('wifi-dest-icon').setAttribute('href',hardware?'#i-server':'#i-laptop');
  text('laptop-label',hardware?(hardware.rx_ack?'RX stored event':'RX receipt unconfirmed'):alert&&!fault?'Simulated receipt':'No physical receipt');
  text('bt-label',hardware?(hardware.bt_ack?'Laptop stored event':'BT receipt unconfirmed'):fault&&alert?'Simulated receipt':'No BT receipt');
  const routeEvent=hardware?`${hardware.event_id} · ${hardware.bt_ack?'Bluetooth stored on laptop':hardware.rx_ack?'RX ESP32 ACK received':'Hardware delivery unconfirmed'}`:alert?`${d.event_id} · ${fault?'Bluetooth-to-laptop receipt simulated':'Wi-Fi-to-laptop receipt simulated'}; physical delivery unverified`:'No alert event yet';
  text('route-event',routeEvent);
  $('route-event').title=routeEvent;
  $('communication-path').classList.toggle('wifi-broken',fault&&alert);
  $('communication-path').classList.toggle('fallback-active',fault&&alert);
}

function chartSvg() {
  const d=state.data, channel=$('chart-channel').value, i=idx(channel);
  const accent=getComputedStyle(document.body).getPropertyValue('--chart-accent').trim()||'#1189f3';
  const predicted=[d.current[i],...d.forecast.map(v=>v[i])];
  const actual=d.actual_future?[d.current[i],...d.actual_future.map(v=>v[i])]:null;
  const limits=d.limits[channel];
  const showLower=Boolean(d.breach?.channel===channel&&d.breach.direction==='below');
  const all=[...predicted,...(actual||[]),...(limits?[limits[showLower?0:1]]:[])];
  let lo=Math.min(...all),hi=Math.max(...all);
  const padding=(hi-lo || 1)*.18;
  lo-=padding;hi+=padding;
  const x=(t)=>52+t/30*737;
  const y=(v)=>198-(v-lo)/(hi-lo)*166;
  const pts=(arr)=>arr.map((v,n)=>`${x(n*5).toFixed(1)},${y(v).toFixed(1)}`).join(' ');
  const smooth=(arr)=>arr.slice(0,-1).reduce((path,_,n)=>{const x0=x(n*5),x1=x((n+1)*5),y0=y(arr[n]),y1=y(arr[n+1]);const prev=y(arr[Math.max(0,n-1)]),next=y(arr[Math.min(arr.length-1,n+2)]);return `${path} C ${(x0+(x1-x0)/3).toFixed(1)} ${(y0+(y1-prev)/6).toFixed(1)} ${(x1-(x1-x0)/3).toFixed(1)} ${(y1-(next-y0)/6).toFixed(1)} ${x1.toFixed(1)} ${y1.toFixed(1)}`;},`M ${x(0)} ${y(arr[0])}`);
  const levels=Array.from({length:5},(_,j)=>lo+(hi-lo)*j/4);
  const grid=levels.map(v=>`<line x1="52" x2="789" y1="${y(v)}" y2="${y(v)}" stroke="#d9e7f3" stroke-width="1"/><text x="43" y="${y(v)+3}" text-anchor="end">${round(v,channel)}</text>`).join('')
    + [0,5,10,15,20,25,30].map(t=>`<line x1="${x(t)}" x2="${x(t)}" y1="32" y2="198" stroke="#e6eff8"/><text x="${x(t)}" y="220" text-anchor="middle">${t}</text>`).join('');
  const boundary=limits?y(limits[showLower?0:1]):0;
  const band=limits?`<rect x="52" y="${showLower?32:boundary}" width="737" height="${Math.max(0,showLower?boundary-32:198-boundary)}" fill="#e7f6ff" opacity=".48"/><line x1="52" x2="789" y1="${boundary}" y2="${boundary}" stroke="#ef5d60" stroke-dasharray="8 5" stroke-width="1.4"/>`:'';
  const fill=`52,198 ${pts(predicted)} 789,198`;
  let breachMarker='';
  if(d.breach&&d.breach.channel===channel){const n=d.forecast_horizons.indexOf(d.breach.at_minute)+1;const bx=x(d.breach.at_minute),by=y(predicted[n]);breachMarker=`<circle cx="${bx}" cy="${by}" r="6" fill="white" stroke="#ef4e50" stroke-width="2"/><rect x="${clamp(bx-42,55,667)}" y="${clamp(by-55,35,139)}" width="122" height="37" rx="6" fill="#fff2f0" stroke="#ffb0a9"/><text x="${clamp(bx-35,62,674)}" y="${clamp(by-39,51,155)}" fill="#bb3333" font-weight="700">Predicted outside</text><text x="${clamp(bx-35,62,674)}" y="${clamp(by-25,65,169)}" fill="#bb3333">+${d.breach.at_minute} min sample</text>`;}
  const axisLabel=channel==='gas_resistance_ohm'?'Gas resistance':channel==='mq135_adc_raw'?'MQ-135 ADC':labels[channel];
  return `<svg viewBox="0 0 820 245" aria-label="${labels[channel]} 30 minute forecast"><defs><linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop stop-color="${accent}" stop-opacity=".22"/><stop offset="1" stop-color="${accent}" stop-opacity=".015"/></linearGradient></defs>${band}${grid}<polygon points="${fill}" fill="url(#area)"/><line x1="52" x2="789" y1="${y(predicted[0])}" y2="${y(predicted[0])}" stroke="#93aac2" stroke-dasharray="7 5" stroke-width="1.2"/><path d="${smooth(predicted)}" fill="none" stroke="${accent}" stroke-width="2.7" stroke-linecap="round" stroke-linejoin="round"/>${actual?`<polyline points="${pts(actual)}" fill="none" stroke="#7e8795" stroke-dasharray="4 4" stroke-width="2"/>`:''}${breachMarker}<text x="421" y="240" text-anchor="middle" class="axis-title">Time (minutes)</text><text transform="translate(10 120) rotate(-90)" text-anchor="middle" class="axis-title">${axisLabel} (${units[channel]})</text></svg>`;
}
function renderChart(){
  const d=state.data, channel=$('chart-channel').value;
  $('chart-heading').innerHTML=`${labels[channel]} Forecast <span>(Next 30 Minutes)</span>`;
  $('limit-legend').parentElement.hidden=!d.limits[channel];
  text('limit-legend',d.breach?.channel===channel&&d.breach.direction==='below'?'Demo lower limit':'Demo upper limit');
  $('chart').innerHTML=chartSvg();
  let comparison='';
  if(d.truth_revealed){
    const outcome=revealedOutcome(d);
    const predicted=d.breach?`Model +${d.breach.at_minute} min (${labels[d.breach.channel]})`:'Model: no breach';
    const alreadyOutside=currentBreach(d);
    const actual=alreadyOutside?`Simulator: already outside now (${labels[alreadyOutside]})`:d.actual_breach?`Simulator +${d.actual_breach.at_minute} min (${labels[d.actual_breach.channel]})`:'Simulator: no breach';
    const sameChannel=d.breach&&d.actual_breach&&d.breach.channel===d.actual_breach.channel;
    const delta=sameChannel&&!alreadyOutside&&d.actual_breach.at_minute>0?d.breach.at_minute-d.actual_breach.at_minute:null;
    const timing=delta===null?'':delta===0?' · same sampled minute':` · ${Math.abs(delta)} min ${delta>0?'late':'early'}`;
    comparison=outcome==='false-alert'?'FALSE ALERT · Simulator stayed within range':outcome==='correct-no-alert'?'CORRECT NO-ALERT · Simulator stayed within range':outcome==='missed-breach'?`MISSED BREACH · ${actual}`:`${predicted} · ${actual}${timing}`;
    $('truth-result').title=`${predicted} · ${actual}${timing}`;
  }
  text('truth-result',comparison);
}

function timelineItem(icon,kind,time,title,sub){const item=document.createElement('div');item.className='timeline-item';const image=document.createElement('span');image.className=`timeline-icon ${kind}`;image.innerHTML=`<svg><use href="#${icon}"/></svg>`;const timeEl=document.createElement('span');timeEl.className='timeline-time';timeEl.textContent=time;const copy=document.createElement('span');copy.className='timeline-copy';const strong=document.createElement('b');strong.textContent=title;const detail=document.createElement('span');detail.textContent=sub;copy.append(strong,detail);item.append(image,timeEl,copy);return item;}
function renderTimeline(){
  const d=state.data, alert=Boolean(d.breach), fault=state.fault, list=$('timeline');list.replaceChildren();
  if(state.hardware){const h=state.hardware;list.append(timelineItem('i-sensor',h.tx_persisted?'success':'warning','TX',h.tx_persisted?'Event persisted on TX':'TX persistence failed','Reported by the connected ESP32 TX.'),timelineItem('i-wifi',h.rx_ack?'success':'warning','Wi-Fi',h.rx_ack?'Exact-ID RX ACK received':'No exact-ID RX ACK','RX storage is separate from backend storage.'),timelineItem('i-bt',h.bt_ack?'success':'muted','Bluetooth',h.bt_ack?'Nearby laptop stored receipt':'Bluetooth receipt unconfirmed','Reported by TX after the receiver ACK.'));$('voice-button').disabled=!alert;return;}
  if(!alert){
    list.append(timelineItem('i-sensor','muted',`Minute ${d.minute}`,'Monitoring sensor trend','No forecast range crossing in the next 30 minutes.'),timelineItem('i-wifi','muted','Primary path','Wi-Fi to laptop on standby','No alert packet generated at this minute.'),timelineItem('i-bt','muted','Alternate','Bluetooth on standby','Fallback used only after a simulated Wi-Fi timeout.'));
  } else {
    list.append(timelineItem('i-alert','warning',`+${d.breach.at_minute} min`,`${labels[d.breach.channel]} forecast outside range`,'TinyML forecast meets the demo alert rule.'));
    if(fault){list.append(timelineItem('i-wifi','warning','Now','Wi-Fi to laptop blocked','Fault injected for this simulated episode.'),timelineItem('i-bt','','Now','Bluetooth to laptop selected','This fallback route is simulated.'),timelineItem('i-check','success','Now','Simulated laptop receipt','Physical delivery is unverified.'));}
    else{list.append(timelineItem('i-wifi','','Now','Wi-Fi to laptop selected','Primary alert path is simulated.'),timelineItem('i-check','success','Now','Simulated laptop receipt','Physical laptop storage is unverified.'));}
  }
  if(revealedOutcome(d)==='false-alert')list.append(timelineItem('i-alert','warning','Reveal','False alert in synthetic episode','Simulator stayed within the demo ranges.'));
  if(revealedOutcome(d)==='correct-no-alert')list.append(timelineItem('i-check','success','Reveal','No-breach control confirmed','Model and simulator stayed within range.'));
  $('voice-button').disabled=!alert;
}
function renderStatus(){
  const d=state.data,alert=Boolean(d.breach),fault=state.fault,b=$('status-banner');
  if(state.hardware){const h=state.hardware;b.className=`status-banner ${h.rx_ack||h.bt_ack?'':'warning'}`;text('status-title',h.bt_ack?'Bluetooth receiver stored event':h.rx_ack?'RX ESP32 stored event':'Hardware delivery unconfirmed');text('status-copy',`${h.event_id} · Legacy two-board replay · TX persisted: ${h.tx_persisted?'yes':'no'} · RX ACK: ${h.rx_ack?'yes':'no'} · Bluetooth receipt: ${h.bt_ack?'yes':'no'} · Backend storage unverified.`);return;}
  const outcome=revealedOutcome(d);
  b.className=`status-banner ${!alert?'info':fault||outcome==='false-alert'?'warning':''}`;
  if(outcome==='false-alert'){text('status-title','False alert in this synthetic episode');text('status-copy',`Model predicted a range crossing, but the revealed simulator future stayed within range. ${d.event_id} used a simulated route.`);}
  else if(outcome==='correct-no-alert'){text('status-title','No-breach control confirmed');text('status-copy','The model predicted no crossing and the revealed simulator future stayed within the demo ranges.');}
  else if(!alert){text('status-title','Monitoring in progress');text('status-copy','No 30-minute breach predicted. Reveal the simulator future to check this no-alert decision.');}
  else if(fault){text('status-title','Bluetooth fallback simulated');text('status-copy',`Wi-Fi to laptop timeout injected for ${d.event_id}. Bluetooth laptop receipt is simulated.`);}
  else{text('status-title','Primary alert delivery simulated');text('status-copy',`Wi-Fi to laptop receipt simulated for ${d.event_id}. Physical and backend storage are unverified.`);}
}
function renderDetails(){
  const d=state.data,host=$('details-body');host.replaceChildren();
  const route=state.hardware?'legacy two-board TX replay':!d.breach?'no alert packet generated':state.fault?'Bluetooth to laptop simulated after Wi-Fi timeout':'Wi-Fi to laptop receipt simulated';
  const lines=[`Scenario: ${d.scenario.room} · ${d.scenario.title}`,`Dataset: synthetic, held-out scenario family · episode seed ${d.seed}`,`Model input: 60 observed minutes, five channels, room type. Hidden future is excluded.`,`Forecast: ${d.breach?`${labels[d.breach.channel]} ${d.breach.direction} ${round(d.breach.limit,d.breach.channel)} ${units[d.breach.channel]} at first sampled point +${d.breach.at_minute} minutes`:'no configured range crossing at six five-minute forecast points'}.`,`Response: ${d.scenario.response}`,`Route: ${route}.`,`Event ID: ${d.event_id}`,`Limits are demonstration policy only. MQ-135 is raw ADC, not calibrated ppm. No real emergency service is contacted.`];
  if(d.truth_revealed){const alreadyOutside=currentBreach(d);lines.push(`Hidden simulator future: ${alreadyOutside?`already outside range now, ${labels[alreadyOutside]}`:d.actual_breach?`first outside at +${d.actual_breach.at_minute} min, ${labels[d.actual_breach.channel]}`:'no breach within 30 minutes'}.`);const outcome=revealedOutcome(d);if(outcome==='false-alert')lines.push('Evaluation: false alert. The simulator stayed within range.');if(outcome==='correct-no-alert')lines.push('Evaluation: correct no-alert control for this episode.');}
  if(state.hardware)lines.push(`Legacy TX hardware: NVS persisted ${state.hardware.tx_persisted}, RX ESP32 ACK ${state.hardware.rx_ack}, laptop Bluetooth receipt ${state.hardware.bt_ack}.`);
  lines.forEach(line=>{const p=document.createElement('p');p.textContent=line;host.append(p)});
}

const escapeHtml = (value) => String(value).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const reading = (channel, number) => `${round(number,channel)} ${units[channel]}`;
function channelBreach(channel) {
  const d=state.data, bounds=d.limits[channel];
  if(!bounds)return null;
  for(let i=0;i<d.forecast.length;i++){
    const predicted=value(d.forecast[i],channel);
    if(predicted<bounds[0]||predicted>bounds[1])return {minute:d.forecast_horizons[i],direction:predicted<bounds[0]?'below':'above'};
  }
  return null;
}
function policyRows() {
  const d=state.data;
  return d.channels.map(channel=>{
    const bounds=d.limits[channel],crossing=channelBreach(channel);
    const range=bounds?`${reading(channel,bounds[0])} to ${reading(channel,bounds[1])}`:'No alert bound';
    const status=!bounds?'Context only':crossing?`Forecast ${crossing.direction} bound at +${crossing.minute} min`:'No forecast crossing';
    return `<tr><th scope="row">${escapeHtml(labels[channel])}</th><td>${escapeHtml(reading(channel,value(d.current,channel)))}</td><td>${escapeHtml(reading(channel,value(d.forecast.at(-1),channel)))}</td><td>${escapeHtml(range)}</td><td><span class="table-status ${crossing?'bad':bounds?'good':'muted'}">${escapeHtml(status)}</span></td></tr>`;
  }).join('');
}
function workspaceMarkup(view) {
  const d=state.data, room=escapeHtml(d.scenario.room), title=escapeHtml(d.scenario.title), story=escapeHtml(d.scenario.story);
  const warning=d.breach?`${escapeHtml(labels[d.breach.channel])} may cross the configured demo range in about ${d.breach.at_minute} minutes.`:'No configured range crossing is forecast in the next 30 minutes.';
  if(view==='overview')return `<div class="workspace-intro"><strong>${room} · ${title}</strong><p>${story}</p><span>Synthetic held-out episode · minute ${d.minute} · 30-minute forecast</span></div><div class="workspace-stat-grid"><article class="workspace-card"><small>Current temperature</small><strong>${reading('temperature_c',value(d.current,'temperature_c'))}</strong><span>BME680 synthetic channel</span></article><article class="workspace-card"><small>Forecast decision</small><strong>${d.breach?'Early alert':'Monitoring'}</strong><span>${warning}</span></article><article class="workspace-card"><small>Alert route</small><strong>${d.breach?(state.fault?'Bluetooth → laptop':'Wi-Fi → laptop'):'Standby'}</strong><span>${d.breach?'Simulated receipt; physical delivery unverified.':'No alert packet generated.'}</span></article></div><div class="workspace-two"><article class="workspace-card"><h2>What the model sees</h2><p>The previous 60 minutes of temperature, humidity, pressure, BME680 gas resistance, and MQ-135 raw ADC, plus the selected room type.</p><button class="workspace-button" data-go="sensors">Inspect all sensors</button></article><article class="workspace-card"><h2>What needs attention</h2><p>${warning} ${escapeHtml(d.scenario.response)}</p><button class="workspace-button" data-go="alerts">Open alert policy</button></article></div>`;
  if(view==='sensors')return `<div class="workspace-intro"><strong>Five synthetic sensor channels</strong><p>Current readings and the model's +30-minute outputs for ${room}. Every channel enters the TinyML model; three have configured demo alert ranges.</p></div><div class="workspace-card workspace-table-wrap"><table class="workspace-table"><thead><tr><th>Channel</th><th>Current</th><th>Forecast +30 min</th><th>Demo range</th><th>Policy result</th></tr></thead><tbody>${policyRows()}</tbody></table></div><div class="workspace-two"><article class="workspace-card"><h2>BME680</h2><p>Temperature, humidity, pressure, and gas resistance are separate readings. Gas resistance is a broad sensor response; it does not identify a chemical.</p></article><article class="workspace-card"><h2>MQ-135</h2><p>MQ-135 is represented as raw ADC. It contributes to the forecast pattern, but no calibrated gas concentration or universal alert limit is claimed.</p></article></div>`;
  if(view==='sites'){
    const rooms=[...new Set(state.scenarios.map(item=>item.room))];
    return `<div class="workspace-intro"><strong>Choose a simulated room and scenario</strong><p>Each selectable scenario family was held out from model fitting. Choosing one loads a new episode and opens its forecast.</p></div><div class="site-grid">${rooms.map(site=>`<article class="workspace-card site-card"><h2>${escapeHtml(site)}</h2><span class="site-count">${state.scenarios.filter(item=>item.room===site).length} held-out scenarios</span>${state.scenarios.filter(item=>item.room===site).map(item=>`<button type="button" class="site-scenario ${item.key===state.scenario?'active':''}" data-scenario="${escapeHtml(item.key)}"><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.story)}</span></button>`).join('')}</article>`).join('')}</div>`;
  }
  if(view==='alerts')return `<div class="workspace-intro ${d.breach?'workspace-warning':''}"><strong>${d.breach?'Forecast alert · '+warning:'No forecast alert at this minute'}</strong><p>${d.breach?escapeHtml(d.scenario.response):'The model predicts no crossing of the configured demo ranges at its six forecast points.'}</p><span>${d.breach?`Event ${escapeHtml(d.event_id)} · ${state.fault?'Bluetooth-to-laptop receipt simulated':'Wi-Fi-to-laptop receipt simulated'}`:'No alert event or receipt has been generated.'}</span></div><div class="workspace-card workspace-table-wrap"><h2>Alert criteria for ${room}</h2><p>Temperature, humidity, and BME680 gas resistance are checked at +5, +10, +15, +20, +25, and +30 minutes. The earliest crossing starts one alert event.</p><table class="workspace-table"><thead><tr><th>Channel</th><th>Current</th><th>Forecast +30 min</th><th>Demo range</th><th>Policy result</th></tr></thead><tbody>${policyRows()}</tbody></table></div><div class="workspace-two"><article class="workspace-card"><h2>Pressure and MQ-135</h2><p>Both channels are model inputs and outputs. Pressure has no room hazard bound in this demo; MQ-135 is raw ADC and has no calibrated ppm limit.</p></article><article class="workspace-card"><h2>Delivery evidence</h2><p>${state.hardware?'TX hardware result available in Alert Details.':state.fault?'Bluetooth receiver receipt is simulated for this episode.':'Laptop Wi-Fi receipt is simulated for this episode.'} Backend storage and actual voice playback are not inferred from these labels.</p><button class="workspace-button" data-go="integrations">Inspect delivery paths</button></article></div>`;
  if(view==='reports'){
    const origin=d.observed.at(-11), observed=d.actual_future?.at(-1);
    const rows=d.channels.map(channel=>{const i=idx(channel),trend=d.current[i]+3*(d.current[i]-origin[i]);const forecast=d.forecast.at(-1)[i];return `<tr><th scope="row">${escapeHtml(labels[channel])}</th><td>${escapeHtml(reading(channel,forecast))}</td><td>${escapeHtml(reading(channel,trend))}</td><td>${observed?escapeHtml(reading(channel,observed[i])):'Hidden'}</td><td>${observed?escapeHtml(reading(channel,Math.abs(forecast-observed[i]))):'—'}</td></tr>`;}).join('');
    return `<div class="workspace-intro"><strong>Forecast versus a recent-trend baseline</strong><p>The trend baseline extends the last ten-minute change to +30 minutes. The TinyML model uses 60 minutes and all five channels. Future values are hidden until revealed.</p><span>Held-out family: ${title} · episode seed ${d.seed}</span></div><div class="workspace-card workspace-table-wrap"><h2>+30-minute comparison</h2><table class="workspace-table"><thead><tr><th>Channel</th><th>TinyML forecast</th><th>Recent trend</th><th>Simulator future</th><th>Model absolute error</th></tr></thead><tbody>${rows}</tbody></table><button class="workspace-button" data-action="reveal">${d.truth_revealed?'Hide simulator future':'Reveal simulator future'}</button></div><div class="workspace-two"><article class="workspace-card"><h2>Model structure</h2><p>70 inputs → 48 → 24 → 30 outputs. Six future points at five-minute spacing are produced on the TX firmware and in this dashboard.</p></article><article class="workspace-card"><h2>Evidence boundary</h2><p>These comparisons use generated scenarios. They do not establish real-room forecast accuracy, physical hazard detection, or calibrated gas concentration.</p></article></div>`;
  }
  if(view==='integrations'){
    const h=state.hardware;
    const wifi=h?(h.rx_ack?'RX exact-ID ACK received':'No RX ACK'):d.breach?(state.fault?'Wi-Fi send blocked in simulation':'Simulated laptop Wi-Fi receipt'):'Ready; no alert packet';
    const bluetooth=h?(h.bt_ack?'Laptop stored receipt received':'Receipt unconfirmed'):d.breach&&state.fault?'Simulated laptop Bluetooth receipt':'Standby';
    return `<div class="workspace-intro"><strong>Alert delivery for ${room}</strong><p>The route is selected after a forecast alert. TX, receiver and backend storage are separate outcomes. Legacy replay includes an RX ESP32.</p><span>${h?'Connected TX result':'The direct laptop route is simulated; no physical receipt is implied.'}</span></div><div class="workspace-stat-grid integration-grid"><article class="workspace-card"><small>01 · TX ESP32</small><strong>${h?(h.tx_persisted?'Stored':'Store failed'):'Synthetic event'}</strong><span>${h?'TX-reported NVS result':'Prepared in browser simulation'}</span></article><article class="workspace-card"><small>02 · ${h?'Wi-Fi → RX ESP32':'Wi-Fi → laptop'}</small><strong>${h?(h.rx_ack?'ACK received':'No ACK'):state.fault?'Blocked':'Primary path'}</strong><span>${escapeHtml(wifi)}</span></article><article class="workspace-card"><small>03 · Bluetooth</small><strong>${h?(h.bt_ack?'Receipt':'Unconfirmed'):d.breach&&state.fault?'Fallback':'Standby'}</strong><span>${escapeHtml(bluetooth)}</span></article><article class="workspace-card"><small>04 · Backend</small><strong>Unverified</strong><span>A route ACK alone does not prove backend storage.</span></article></div><div class="workspace-card integration-control"><h2>Transport test</h2><p>Toggle a simulated Wi-Fi-to-laptop timeout. An alert then uses the nearby Bluetooth route in the demo.</p><label class="workspace-check"><input id="integration-fault" type="checkbox" ${state.fault?'checked':''}> Simulate Wi-Fi timeout</label><button class="workspace-button" data-action="hardware">Open connected TX replay</button></div>`;
  }
  if(view==='settings')return `<div class="workspace-intro"><strong>Simulation controls</strong><p>These controls affect only the generated episode and dashboard display. They do not configure real emergency dispatch or a deployed sensor.</p></div><div class="workspace-card settings-card"><label>Episode seed <input id="setting-seed" type="number" min="1" max="999" value="${d.seed}"></label><label>Simulation minute <input id="setting-minute" type="range" min="60" max="110" value="${d.minute}"><output id="setting-minute-value">${d.minute}</output></label><label class="workspace-check"><input id="setting-fault" type="checkbox" ${state.fault?'checked':''}> Inject Wi-Fi-to-laptop timeout</label><label class="workspace-check"><input id="setting-reveal" type="checkbox" ${state.reveal?'checked':''}> Reveal hidden simulator future</label><button class="workspace-button" data-action="apply-settings">Apply settings</button><p id="setting-error" class="setting-error" role="status"></p></div><div class="workspace-two"><article class="workspace-card"><h2>Selected scenario</h2><p>${room} · ${title}</p><button class="workspace-button" data-go="sites">Change room</button></article><article class="workspace-card"><h2>Alert policy</h2><p>Forecast limits are fixed for each room in this synthetic demo. Temperature, humidity, and BME680 gas resistance can trigger alerts; pressure and MQ-135 raw ADC remain context signals.</p></article></div>`;
  return '';
}
const workspaceTitles = {overview:['Overview','Current episode at a glance'],live:['Live Hardware','Physical sensor readings and delivery receipts'],sensors:['Sensors','Five inputs, five forecast outputs'],sites:['Sites','Choose a room and held-out scenario'],alerts:['Alerts','Forecast limits and delivery state'],reports:['Reports','Model output and baseline comparison'],integrations:['Integrations','Wi-Fi, Bluetooth, and receipt boundaries'],settings:['Settings','Synthetic episode controls']};
function renderWorkspace(){
  if(state.view==='forecast')return;
  const config=workspaceTitles[state.view];
  text('workspace-title',config[0]);text('workspace-subtitle',config[1]);
  if(state.view==='live'){
    text('workspace-context','PHYSICAL ROUTE');
    text('room-motto','REAL READINGS. TRACEABLE DELIVERY.');
    text('brand-tagline','HARDWARE NETWORK. LIVE TELEMETRY.');
    window.liveDashboard.render();
    return;
  }
  text('workspace-context',state.data?`${state.data.scenario.room.toUpperCase()} · SYNTHETIC`:'SYNTHETIC DEMO');
  $('workspace-body').innerHTML=state.data?workspaceMarkup(state.view):'<div class="workspace-card">Loading synthetic episode…</div>';
  const minute=$('setting-minute');if(minute)minute.addEventListener('input',()=>text('setting-minute-value',minute.value));
}
function setView(view,push=true){
  const selected=viewNames.includes(view)?view:'forecast';
  if(state.view==='live'&&selected!=='live'){
    window.liveDashboard.stop();
    text('top-time',`Synthetic episode · minute ${state.minute}`);
    text('room-motto',roomThemes[state.data?.scenario.room||'Cold storage'].motto);
    text('brand-tagline',roomThemes[state.data?.scenario.room||'Cold storage'].brand);
  }
  if(selected!=='forecast')stop();
  state.view=selected;
  document.body.dataset.view=selected;
  $('forecast-view').hidden=selected!=='forecast';
  $('workspace-view').hidden=selected==='forecast';
  document.querySelectorAll('.sidebar nav a[data-view]').forEach(link=>{const active=link.dataset.view===selected;link.classList.toggle('selected',active);if(active)link.setAttribute('aria-current','page');else link.removeAttribute('aria-current');});
  document.title=`${selected==='forecast'?'Scenario Forecast':workspaceTitles[selected][0]} · SafeSense`;
  if(push)history.pushState({view:selected},'',selected==='forecast'?'/forecast':`/forecast?view=${selected}`);
  renderWorkspace();if(selected==='live')window.liveDashboard.start();window.scrollTo(0,0);
}
function speak(){const d=state.data;if(!d?.breach)return;if(!('speechSynthesis' in window)){alert('Speech synthesis is unavailable in this browser.');return;}speechSynthesis.cancel();const message=`SafeSense synthetic demonstration alert. ${d.scenario.room}. ${labels[d.breach.channel]} may cross the configured demo range in about ${d.breach.at_minute} minutes. ${d.scenario.response}`;speechSynthesis.speak(new SpeechSynthesisUtterance(message));}
function stop(){if(state.timer){clearInterval(state.timer);state.timer=null;}$('run-button').querySelector('span').textContent='Run Simulation';}

$('scenario-select').addEventListener('change',async e=>{stop();state.scenario=e.target.value;state.minute=82;state.chartManual=false;await loadEpisode();});
$('location-button').addEventListener('click',()=>setView('sites'));
$('wifi-fault').addEventListener('change',e=>{state.fault=e.target.checked;state.hardware=null;render();});
$('reveal-truth').addEventListener('change',async e=>{state.reveal=e.target.checked;await loadEpisode();});
$('chart-channel').addEventListener('change',()=>{state.chartManual=true;renderChart();});
$('voice-button').addEventListener('click',speak);
$('run-button').addEventListener('click',async()=>{if(state.timer){stop();return;}state.minute=60;await loadEpisode();$('run-button').querySelector('span').textContent='Pause Simulation';state.timer=setInterval(async()=>{if(state.minute>=110){stop();return;}state.minute++;try{await loadEpisode();}catch(error){stop();showError(error);}},450);});
$('scenario-search').addEventListener('input',e=>{const term=e.target.value.trim().toLowerCase();for(const option of $('scenario-select').options)option.hidden=Boolean(term&&!option.textContent.toLowerCase().includes(term));});
$('scenario-search').addEventListener('keydown',e=>{if(e.key==='Enter'){const option=[...$('scenario-select').options].find(o=>!o.hidden);if(option){$('scenario-select').value=option.value;$('scenario-select').dispatchEvent(new Event('change'));setView('forecast');e.target.blur();}}});
$('details-button').addEventListener('click',()=>$('details-dialog').showModal());
$('close-details').addEventListener('click',()=>$('details-dialog').close());
$('replay-button').addEventListener('click',async()=>{const button=$('replay-button'),port=$('tx-port').value.trim().toUpperCase();if(!/^COM[0-9]{1,3}$/.test(port)){text('replay-result','Enter a local COM port such as COM11.');return;}button.disabled=true;text('replay-result','Sending synthetic history to TX and waiting for route receipts…');try{const response=await fetch('/api/v1/forecast/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario:state.scenario,minute:state.minute,seed:state.seed,wifi_fault:state.fault,port})});const result=await response.json();if(!response.ok)throw new Error(result.detail||'TX replay failed');state.hardware=result.receipt;text('replay-result',`TX result received for ${state.hardware.event_id}.`);render();}catch(error){text('replay-result',String(error.message||error));}finally{button.disabled=false;}});
document.querySelectorAll('[data-view]').forEach(link=>link.addEventListener('click',event=>{event.preventDefault();setView(link.dataset.view);}));
window.addEventListener('popstate',()=>{const view=new URLSearchParams(location.search).get('view');setView(viewNames.includes(view)?view:'forecast',false);});
$('workspace-body').addEventListener('click',async event=>{
  const go=event.target.closest('[data-go]');if(go){setView(go.dataset.go);return;}
  const scenario=event.target.closest('[data-scenario]');if(scenario){state.scenario=scenario.dataset.scenario;state.minute=82;state.chartManual=false;$('scenario-select').value=state.scenario;await loadEpisode();setView('forecast');return;}
  const action=event.target.closest('[data-action]')?.dataset.action;
  if(action==='reveal'){state.reveal=!state.reveal;$('reveal-truth').checked=state.reveal;await loadEpisode();return;}
  if(action==='hardware'){$('details-dialog').showModal();return;}
  if(action==='apply-settings'){
    const seed=Number($('setting-seed').value),minute=Number($('setting-minute').value);
    if(!Number.isInteger(seed)||seed<1||seed>999||!Number.isInteger(minute)||minute<60||minute>110){text('setting-error','Use seed 1–999 and minute 60–110.');return;}
    state.seed=seed;state.minute=minute;state.fault=$('setting-fault').checked;state.reveal=$('setting-reveal').checked;
    $('wifi-fault').checked=state.fault;$('reveal-truth').checked=state.reveal;
    await loadEpisode();
  }
});
$('workspace-body').addEventListener('change',event=>{
  if(event.target.id==='integration-fault'){
    state.fault=event.target.checked;$('wifi-fault').checked=state.fault;state.hardware=null;render();
  }
});
function showError(error){text('status-title','Forecast unavailable');text('status-copy',String(error.message||error));$('status-banner').className='status-banner warning';}
setView(state.view,false);
loadScenarios().catch(showError);
