(() => {
  const scenarios={empty_room:{count:0,title:'Empty room'},one_person:{count:1,title:'One person'},two_people:{count:2,title:'Two people'}};
  const state = {mode:'replay', scenario:'empty_room', index:0, result:null, capture:null, captureError:'', timer:null, playTimer:null, requestId:0, windowHistory:[], windowCounter:0, lastHistorySequence:null};
  const root = () => document.getElementById('workspace-body');
  const el = id => document.getElementById(id);
  const label = value => value == null ? 'UNKNOWN' : `${value} ${value === 1 ? 'person' : 'people'}`;

  function rememberWindow(sample) {
    if(!Array.isArray(sample.signal_trace)||sample.signal_trace.length!==100)return;
    if(sample.source?.startsWith('LIVE_ESP32_')&&sample.last_sequence===state.lastHistorySequence)return;
    state.lastHistorySequence=sample.last_sequence;
    const values=sample.signal_trace;
    state.windowHistory.unshift({number:++state.windowCounter,count:sample.predicted_count,
      mean:values.reduce((sum,value)=>sum+value,0)/values.length,
      low:Math.min(...values),high:Math.max(...values)});
    state.windowHistory.length=Math.min(state.windowHistory.length,50);
  }

  function chart(values) {
    if (!values?.length) return '<div class="csi-no-trace">Waiting for CSI samples</div>';
    const min = Math.min(...values), max = Math.max(...values), span = Math.max(max-min, 1);
    const points = values.map((v,i) => `${(i*700/Math.max(values.length-1,1)).toFixed(1)},${(145-(v-min)*115/span).toFixed(1)}`).join(' ');
    return `<svg viewBox="0 0 700 170" preserveAspectRatio="none" role="img" aria-label="CSI mean amplitude across ${values.length} received frames"><line x1="0" y1="145" x2="700" y2="145" stroke="#cbddea"/><polyline points="${points}" fill="none" stroke="#0b83e9" stroke-width="3" stroke-linejoin="round"/></svg>`;
  }

  function updateCapture() {
    const panel=el('csi-room-capture');
    if(!panel)return;
    panel.hidden=state.mode!=='live';
    if(state.mode!=='live')return;
    const c=state.capture;
    el('csi-capture-status').textContent=state.captureError||(!c?'Checking capture status…':c.active
      ? `${c.room} · ${c.saved_windows} saved window${c.saved_windows===1?'':'s'} · ${c.label_count==null?'unlabelled':`${c.label_count} people, operator confirmed`}`
      : c.session_id?`${c.room} · stopped · ${c.saved_windows} saved windows`:'No room capture started');
    el('csi-capture-summary').textContent=c?.session_id
      ? `Verified windows: 0 people ${c.label_counts?.['0']??0} · 1 person ${c.label_counts?.['1']??0} · 2 people ${c.label_counts?.['2']??0} · unlabelled ${c.label_counts?.unlabelled??0} · Session ID ${c.session_id}`
      : 'Verified window counts will appear after capture starts.';
    el('csi-capture-start').disabled=!!c?.active;
    el('csi-capture-stop').disabled=!c?.active;
    document.querySelectorAll('[data-csi-count]').forEach(button=>{
      button.disabled=!c?.active;
      button.setAttribute('aria-pressed',String(c?.active&&String(c.label_count)===button.dataset.csiCount));
    });
    el('csi-capture-next').textContent=c?.active
      ? `Every ${c.interval_seconds}s · next eligible window ${new Date(c.next_due_at_utc).toLocaleTimeString()}`
      : 'Capture waits for 100 fresh, contiguous CSI frames.';
  }

  async function fetchCapture() {
    if(state.mode!=='live')return;
    try {
      const response=await fetch('/api/v1/csi-count/room-capture',{cache:'no-store'});
      if(!response.ok)throw new Error(`Capture status HTTP ${response.status}`);
      state.capture=await response.json();state.captureError='';
    }catch(problem){state.captureError=String(problem.message||problem);}
    updateCapture();
  }

  async function captureAction(path,body) {
    state.captureError='Applying capture change…';updateCapture();
    try {
      const response=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-SafeSense-Control':'dashboard'},body:JSON.stringify(body||{})});
      const result=await response.json();
      if(!response.ok)throw new Error(result.detail||`HTTP ${response.status}`);
      state.capture=result;state.captureError='';
      await fetchData();
    }catch(problem){state.captureError=String(problem.message||problem);}
    updateCapture();
  }

  function update() {
    if (!el('csi-predicted')) return;
    const d=state.result;
    const live=state.mode==='live';
    const fresh=live&&['LIVE_ESP32_WIFI','LIVE_ESP32_BLUETOOTH'].includes(d?.source);
    const route=d?.source==='LIVE_ESP32_WIFI'?'Wi-Fi UDP':d?.source==='LIVE_ESP32_BLUETOOTH'?'Bluetooth SPP':'wireless';
    const controls=document.querySelector('.csi-controls');
    controls.hidden=live;
    document.querySelector('.csi-layout').classList.toggle('csi-layout-single',live);
    controls.querySelector('small').textContent=live?'LIVE ESP32 CSI':'FIXED RECORDED SCENARIOS';
    controls.querySelector('h2').textContent=state.mode==='live'?'Live people count':'Known people count';
    controls.querySelector('p').textContent=state.mode==='live'?'Fresh CSI packets from the ESP32 are shown here with the count estimated by the model.':'Each button chooses held-out CSI from a recording made with that count. The count is a reference label, not a model input.';
    document.querySelector('.csi-head p').textContent=live?'Live people count and CSI signal fluctuations.':'Choose a fixed scenario. A recorded 100-frame CSI window goes to the model, then its prediction is compared with the known count.';
    document.querySelector('.csi-result > small').textContent=live?'LIVE CSI MODEL OUTPUT':'CSI MODEL OUTPUT';
    document.querySelector('.csi-vs').hidden=live;
    el('csi-match').hidden=live;
    el('csi-score').hidden=live;
    document.querySelector('.csi-trace-head h2').textContent=live?'CSI signal fluctuations':'CSI amplitude over the window';
    document.querySelector('.csi-trace-head small').textContent=live?'LIVE WIRELESS SIGNAL':'RECORDED SIGNAL';
    el('csi-source').textContent=!live?'RECORDED CSI REPLAY':fresh?`${route.toUpperCase()} · FRESH`:'LIVE CSI · NO FRESH WIRELESS DATA';
    const reference=scenarios[state.scenario].count;
    el('csi-actual').textContent=label(reference);
    el('csi-predicted').textContent=label(d?.predicted_count);
    el('csi-predicted-small').textContent=label(d?.predicted_count);
    el('csi-score').textContent=d?.model_score==null?'—':`${Math.round(d.model_score*100)}% model score`;
    const comparable=d?.predicted_count!=null;
    el('csi-match').textContent=!comparable?'Comparison unavailable':reference===d.predicted_count?'Matches scenario reference':'Different from scenario reference';
    el('csi-match').className=`csi-match ${!comparable?'':reference===d.predicted_count?'match':'miss'}`;
    el('csi-trace').innerHTML=chart(d?.signal_trace);
    el('csi-sample').hidden=live;
    el('csi-sample').textContent=!live&&d?`Held-out window ${d.sample_index+1} / ${d.sample_total}`:'No sample loaded';
    el('csi-note').textContent=state.mode==='replay'
      ? 'The scenario selects a held-out PRoFENCH/WiVi32 recording with the same known count. Only 100 × 50 CSI amplitudes are passed to the model.'
      : 'The model receives live ESP32 CSI only; missing, stale, or out-of-range windows stay UNKNOWN.';
    el('csi-live-help').textContent=d?.quality_reason==='OUTSIDE_RECORDED_SIGNAL_RANGE'
      ? `Fresh CSI received, but signal variation ${d.signal_variation} is outside the recorded range ${d.recorded_variation_range?.join('–')}. The count is withheld until this room and radio setup are validated.`
      : fresh ? 'Collecting fresh frames for the model. A full 100-frame window is required.'
        : 'Connect the laptop to the ESP32 Wi-Fi AP for CSI probes, or use Bluetooth when measured CSI packets are available. A full 100-frame window is required.';
    document.querySelectorAll('[data-csi-scenario]').forEach(button=>{
      const active=button.dataset.csiScenario===state.scenario;
      button.classList.toggle('active',active);
      button.setAttribute('aria-pressed',String(active));
    });
    el('csi-next').hidden=state.mode!=='replay';
    el('csi-play').hidden=state.mode!=='replay';
    el('csi-play').textContent=state.playTimer?'Pause recorded windows':'Play recorded windows';
    el('csi-live-help').hidden=!live;
    el('csi-live-samples').hidden=state.mode!=='live';
    if(state.mode==='live'){
      updateCapture();
      el('csi-live-source').textContent=`ESP32 ${route.toUpperCase()} PACKET · MEASURED VALUES`;
      el('csi-live-heading').textContent='Latest CSI packet details';
      el('csi-live-description').textContent='The ESP32 exports 50 signed I/Q pairs (100 payload bytes). Amplitude is √(I² + Q²). A 100-frame window becomes 250 model features: mean, standard deviation, frame change, P10 and P90 for each pair.';
      const history=el('csi-window-history');history.replaceChildren();
      if(!state.windowHistory.length){const note=document.createElement('p');note.className='csi-history-empty';note.textContent='No fresh 100-frame window has reached this session.';history.appendChild(note);}
      state.windowHistory.forEach(window=>{
        const row=document.createElement('div');row.className='csi-window-row';
        [String(window.number),label(window.count),window.mean.toFixed(2),`${window.low.toFixed(2)}–${window.high.toFixed(2)}`].forEach(value=>{
          const cell=document.createElement('span');cell.textContent=value;row.appendChild(cell);
        });
        history.appendChild(row);
      });
      el('csi-live-state').textContent=fresh?'Fresh CSI packet received':'No fresh CSI packet';
      el('csi-live-age').textContent=d?.age_seconds==null?'Never received':`${d.age_seconds}s since last packet`;
      el('csi-live-sequence').textContent=fresh?String(d.last_sequence):'—';
      el('csi-live-rssi').textContent=fresh&&d.last_rssi_dbm!=null?`${d.last_rssi_dbm} dBm`:'—';
      el('csi-live-received').textContent=d?.last_packet_received_at?new Date(d.last_packet_received_at).toLocaleString():'—';
      el('csi-live-frames').textContent=fresh?`${d?.buffered_frames??0}/100`:'0 fresh / 100';
      el('csi-live-packets').textContent=String(d?.packet_count??0);
      el('csi-live-drops').textContent=String(d?.queue_drops??0);
      el('csi-live-board-time').textContent=fresh&&d.last_packet?`${d.last_packet.board_time_us} µs`:'—';
      el('csi-live-first-word').textContent=fresh&&d.last_packet?(d.last_packet.invalid_first_word?'Invalid flag set':'Valid flag'):'—';
      el('csi-live-quality').textContent=d?.quality_reason==='OUTSIDE_RECORDED_SIGNAL_RANGE'
        ? `Variation ${d.signal_variation} vs recorded ${d.recorded_variation_range?.join('–')}`
        : d?.status==='READY'?'Model window accepted':d?.quality_reason||'Awaiting data';
      const pairs=el('csi-live-pairs');pairs.replaceChildren();
      if(fresh&&Array.isArray(d.latest_pair_amplitudes))d.latest_pair_amplitudes.forEach((value,index)=>{
        const item=document.createElement('div');
        const iq=d.last_packet?.iq_pairs?.[index];
        item.textContent=`Pair ${d.pair_positions?.[index]??index} · I ${iq?.[0]??'—'} · Q ${iq?.[1]??'—'} · |H| ${Number(value).toFixed(2)}`;
        pairs.appendChild(item);
      });
      el('csi-live-empty').textContent='No fresh wireless CSI packet has reached the backend.';
      el('csi-live-empty').hidden=fresh;
    }
  }

  async function fetchData() {
    const requestId=++state.requestId;
    try {
      const path=state.mode==='replay'?`/api/v1/csi-count/replay?scenario=${state.scenario}&index=${state.index}`:'/api/v1/csi-count/status';
      const response=await fetch(path,{cache:'no-store'});
      const data=await response.json();
      if(requestId!==state.requestId)return;
      if (!response.ok) throw new Error(data.detail||`HTTP ${response.status}`);
      state.result=data;
      if(state.mode==='live'&&data.source?.startsWith('LIVE_ESP32_'))rememberWindow(data);
      el('csi-error').textContent='';
      update();
    } catch(error) {
      if(requestId!==state.requestId)return;
      state.result=null;
      el('csi-error').textContent=String(error.message||error);
      update();
    }
  }

  function render() {
    root().innerHTML=`<div class="csi-head"><div><span class="csi-eyebrow">Wi-Fi CHANNEL STATE INFORMATION</span><h2>People count from CSI</h2><p>Choose a fixed scenario. A recorded 100-frame CSI window goes to the model, then its prediction is compared with the known count.</p></div><span id="csi-source" class="csi-source">RECORDED CSI REPLAY</span></div>
      <div class="csi-tabs" role="group" aria-label="CSI source"><button id="csi-replay-tab" type="button" class="${state.mode==='replay'?'active':''}">Recorded replay</button><button id="csi-live-tab" type="button" class="${state.mode==='live'?'active':''}">Live ESP32</button></div>
      <section class="workspace-card evidence-exports" aria-label="CSI CSV exports"><small>DOWNLOAD STORED EVIDENCE</small><h2>CSI exports</h2><p>Export measured packet I/Q and saved room windows. These files contain collected records, including older rows; replay selections do not create new captures. Count labels appear only when an operator supplied them.</p><div class="evidence-export-links"><a download href="/api/v1/exports/csi-packets.csv">Export detailed packets · CSV</a><a download href="/api/v1/exports/room-windows.csv">Export collected windows · CSV</a></div></section>
      <div class="csi-layout"><section class="workspace-card csi-controls"><small>FIXED RECORDED SCENARIOS</small><h2>Known people count</h2><p>Each button chooses held-out CSI from a recording made with that count. The count is a reference label, not a model input.</p><div class="csi-scenarios" role="group" aria-label="Recorded people count scenarios">${Object.entries(scenarios).map(([key,s])=>`<button type="button" data-csi-scenario="${key}" aria-pressed="false"><strong>${s.count}</strong><span>${s.title}</span></button>`).join('')}</div><p id="csi-note" class="csi-mode-note"></p><div class="csi-actions"><button id="csi-next" class="workspace-button" type="button">Next CSI window →</button><button id="csi-play" class="workspace-button csi-secondary" type="button">Play recorded windows</button></div></section>
      <section class="workspace-card csi-result"><small>CSI MODEL OUTPUT</small><h2 id="csi-predicted">UNKNOWN</h2><span id="csi-score" class="csi-score">—</span><div class="csi-vs"><div><span>Scenario reference</span><strong id="csi-actual">0 people</strong></div><div><span>Predicted from CSI</span><strong id="csi-predicted-small">UNKNOWN</strong></div></div><div id="csi-match" class="csi-match">Comparison unavailable</div></section></div>
      <section class="workspace-card csi-trace-card"><div class="csi-trace-head"><div><small>RECEIVED SIGNAL</small><h2>CSI amplitude over the window</h2></div><span id="csi-sample">No sample loaded</span></div><div id="csi-trace" class="csi-trace"></div><p id="csi-error" role="status" class="setting-error"></p></section>
      <section id="csi-live-samples" class="workspace-card csi-live-samples" hidden><small id="csi-live-source">WIRELESS CSI RECEIVER</small><h2 id="csi-live-heading">Latest CSI packet details</h2><p id="csi-live-description"></p><div id="csi-live-help" class="csi-live-help" role="status"></div><div class="csi-live-facts"><div><span>Packet state</span><strong id="csi-live-state">No fresh CSI packets</strong></div><div><span>Freshness</span><strong id="csi-live-age">Never received</strong></div><div><span>Sequence</span><strong id="csi-live-sequence">—</strong></div><div><span>RSSI</span><strong id="csi-live-rssi">—</strong></div><div><span>Last backend receipt</span><strong id="csi-live-received">—</strong></div><div><span>Frames in window</span><strong id="csi-live-frames">0/100</strong></div><div><span>Packets received</span><strong id="csi-live-packets">0</strong></div><div><span>Board queue drops</span><strong id="csi-live-drops">0</strong></div><div><span>Board packet time</span><strong id="csi-live-board-time">—</strong></div><div><span>First word flag</span><strong id="csi-live-first-word">—</strong></div></div><p class="csi-quality">Window quality: <strong id="csi-live-quality">Awaiting data</strong></p><p id="csi-live-empty" class="csi-live-empty">No fresh CSI sample available from the local bridge.</p><details><summary>Show all 50 I/Q pairs and amplitudes</summary><div id="csi-live-pairs" class="csi-pairs"></div></details></section>
      <section id="csi-room-capture" class="workspace-card csi-room-capture" hidden><small>NEW ROOM SETUP</small><h2>Timed CSI capture</h2><p>Enter the actual count once when it changes. Complete CSI windows are saved and labelled automatically at the selected interval. Model estimates are never treated as verified labels.</p><p class="csi-capture-source">Measured CSI reaches this page over ESP32 Wi-Fi UDP or the paired Bluetooth SPP link. Capture starts when fresh packets arrive.</p><div class="csi-capture-setup"><label>Room name <input id="csi-room-name" maxlength="80" value="Demo room" autocomplete="off"></label><label>Interval <select id="csi-room-interval"><option value="5">5 seconds</option><option value="10" selected>10 seconds</option><option value="20">20 seconds</option><option value="30">30 seconds</option></select></label><label>Starting count <select id="csi-room-label"><option value="">Unlabelled</option><option value="0">0 people</option><option value="1">1 person</option><option value="2">2 people</option></select></label><button id="csi-capture-start" type="button" class="workspace-button">Start room capture</button></div><div class="csi-capture-actions"><button type="button" data-csi-count="0">Now 0 people</button><button type="button" data-csi-count="1">Now 1 person</button><button type="button" data-csi-count="2">Now 2 people</button><button id="csi-capture-stop" type="button">Stop</button></div><p id="csi-capture-status" role="status">Checking capture status…</p><p id="csi-capture-summary" class="csi-capture-summary"></p><small id="csi-capture-next">Capture waits for 100 fresh, contiguous CSI frames.</small></section>
      <p class="csi-disclaimer">Research baseline: 0–2 people only. The 85.6% held-out score is from later windows of the same recordings. New-room accuracy and ESP32 live accuracy have not been measured; this output is not a safety or occupancy decision.</p>`;
    el('csi-live-pairs').closest('details').insertAdjacentHTML('afterend','<h3 class="csi-history-heading">Recent received model windows</h3><div class="csi-window-table"><div class="csi-window-row csi-window-header"><span>Window</span><span>People</span><span>Mean CSI</span><span>Range</span></div><div id="csi-window-history" class="csi-window-history"></div></div>');
    document.querySelectorAll('[data-csi-scenario]').forEach(button=>button.addEventListener('click',()=>{
      state.scenario=button.dataset.csiScenario;state.index=0;state.result=null;
      if(state.mode==='replay')fetchData();else update();
    }));
    el('csi-replay-tab').addEventListener('click',()=>switchMode('replay'));
    el('csi-live-tab').addEventListener('click',()=>switchMode('live'));
    el('csi-next').addEventListener('click',()=>{state.index=(state.index+1)%(state.result?.sample_total||1);fetchData();});
    el('csi-play').addEventListener('click',()=>{
      if(state.playTimer){clearInterval(state.playTimer);state.playTimer=null;}
      else state.playTimer=setInterval(()=>{state.index=(state.index+1)%(state.result?.sample_total||1);fetchData();},1500);
      update();
    });
    el('csi-capture-start').addEventListener('click',()=>captureAction('/api/v1/csi-count/room-capture',{
      room:el('csi-room-name').value.trim(),interval_seconds:Number(el('csi-room-interval').value),
      label_count:el('csi-room-label').value===''?null:Number(el('csi-room-label').value)}));
    document.querySelectorAll('[data-csi-count]').forEach(button=>button.addEventListener('click',()=>
      captureAction('/api/v1/csi-count/room-capture/label',{label_count:Number(button.dataset.csiCount)})));
    el('csi-capture-stop').addEventListener('click',()=>captureAction('/api/v1/csi-count/room-capture/stop',{}));
    update();fetchData();
  }

  function switchMode(mode) {
    if(state.mode===mode)return;
    stop();state.mode=mode;state.result=null;state.index=0;
    render();start();
  }
  function start() {if(state.mode==='live'&&!state.timer){fetchData();fetchCapture();state.timer=setInterval(()=>{fetchData();fetchCapture();},1000);}}
  function stop() {if(state.timer){clearInterval(state.timer);state.timer=null;}if(state.playTimer){clearInterval(state.playTimer);state.playTimer=null;}state.requestId++;}
  window.csiCountDashboard={render,start,stop};
})();
