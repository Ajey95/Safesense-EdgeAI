/* Physical readings come from backend storage; each route keeps its own evidence. */
(() => {
  let snapshot = null;
  let error = null;
  let timer = null;
  let busy = false;
  let manualQueued = false;
  let refreshFeedback = '';
  const html = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'
  })[char]);
  const stamp = value => value ? new Date(value).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—';
  const receiptStamp = value => value ? new Date(value).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'}) : '—';
  const utcStamp = value => value && !/(?:Z|[+-]\d\d:\d\d)$/i.test(value) ? `${value}Z` : value;
  const reading = (value, digits, suffix) => value === null || value === undefined
    ? 'Unavailable' : `${Number(value).toLocaleString(undefined,{maximumFractionDigits:digits,minimumFractionDigits:digits})}${suffix}`;
  const status = (label, kind='muted') => `<span class="table-status ${kind}">${html(label)}</span>`;
  const refreshControls = () => `<button type="button" id="live-refresh" ${busy?'disabled':''}>${busy?'Checking…':'Refresh now'}</button>${refreshFeedback?`<span class="live-refresh-feedback" role="status" aria-live="polite">${html(refreshFeedback)}</span>`:''}`;

  function sensorCard(label, value, note) {
    return `<article class="live-sensor"><small>${html(label)}</small><strong>${html(value)}</strong><span>${html(note)}</span></article>`;
  }

  function bridgeCard(label, info, qualifier) {
    const state = !info ? 'No heartbeat' : info.fresh ? 'Process reporting' : 'Heartbeat stale';
    const description = info ? `${qualifier} · ${info.status} · ${Math.round(info.age_seconds)}s ago` : qualifier;
    return `<article class="workspace-card live-bridge"><small>${html(label)}</small><strong>${html(state)}</strong><span>${html(description)}</span></article>`;
  }

  function wirelessReceiptCards() {
    const card = (label, receipts) => `<article class="workspace-card live-bt-card"><div class="live-section-title"><h2>${label} delivery receipts</h2><span>${receipts.length} recent backend-stored event${receipts.length===1?'':'s'}</span></div>
      ${receipts.length ? receipts.map(receipt => `<div class="live-bt-row"><code>${html(receipt.event_id)}</code><span>${receipt.test_alert?'Transport test':'Sensor sample'} · Laptop stored · Backend receipt ${html(receiptStamp(receipt.receipt_reported_at))}</span><strong>Stored</strong></div>`).join('') : `<p>No ${label} sensor delivery has reached the backend yet.</p>`}</article>`;
    return `<section class="workspace-two live-receipt-grid" aria-label="Wireless delivery receipts">${card('Wi-Fi',snapshot.wifi_receipts||[])}${card('Bluetooth',snapshot.bluetooth_receipts||[])}</section>`;
  }

  function sensorDeliveryTable(label, receipts) {
    const samples = receipts.filter(receipt => !receipt.test_alert);
    const rows = samples.map(receipt => {
      const sensor = receipt.environment || {};
      return `<tr><th scope="row"><code>${html(receipt.event_id)}</code></th>
        <td>${html(receiptStamp(receipt.receipt_reported_at))}</td>
        <td>${html(reading(sensor.temperature_c,1,' °C'))}</td>
        <td>${html(reading(sensor.humidity_pct,1,' %'))}</td>
        <td>${html(reading(sensor.gas_adc_raw,0,' raw'))}</td>
        <td>${status(`${label} laptop stored`,'good')}</td></tr>`;
    }).join('');
    return `<section class="workspace-card workspace-table-wrap live-history"><div class="live-section-title"><h2>Recent ${label} sensor deliveries</h2><span>${samples.length} backend-stored sample${samples.length===1?'':'s'}</span></div>
      ${rows?`<table class="workspace-table"><thead><tr><th>Event ID</th><th>Backend receipt</th><th>Temperature</th><th>Humidity</th><th>MQ-135</th><th>Transport</th></tr></thead><tbody>${rows}</tbody></table>`:`<p>No ${label} sensor delivery has reached the backend yet.</p>`}</section>`;
  }

  function wirelessDeliveryTables() {
    return sensorDeliveryTable('Wi-Fi',snapshot.wifi_sensor_deliveries||[]) +
      sensorDeliveryTable('Bluetooth',snapshot.bluetooth_sensor_deliveries||[]);
  }

  function deliveryProofCard() {
    const board = snapshot.board_queue;
    const proof = snapshot.board_queue_proof;
    if (!board) return `<section class="workspace-card live-bt-card" aria-label="Wireless delivery proof"><div class="live-section-title"><h2>ESP32 NVS → databases</h2>${status('Awaiting board status')}</div><p>No wireless NVS status has reached the laptop and backend. Update the ESP32 firmware and both receiver processes to show this proof.</p></section>`;
    const fresh = board.age_seconds <= 45;
    const pending = board.pending_event_ids.length
      ? board.pending_event_ids.map(id => `<code>${html(id)}</code>`).join(' · ') : 'None';
    const ack = board.last_acked_id || 'None yet';
    const history = (snapshot.board_queue_history||[]).slice(0,6).map(row =>
      `<div class="live-bt-row"><code>${html(row.queue_depth)}/16</code><span>${html(row.route)} board report · ${html(receiptStamp(row.backend_stored_at_utc))}${row.age_seconds>45?' · historical':''}</span><strong>${html(row.last_acked_id||row.last_enqueued_id||'No event')}</strong></div>`).join('');
    return `<section class="workspace-card live-bt-card" aria-label="Wireless delivery proof">
      <div class="live-section-title"><h2>ESP32 NVS → databases</h2>${status(fresh?'LIVE BOARD REPORT':'STALE BOARD REPORT',fresh?'good':'bad')}</div>
      <div class="live-path">
        <div><small>01 · ESP32 NVS</small><strong>${html(board.queue_depth)}/16 pending</strong><span>${html(board.route)} status · ${html(receiptStamp(board.backend_stored_at_utc))}</span></div>
        <div><small>02 · Laptop journal</small><strong>Board status stored</strong><span>${html(receiptStamp(board.laptop_stored_at_utc))}</span></div>
        <div><small>03 · Backend SQLite</small><strong>Board status stored</strong><span>${html(receiptStamp(board.backend_stored_at_utc))}</span></div>
        <div><small>04 · Exact-ID ACK</small><strong><code>${html(ack)}</code></strong><span>${html(board.last_ack_route)} board-observed ACK</span></div>
      </div>
      <p><strong>Pending IDs:</strong> ${pending}</p>
      <p><strong>Last enqueued:</strong> <code>${html(board.last_enqueued_id||'None yet')}</code></p>
      ${proof?.receiver_receipt_at&&proof?.backend_stored_at
        ? `<p><strong>Matching event in databases:</strong> <code>${html(proof.event_id)}</code> · transport receipt recorded ${html(receiptStamp(proof.receiver_receipt_at))} · backend telemetry ${html(receiptStamp(proof.backend_stored_at))}</p>`
        : proof ? `<p><strong>Database sync pending:</strong> <code>${html(proof.event_id)}</code> was ACKed by the board; wait for its transport receipt and backend telemetry.</p>` : ''}
      <div class="live-section-title"><h3>Recent board queue observations</h3><span>Board values, received wirelessly</span></div>${history}
      <p class="live-provenance">Queue depth is reported by the ESP32 at the shown time. An old report is marked stale. A board ACK means its NVS head was removed after the laptop's exact-ID acknowledgement; backend telemetry is checked separately.</p>
    </section>`;
  }

  function appendDirectTestPanel(target) {
    const receiver = snapshot.direct_status;
    if (!receiver) return;
    const panel = document.createElement('section');
    panel.className = 'workspace-card integration-control';
    panel.innerHTML = `<h2>Single-board wireless test</h2><p>The laptop receiver is running. Join the ESP32 Wi-Fi network, then test a real packet and receipt.</p>
      <label class="workspace-check"><input id="direct-fault" type="checkbox" ${receiver.wifi_fault?'checked':''}> Inject Wi-Fi receiver fault</label>
      <button type="button" class="workspace-button" id="direct-test">Send transport test alert</button>
      <span id="direct-test-result" role="status">${receiver.laptop_stored} Wi-Fi events stored · ${receiver.backend_pending} awaiting backend</span>`;
    target.querySelector('.live-head')?.insertAdjacentElement('afterend', panel);
    panel.querySelector('#direct-fault').addEventListener('change', async event => {
      try {
        const response = await fetch('/api/v1/live/direct/fault', {method:'POST',headers:{'Content-Type':'application/json','X-SafeSense-Control':'dashboard'},body:JSON.stringify({enabled:event.target.checked})});
        if (!response.ok) throw new Error(`Fault control returned HTTP ${response.status}`);
        await refresh(true);
      } catch (problem) { panel.querySelector('#direct-test-result').textContent = String(problem.message || problem); }
    });
    panel.querySelector('#direct-test').addEventListener('click', async () => {
      const result = panel.querySelector('#direct-test-result');
      result.textContent = 'Requesting an ESP32 transport test alert…';
      try {
        const response = await fetch('/api/v1/live/direct/test-alert', {method:'POST',headers:{'X-SafeSense-Control':'dashboard'}});
        if (!response.ok) {
          const problemBody = await response.json().catch(() => ({}));
          throw new Error(problemBody.detail || `Test request returned HTTP ${response.status}`);
        }
        result.textContent = 'Request sent. Await a real Wi-Fi or Bluetooth receipt.';
      } catch (problem) { result.textContent = String(problem.message || problem); }
    });
  }

  function appendTransportSwitcher(target) {
    const network=snapshot.wifi_session;
    if(!network)return;
    const handoff=snapshot.transport_handoff;
    const onAp=network.on_safesense_ap;
    const onAmrita=network.current_ssid===network.restore_profile;
    const switching=['STARTING','CONNECTING','ON_SAFESENSE_AP'].includes(network.session?.state);
    const duration=network.duration_seconds||120;
    const logLabels={STARTING:'Wi-Fi visit requested',CONNECTING:'Connecting to ESP32 AP',ON_SAFESENSE_AP:'ESP32 AP connected',AP_CONNECTION_FAILED:'ESP32 AP connection failed',RESTORING:'Returning to Amrita',RESTORED:'Amrita restored',RESTORE_FAILED:'Amrita restore failed',BLUETOOTH_RECONNECT_REQUESTED:'Bluetooth reconnect requested',BLUETOOTH_PACKET_STORED:'New Bluetooth board packet stored'};
    const logRows=(network.events||[]).slice(0,12).map(entry=>{
      const details=[entry.reason,Number.isFinite(entry.csi_probes_sent)?`${entry.csi_probes_sent} CSI probes sent`:null,Number.isFinite(entry.csi_probe_errors)?`${entry.csi_probe_errors} probe errors`:null,entry.event_id?`Event ${entry.event_id}`:null].filter(Boolean).join(' · ');
      return `<li><time>${html(receiptStamp(utcStamp(entry.at_utc)))}</time><strong>${html(logLabels[entry.state]||entry.state)}</strong>${details?`<span>${html(details)}</span>`:''}</li>`;
    }).join('');
    const panel=document.createElement('section');
    panel.className='workspace-card integration-control transport-switcher';
    const btState=handoff?.state==='READY'?`Bluetooth ready · fresh board packet ${html(handoff.latest_bt_event_id)} stored`:handoff?.state==='WAITING_WIFI'?'Returning laptop to Amrita…':handoff?.state==='WAITING_BLUETOOTH'?'Amrita connected · waiting for a new Bluetooth board packet and backend receipt…':handoff?.state==='TIMED_OUT'?'Bluetooth handoff timed out · check pairing and COM15, then press Reconnect Bluetooth':'Bluetooth handoff not yet verified';
    panel.innerHTML=`<h2>Choose laptop transport</h2><p>ESP32 sensor readings and measured CSI use Wi-Fi during the bounded AP visit, then the paired Bluetooth link when available. The Wi-Fi visit returns to Amrita after ${duration} seconds; you can return earlier with the Bluetooth button.</p><div class="transport-switch-actions"><button type="button" class="workspace-button" id="transport-wifi" ${onAmrita&&!switching?'':'disabled'}>Use ESP32 Wi-Fi for ${duration}s</button><button type="button" class="workspace-button" id="transport-bluetooth">${onAmrita&&!switching?'Reconnect Bluetooth':'Return to Amrita · Bluetooth'}</button></div><p id="transport-switch-status" role="status">Laptop Wi-Fi: ${html(network.current_ssid||'Disconnected')} · ${onAp?'ESP32 AP connected':switching?'Wi-Fi visit active':onAmrita?'Internet network connected':'Transition in progress'}${network.session?.return_by_utc&&onAp?` · automatic return by ${html(stamp(network.session.return_by_utc))}`:''}${network.session?.ap_connected===false?` · ESP32 AP connection failed; Amrita restored${network.session.reason?`: ${html(network.session.reason)}`:''}`:''} · ${btState}</p><div class="transport-event-log"><h3>Wi-Fi and Bluetooth transition log</h3><ol aria-label="Recent transport transitions">${logRows||'<li>No transport transition recorded yet.</li>'}</ol></div><p>Wireless delivery is shown only after its packet reaches the laptop and backend. CSI still needs Wi-Fi radio traffic to measure.</p>`;
    target.querySelector('.live-head')?.insertAdjacentElement('afterend',panel);
    for(const [id,path] of [['transport-wifi','/api/v1/live/direct/wifi-session'],['transport-bluetooth','/api/v1/live/direct/wifi-session/restore']]){
      panel.querySelector(`#${id}`).addEventListener('click',async()=>{
        const output=panel.querySelector('#transport-switch-status');
        output.textContent=id==='transport-wifi'?'Changing laptop Wi-Fi profile…':'Requesting Bluetooth reconnect…';
        try{
          const response=await fetch(path,{method:'POST',headers:{'X-SafeSense-Control':'dashboard'}});
          const result=await response.json();
          if(!response.ok)throw new Error(result.detail||`HTTP ${response.status}`);
          output.textContent=id==='transport-wifi'?'Switching to ESP32 AP; automatic return to Amrita is scheduled.':'Bluetooth reconnect requested. Waiting for a fresh board packet and backend receipt…';
          setTimeout(()=>refresh(true),1200);
        }catch(problem){output.textContent=String(problem.message||problem);}
      });
    }
  }

  function exportCard() {
    return `<section class="workspace-card evidence-exports" aria-label="Live hardware CSV exports"><small>DOWNLOAD STORED EVIDENCE</small><h2>Live hardware exports</h2><p>Download Wi-Fi/Bluetooth sensor receipts, ESP32 queue observations, or every local SQLite table. Exports include historical records; check timestamps and source before presenting a row as live.</p><div class="evidence-export-links"><a download href="/api/v1/exports/wireless-sensors.csv">Export sensor deliveries · CSV</a><a download href="/api/v1/exports/nvs-queue.csv">Export NVS queue · CSV</a><a download href="/api/v1/exports/sqlite-tables.zip">Export all databases · CSV ZIP</a></div></section>`;
  }

  function renderWifi(target) {
    const current = snapshot.latest;
    const env = current.environment || {};
    const fresh = snapshot.latest_fresh;
    const sensorReady = env.sensor_healthy === true;
    const receiver = snapshot.direct_status;
    const btOnly = (snapshot.direct_bt_only || []).map(receipt => `<div class="live-bt-row"><code>${html(receipt.event_id)}</code><span>${receipt.details.simulated?'Transport test':'Forecast alert'} · Bluetooth laptop receipt</span><strong>${html(stamp(receipt.reported_at))}</strong></div>`).join('');
    document.getElementById('workspace-context').textContent = 'DIRECT WI-FI';
    document.getElementById('workspace-subtitle').textContent = 'Physical laptop receipts for the single-board route';
    document.getElementById('room-motto').textContent = 'REAL SENSOR DATA. WIRELESS DELIVERY.';
    document.getElementById('brand-tagline').textContent = 'DIRECT SENSOR TELEMETRY.';
    target.innerHTML = `
      <section class="live-head"><div><h2>Live BME680 + MQ-135 readings</h2><p>Sensor ESP32 → Wi-Fi → nearby laptop → local backend. Fresh Wi-Fi readings require the laptop on SafeSense-TX-Laptop.</p></div><div class="live-head-side">${status(!current.sample_observed_at?'WI-FI RECEIPT · SAMPLE AGE UNVERIFIED':!fresh?'STALE WI-FI READING':sensorReady?'LIVE WI-FI READING':'LIVE LINK · SENSOR UNAVAILABLE',fresh&&sensorReady?'good':'bad')}<small>${current.sample_observed_at?`${Math.round(snapshot.latest_age_seconds)}s since board capture`:`Received ${html(stamp(current.wireless_received_at))} · capture time unavailable`}</small>${refreshControls()}</div></section>
      ${exportCard()}
      ${sensorReady?'':'<section class="workspace-card live-sensor-warning" role="status"><strong>BME680 has no valid reading.</strong><p>The packet reached the laptop, but the board has no valid temperature, humidity, pressure, or gas measurement. Check BME680 power, ground, SDA GPIO21, SCL GPIO22, and I²C address 0x76/0x77 before presenting live measurements or a real forecast alert.</p></section>'}
      <section class="live-sensors" aria-label="Latest wireless physical readings">
        ${sensorCard('BME680 · Temperature',reading(env.temperature_c,1,' °C'),!current.sample_observed_at?'Capture age unverified':fresh?'Latest Wi-Fi sample':'Last Wi-Fi sample · stale')}
        ${sensorCard('BME680 · Humidity',reading(env.humidity_pct,1,' %'),!current.sample_observed_at?'Capture age unverified':fresh?'Latest Wi-Fi sample':'Last Wi-Fi sample · stale')}
        ${sensorCard('BME680 · Pressure',reading(env.pressure_pa,0,' Pa'),!current.sample_observed_at?'Capture age unverified':fresh?'Latest Wi-Fi sample':'Last Wi-Fi sample · stale')}
        ${sensorCard('BME680 · Gas resistance',env.gas_valid?reading(env.gas_resistance_ohm,0,' Ω'):'Unavailable','Broad gas response · not a chemical identifier')}
        ${sensorCard('MQ-135 · Analog output',reading(env.gas_adc_raw,0,' raw'),'Uncalibrated ADC · not ppm')}
      </section>
      <section class="workspace-card live-route-card"><div class="live-section-title"><h2>Latest direct transmission</h2><span>${html(stamp(current.backend_stored_at))}</span></div><div class="live-path">
        <div><small>01 · Sensor ESP32</small><strong>${current.test_alert?'Transport test':'Sensor sample'}</strong><span>Event ${html(current.event_id)}</span></div>
        <div><small>02 · Wi-Fi</small><strong>Laptop receiver</strong><span>Exact event ID acknowledged after local journal commit</span></div>
        <div><small>03 · Backend</small><strong>SQLite stored</strong><span>${html(stamp(current.backend_stored_at))} local time</span></div>
        <div><small>04 · Bluetooth</small><strong>${current.bluetooth_stored?'Laptop receipt':'No receipt'}</strong><span>Fallback only when an alert lacks Wi-Fi ACK</span></div>
      </div></section>
      ${deliveryProofCard()}
      ${wirelessDeliveryTables()}
      ${wirelessReceiptCards()}
      <section class="workspace-card integration-control"><h2>Real transport test</h2><p>Reject Wi-Fi alert delivery at the laptop receiver, then send a labelled test alert from the ESP32. Bluetooth needs a paired laptop receiver.</p>
        <label class="workspace-check"><input id="direct-fault" type="checkbox" ${receiver?.wifi_fault?'checked':''} ${receiver?'':'disabled'}> Inject Wi-Fi receiver fault</label>
        <button type="button" class="workspace-button" id="direct-test" ${receiver?'':'disabled'}>Send transport test alert</button>
        <span id="direct-test-result" role="status">${receiver?`${receiver.laptop_stored} Wi-Fi events stored · ${receiver.backend_pending} awaiting backend`:'Laptop receiver unavailable'}</span>
      </section>
      <section class="workspace-card live-bt-card"><div class="live-section-title"><h2>Transport test events</h2><span>Labelled tests</span></div>${snapshot.direct_wifi_tests.length?snapshot.direct_wifi_tests.slice(0,5).map(event=>`<div class="live-bt-row"><code>${html(event.event_id)}</code><span>Wi-Fi laptop receipt · backend stored</span><strong>${html(stamp(event.backend_stored_at))}</strong></div>`).join(''):'<p>No transport test has reached the backend.</p>'}</section>
      <section class="workspace-card live-bt-card"><div class="live-section-title"><h2>Bluetooth alerts without Wi-Fi receipt</h2><span>Nearby laptop receipts</span></div>${btOnly||'<p>No Bluetooth-only alert receipt has been reported.</p>'}</section>
      <p class="live-provenance">Wi-Fi ACK means the laptop stored the exact event ID; backend storage is shown separately. Bluetooth storage requires a paired receiver and its own ACK. Transport tests are labelled and do not validate the forecast model.</p>`;
    target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
    target.querySelector('#direct-fault').addEventListener('change', async event => {
      try {
        const response = await fetch('/api/v1/live/direct/fault', {method:'POST',headers:{'Content-Type':'application/json','X-SafeSense-Control':'dashboard'},body:JSON.stringify({enabled:event.target.checked})});
        if (!response.ok) throw new Error(`Fault control returned HTTP ${response.status}`);
        await refresh(true);
      } catch (problem) { document.getElementById('direct-test-result').textContent = String(problem.message || problem); }
    });
    target.querySelector('#direct-test').addEventListener('click', async () => {
      const result = document.getElementById('direct-test-result');
      result.textContent = 'Requesting an ESP32 transport test alert…';
      try {
        const response = await fetch('/api/v1/live/direct/test-alert', {method:'POST',headers:{'X-SafeSense-Control':'dashboard'}});
        if (!response.ok) {
          const problemBody = await response.json().catch(() => ({}));
          throw new Error(problemBody.detail || `Test request returned HTTP ${response.status}`);
        }
        result.textContent = 'Test requested. Watch the Wi-Fi and Bluetooth receipts below.';
      } catch (problem) { result.textContent = String(problem.message || problem); }
    });
    appendTransportSwitcher(target);
  }

  function renderBluetooth(target) {
    const current = snapshot.latest;
    const env = current.environment || {};
    const fresh = snapshot.latest_fresh;
    const sensorReady = env.sensor_healthy === true;
    const alerts = (snapshot.direct_bt_only || []).map(receipt => `<div class="live-bt-row"><code>${html(receipt.event_id)}</code><span>${receipt.details.simulated?'Transport test':'Forecast alert'} · Bluetooth alert receipt</span><strong>${html(stamp(receipt.reported_at))}</strong></div>`).join('');
    document.getElementById('workspace-context').textContent = 'DIRECT BLUETOOTH';
    document.getElementById('workspace-subtitle').textContent = 'Physical sensor readings received through the paired laptop';
    document.getElementById('room-motto').textContent = 'REAL SENSOR DATA. BLUETOOTH DELIVERY.';
    document.getElementById('brand-tagline').textContent = 'DIRECT SENSOR TELEMETRY.';
    target.innerHTML = `
      <section class="live-head"><div><h2>Live BME680 + MQ-135 readings</h2><p>Sensor ESP32 → Bluetooth SPP → laptop journal → local backend. The laptop can remain on Amrita.</p></div><div class="live-head-side">${status(!current.sample_observed_at?'BLUETOOTH RECEIPT · SAMPLE AGE UNVERIFIED':!fresh?'STALE BLUETOOTH READING':sensorReady?'LIVE BLUETOOTH READING':'LIVE LINK · SENSOR UNAVAILABLE',fresh&&sensorReady?'good':'bad')}<small>${current.sample_observed_at?`${Math.round(snapshot.latest_age_seconds)}s since board capture`:`Received ${html(stamp(current.wireless_received_at))} · capture time unavailable`}</small>${refreshControls()}</div></section>
      ${exportCard()}
      ${sensorReady?'':'<section class="workspace-card live-sensor-warning" role="status"><strong>BME680 has no valid reading.</strong><p>The packet reached the laptop, but temperature, humidity, pressure, and gas values are unavailable. Check BME680 power, ground, SDA GPIO21, SCL GPIO22, and I²C address 0x76/0x77 before presenting live measurements or a real forecast alert.</p></section>'}
      <section class="live-sensors" aria-label="Latest Bluetooth physical readings">
        ${sensorCard('BME680 · Temperature',reading(env.temperature_c,1,' °C'),!current.sample_observed_at?'Capture age unverified':fresh?'Latest Bluetooth sample':'Last Bluetooth sample · stale')}
        ${sensorCard('BME680 · Humidity',reading(env.humidity_pct,1,' %'),!current.sample_observed_at?'Capture age unverified':fresh?'Latest Bluetooth sample':'Last Bluetooth sample · stale')}
        ${sensorCard('BME680 · Pressure',reading(env.pressure_pa,0,' Pa'),!current.sample_observed_at?'Capture age unverified':fresh?'Latest Bluetooth sample':'Last Bluetooth sample · stale')}
        ${sensorCard('BME680 · Gas resistance',env.gas_valid?reading(env.gas_resistance_ohm,0,' Ω'):'Unavailable','Broad gas response · not a chemical identifier')}
        ${sensorCard('MQ-135 · Analog output',reading(env.gas_adc_raw,0,' raw'),'Uncalibrated ADC · not ppm')}
      </section>
      <section class="workspace-card live-route-card"><div class="live-section-title"><h2>Latest Bluetooth sensor delivery</h2><span>${html(stamp(current.backend_stored_at))}</span></div><div class="live-path">
        <div><small>01 · Sensor ESP32</small><strong>Event ${html(current.event_id)}</strong><span>${sensorReady?'Physical sensor sample':'Sensor sample unavailable · board health false'}</span></div>
        <div><small>02 · Bluetooth</small><strong>Laptop journal stored</strong><span>Exact event ID acknowledged over SPP</span></div>
        <div><small>03 · Backend</small><strong>SQLite stored</strong><span>${html(stamp(current.backend_stored_at))} local time</span></div>
      </div></section>
      ${deliveryProofCard()}
      ${wirelessDeliveryTables()}
      ${wirelessReceiptCards()}
      <section class="workspace-card live-bt-card"><div class="live-section-title"><h2>Bluetooth alert receipts</h2><span>Separate from sensor samples</span></div>${alerts||'<p>No Bluetooth alert receipt has been reported.</p>'}</section>
      <p class="live-provenance">Bluetooth sensor storage is confirmed by the laptop journal before an exact-ID ACK. Backend storage is shown separately. These readings do not validate the synthetic forecast model.</p>`;
    target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
    appendTransportSwitcher(target);
  }

  function render() {
    const target = document.getElementById('workspace-body');
    if (!target) return;
    document.getElementById('top-time').textContent = snapshot
      ? `Live monitor · updated ${stamp(snapshot.as_of)}` : 'Live monitor · awaiting data';
    if (error) {
      target.innerHTML = `<div class="live-empty"><h2>Live monitor unavailable</h2><p>${html(error)}</p><button type="button" class="workspace-button" id="live-refresh">Try again</button></div>${exportCard()}`;
      target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
      return;
    }
    if (!snapshot) {
      target.innerHTML = `<div class="live-empty"><h2>Checking physical telemetry</h2><p>Waiting for the local backend response.</p></div>${exportCard()}`;
      return;
    }
    if (snapshot.latest?.route === 'DIRECT_WIFI') {
      renderWifi(target);
      return;
    }
    if (snapshot.latest?.route === 'DIRECT_BLUETOOTH') {
      renderBluetooth(target);
      return;
    }
    const current = snapshot.latest;
    const env = current?.environment || {};
    const fresh = snapshot.latest_fresh;
    const stateLabel = !current ? 'NO HARDWARE DATA' : fresh ? 'LIVE READING' : 'STALE READING';
    const stateClass = !current ? 'muted' : fresh ? 'good' : 'bad';
    const age = current ? `${Math.round(snapshot.latest_age_seconds)}s since backend storage` : 'No physical telemetry received yet';
    const eventRows = snapshot.events.map(event => {
      const sensor = event.environment || {};
      return `<tr><th scope="row"><code>${html(event.event_id)}</code><span class="live-small">${html(event.device_id)} · seq ${event.sequence ?? '—'}</span></th>
        <td>${html(stamp(event.backend_stored_at))}</td>
        <td>${html(reading(sensor.temperature_c,1,' °C'))}<span class="live-small">${html(reading(sensor.humidity_pct,1,' % RH'))}</span></td>
        <td>${status('Stored · RX reported','good')}<span class="live-small">${html(event.rx_device_id || 'RX ID unavailable')}</span></td>
        <td>${status('Stored','good')}</td>
        <td>${event.rx_forward_acked_at?status('Queue cleared','good'):status('Unconfirmed')}</td>
        <td>${event.bluetooth_stored_at?status('Laptop stored','good'):status('No receipt')}</td></tr>`;
    }).join('');
    const btOnly = snapshot.bluetooth_only.map(receipt => `<div class="live-bt-row"><code>${html(receipt.event_id)}</code><span>${html(receipt.details.room || 'Room unavailable')} · ${html(receipt.details.channel || 'Channel unavailable')}</span><strong>${html(stamp(receipt.reported_at))}</strong></div>`).join('');
    const latestPath = current ? `<div class="live-path">
      <div><small>01 · TX ESP32</small><strong>Event ${html(current.event_id)}</strong><span>Sequence ${current.sequence ?? 'unavailable'} · TX ACK state not observed here</span></div>
      <div><small>02 · Wi-Fi → RX</small><strong>Stored · RX reported</strong><span>${html(current.rx_device_id || 'RX ID unavailable')} · uptime ${current.rx_received_uptime_ms ?? '—'} ms</span></div>
      <div><small>03 · Laptop bridge</small><strong>${current.rx_forward_acked_at?'RX queue cleared':'Forward ACK unconfirmed'}</strong><span>Exact event ID ${html(current.event_id)}</span></div>
      <div><small>04 · Backend</small><strong>SQLite stored</strong><span>${html(stamp(current.backend_stored_at))} local time</span></div>
    </div>` : '<div class="live-empty inset"><h2>Waiting for a physical sensor sample</h2><p>Connect the ESP32 over Wi-Fi or Bluetooth and wait for a backend receipt. Synthetic scenario replay is excluded.</p></div>';
    target.innerHTML = `
      <section class="live-head"><div><h2>Physical sensor & delivery monitor</h2><p>Actual sensor readings stored by this backend; route evidence is shown separately.</p></div><div class="live-head-side">${status(stateLabel,stateClass)}<small>${html(age)}</small>${refreshControls()}</div></section>
      ${exportCard()}
      <section class="live-sensors" aria-label="Latest physical readings">
        ${sensorCard('BME680 · Temperature',reading(env.temperature_c,1,' °C'),current?(fresh?'Latest received reading':'Last received reading · stale'):'Awaiting telemetry')}
        ${sensorCard('BME680 · Humidity',reading(env.humidity_pct,1,' %'),current?(fresh?'Latest received reading':'Last received reading · stale'):'Awaiting telemetry')}
        ${sensorCard('BME680 · Pressure',reading(env.pressure_pa,0,' Pa'),current?(fresh?'Latest received reading':'Last received reading · stale'):'Awaiting telemetry')}
        ${sensorCard('BME680 · Gas resistance',env.gas_valid?reading(env.gas_resistance_ohm,0,' Ω'):'Unavailable',env.gas_valid?'Heater stable · broad response':'Gas reading invalid or unavailable')}
        ${sensorCard('MQ-135 · Analog output',reading(env.gas_adc_raw,0,' raw'),env.gas_adc_raw===0?'Zero signal · check sensor':'Uncalibrated ADC · not ppm')}
      </section>
      ${deliveryProofCard()}
      <section class="workspace-card live-route-card"><div class="live-section-title"><h2>Latest TX → RX transmission</h2><span>${current?html(stamp(current.backend_stored_at)):'No event yet'}</span></div>${latestPath}</section>
      <div class="workspace-two live-connectivity">
        ${bridgeCard('Wi-Fi RX bridge',snapshot.bridges.rx_http_bridge,'Laptop polling RX HTTP queue')}
        ${bridgeCard('Bluetooth receiver',snapshot.bridges.bt_alert_receiver,'Laptop COM listener; pairing not inferred')}
      </div>
      ${wirelessDeliveryTables()}
      ${wirelessReceiptCards()}
      <section class="workspace-card workspace-table-wrap live-history"><div class="live-section-title"><h2>Recent physical deliveries</h2><span>${snapshot.events.length} backend-stored event${snapshot.events.length===1?'':'s'}</span></div>
        ${eventRows?`<table class="workspace-table"><thead><tr><th>Event ID / TX sequence</th><th>Backend time</th><th>Sensor sample</th><th>RX NVS</th><th>Backend</th><th>RX forward ACK</th><th>Bluetooth</th></tr></thead><tbody>${eventRows}</tbody></table>`:'<p>No physical Wi-Fi delivery has reached the backend.</p>'}</section>
      <section class="workspace-card live-bt-card"><div class="live-section-title"><h2>Bluetooth alerts without matching Wi-Fi telemetry</h2><span>Nearby laptop receipts</span></div>${btOnly||'<p>No Bluetooth-only alert receipt has been reported.</p>'}</section>
      <p class="live-provenance">RX storage and queue state are reported by the RX bridge. Bluetooth storage is reported by the paired laptop receiver after journaling. This page cannot prove that TX heard the Wi-Fi ACK, that speech played, or that anyone outside this laptop received an alert. A stale value is never labeled live.</p>`;
    target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
    appendDirectTestPanel(target);
    appendTransportSwitcher(target);
  }

  async function refresh(manual=false) {
    if (busy) {
      if (manual) manualQueued = true;
      return;
    }
    const previousId = snapshot?.latest?.event_id;
    busy = true;
    if (manual) {
      refreshFeedback = 'Checking the backend for a new sensor sample…';
      if (timer) render();
    }
    try {
      const [response, directResponse, statusResponse, wifiSessionResponse, handoffResponse] = await Promise.all([
        fetch('/api/v1/live', {cache:'no-store'}),
        fetch('/api/v1/live/direct', {cache:'no-store'}),
        fetch('/api/v1/live/direct/status', {cache:'no-store'}),
        fetch('/api/v1/live/direct/wifi-session', {cache:'no-store'}),
        fetch('/api/v1/live/direct/transport-handoff', {cache:'no-store'}),
      ]);
      if (!response.ok || !directResponse.ok) throw new Error(`Backend returned HTTP ${response.status}/${directResponse.status}`);
      const physical = await response.json();
      const directWifi = await directResponse.json();
      const normalizeReceipts = receipts => (receipts||[]).map(receipt => ({...receipt,
        receipt_reported_at:utcStamp(receipt.receipt_reported_at)}));
      const directStatus = statusResponse.ok ? await statusResponse.json() : null;
      const wifiSession = wifiSessionResponse.ok ? await wifiSessionResponse.json() : null;
      const transportHandoff = handoffResponse.ok ? await handoffResponse.json() : null;
      const directEvents = directWifi.events.map(event => ({...event,
        backend_stored_at: utcStamp(event.backend_stored_at),
        wireless_received_at: utcStamp(event.wireless_received_at),
        sample_observed_at: utcStamp(event.sample_observed_at)}));
      const directPhysical = directEvents.filter(event => !event.test_alert);
      const directBluetooth = directPhysical.filter(event => event.route === 'DIRECT_BLUETOOTH');
      const directWifiPhysical = directPhysical.filter(event => event.route === 'DIRECT_WIFI');
      const directTests = directEvents.filter(event => event.test_alert);
      const combined = [...directWifiPhysical, ...directBluetooth, ...physical.events]
        .sort((a,b) => Date.parse(b.sample_observed_at||b.wireless_received_at||b.backend_stored_at)-Date.parse(a.sample_observed_at||a.wireless_received_at||a.backend_stored_at));
      const latest = combined[0] || null;
      const sampleTime = latest?.route === 'DIRECT_WIFI' || latest?.route === 'DIRECT_BLUETOOTH'
        ? latest.sample_observed_at : latest?.backend_stored_at;
      const latestAge = sampleTime ? Math.max(0,(Date.parse(physical.as_of)-Date.parse(sampleTime))/1000) : null;
      snapshot = {...physical, direct_wifi_tests:directTests,
                  board_queue:directWifi.board_queue ? {
                    ...directWifi.board_queue,
                    laptop_stored_at_utc:utcStamp(directWifi.board_queue.laptop_stored_at_utc),
                    backend_stored_at_utc:utcStamp(directWifi.board_queue.backend_stored_at_utc)} : null,
                  board_queue_history:(directWifi.board_queue_history||[]).map(row => ({...row,
                    backend_stored_at_utc:utcStamp(row.backend_stored_at_utc)})),
                  board_queue_proof:directWifi.board_queue_proof ? {
                    ...directWifi.board_queue_proof,
                    receiver_receipt_at:utcStamp(directWifi.board_queue_proof.receiver_receipt_at),
                    backend_stored_at:utcStamp(directWifi.board_queue_proof.backend_stored_at)} : null,
                  wifi_receipts:normalizeReceipts(directWifi.wifi_receipts),
                  bluetooth_receipts:normalizeReceipts(directWifi.bluetooth_receipts),
                  wifi_sensor_deliveries:normalizeReceipts(directWifi.wifi_sensor_deliveries),
                  bluetooth_sensor_deliveries:normalizeReceipts(directWifi.bluetooth_sensor_deliveries),
                  direct_bt_only:directWifi.bluetooth_only.map(receipt => ({...receipt,
                    reported_at: utcStamp(receipt.reported_at)})), direct_status:directStatus,
                  wifi_session:wifiSession, transport_handoff:transportHandoff,
                  events:physical.events, latest, latest_age_seconds:latestAge,
                  latest_fresh:latestAge !== null && latestAge <= physical.fresh_after_seconds};
      error = null;
      if (manual) {
        const checked = stamp(physical.as_of);
        refreshFeedback = !latest ? `Checked ${checked}: no physical sample has reached the backend.`
          : !snapshot.latest_fresh && latest.route === 'DIRECT_WIFI'
            ? `Checked ${checked}: latest Wi-Fi receipt ${stamp(latest.wireless_received_at)}; board capture age ${latest.sample_observed_at?'stale':'unverified'}.`
          : !snapshot.latest_fresh && latest.route === 'DIRECT_BLUETOOTH'
            ? `Checked ${checked}: latest Bluetooth receipt ${stamp(latest.wireless_received_at)}; board capture age ${latest.sample_observed_at?'stale':'unverified'}.`
          : !snapshot.latest_fresh ? `Checked ${checked}: no new wireless sensor data. Check the Wi-Fi or Bluetooth receiver.`
          : latest.event_id !== previousId ? `New sensor sample received at ${stamp(latest.backend_stored_at)}.`
          : `Checked ${checked}: waiting for the next sensor sample.`;
      } else if (refreshFeedback && latest?.event_id !== previousId && snapshot.latest_fresh) {
        refreshFeedback = `New sensor sample received at ${stamp(latest.backend_stored_at)}.`;
      }
    } catch (problem) {
      error = String(problem.message || problem);
    } finally {
      busy = false;
      if (timer) render();
      if (manualQueued && timer) {
        manualQueued = false;
        void refresh(true);
      }
    }
  }

  window.liveDashboard = {
    start() { if (!timer) { timer = setInterval(() => refresh(), 3000); refresh(); } },
    stop() { if (timer) clearInterval(timer); timer = null; manualQueued = false; },
    render,
  };
})();
