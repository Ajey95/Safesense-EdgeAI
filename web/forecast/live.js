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

  function renderDirect(target) {
    const current = snapshot.latest;
    const env = current.environment || {};
    const fresh = snapshot.latest_fresh;
    const rows = snapshot.direct_events.slice(0, 10).map(event => {
      const sensor = event.environment;
      return `<tr><th scope="row"><code>${html(event.event_id)}</code></th><td>${html(stamp(event.backend_stored_at))}</td>
        <td>${html(reading(sensor.temperature_c,2,' °C'))}</td><td>${html(reading(sensor.humidity_pct,2,' %'))}</td>
        <td>${html(reading(sensor.pressure_pa,0,' Pa'))}</td><td>${html(reading(sensor.gas_resistance_ohm,0,' Ω'))}</td>
        <td>${html(reading(sensor.gas_adc_raw,0,' raw'))}</td></tr>`;
    }).join('');
    document.getElementById('workspace-context').textContent = 'DIRECT USB';
    document.getElementById('workspace-subtitle').textContent = 'Physical sensor readings and local backend storage';
    document.getElementById('room-motto').textContent = 'REAL SENSOR DATA. DIRECT TO DASHBOARD.';
    document.getElementById('brand-tagline').textContent = 'DIRECT SENSOR TELEMETRY.';
    target.innerHTML = `
      <section class="live-head"><div><h2>Live BME680 + MQ-135 readings</h2><p>Physical sensor ESP32 → USB serial → laptop bridge → local SafeSense backend.</p></div><div class="live-head-side">${status(fresh?'LIVE USB READING':'STALE USB READING',fresh?'good':'bad')}<small>${Math.round(snapshot.latest_age_seconds)}s since backend storage</small>${refreshControls()}</div></section>
      <section class="live-sensors" aria-label="Latest direct physical readings">
        ${sensorCard('BME680 · Temperature',reading(env.temperature_c,1,' °C'),fresh?'Latest USB sensor sample':'Last USB sample · stale')}
        ${sensorCard('BME680 · Humidity',reading(env.humidity_pct,1,' %'),fresh?'Latest USB sensor sample':'Last USB sample · stale')}
        ${sensorCard('BME680 · Pressure',reading(env.pressure_pa,0,' Pa'),fresh?'Latest USB sensor sample':'Last USB sample · stale')}
        ${sensorCard('BME680 · Gas resistance',reading(env.gas_resistance_ohm,0,' Ω'),'Broad gas response · heater stability unverified')}
        ${sensorCard('MQ-135 · Analog output',reading(env.gas_adc_raw,0,' raw'),'Uncalibrated ADC · not ppm')}
      </section>
      <section class="workspace-card live-route-card"><div class="live-section-title"><h2>Latest direct transmission</h2><span>${html(stamp(current.backend_stored_at))}</span></div><div class="live-path">
        <div><small>01 · Sensor ESP32</small><strong>BME680 + MQ-135</strong><span>Board reports sensor status OK</span></div>
        <div><small>02 · USB serial</small><strong>Direct cable</strong><span>No RX ESP32 in this route</span></div>
        <div><small>03 · Laptop bridge</small><strong>JSON sample accepted</strong><span>Sample ${html(current.event_id)} · no durable queue claim</span></div>
        <div><small>04 · Backend</small><strong>SQLite stored</strong><span>${html(stamp(current.backend_stored_at))} local time</span></div>
      </div></section>
      <div class="workspace-two live-connectivity">
        <article class="workspace-card live-bridge"><small>USB sensor feed</small><strong>${fresh?'Receiving samples':'Sample stream stale'}</strong><span>COM port read by local bridge; backend event ID confirmed.</span></article>
        <article class="workspace-card live-bridge"><small>Forecast and alerts</small><strong>Not validated by this feed</strong><span>Scenario forecast remains synthetic; MQ-135 is raw ADC.</span></article>
      </div>
      <section class="workspace-card workspace-table-wrap live-history"><div class="live-section-title"><h2>Recent direct sensor samples</h2><span>${Math.min(snapshot.direct_events.length,10)} stored sample${snapshot.direct_events.length===1?'':'s'} shown</span></div>
        <table class="workspace-table"><thead><tr><th>Event ID</th><th>Backend time</th><th>Temperature</th><th>Humidity</th><th>Pressure</th><th>BME680 gas</th><th>MQ-135</th></tr></thead><tbody>${rows}</tbody></table>
      </section>
      <p class="live-provenance">These values are reported by the connected sensor board through the laptop USB bridge and stored by the local backend. This route makes no Wi-Fi RX, Bluetooth, or emergency delivery claim. A stale value is never labeled live.</p>`;
    target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
  }

  function render() {
    const target = document.getElementById('workspace-body');
    if (!target) return;
    document.getElementById('top-time').textContent = snapshot
      ? `Live monitor · updated ${stamp(snapshot.as_of)}` : 'Live monitor · awaiting data';
    if (error) {
      target.innerHTML = `<div class="live-empty"><h2>Live monitor unavailable</h2><p>${html(error)}</p><button type="button" class="workspace-button" id="live-refresh">Try again</button></div>`;
      target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
      return;
    }
    if (!snapshot) {
      target.innerHTML = '<div class="live-empty"><h2>Checking physical telemetry</h2><p>Waiting for the local backend response.</p></div>';
      return;
    }
    if (snapshot.latest?.route === 'USB_SERIAL') {
      renderDirect(target);
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
    </div>` : '<div class="live-empty inset"><h2>Waiting for a physical sensor sample</h2><p>Start the USB serial bridge for direct readings or the RX bridge for Wi-Fi delivery. Synthetic scenario replay is excluded.</p></div>';
    target.innerHTML = `
      <section class="live-head"><div><h2>Physical sensor & delivery monitor</h2><p>Actual sensor readings stored by this backend; route evidence is shown separately.</p></div><div class="live-head-side">${status(stateLabel,stateClass)}<small>${html(age)}</small>${refreshControls()}</div></section>
      <section class="live-sensors" aria-label="Latest physical readings">
        ${sensorCard('BME680 · Temperature',reading(env.temperature_c,1,' °C'),current?(fresh?'Latest received reading':'Last received reading · stale'):'Awaiting telemetry')}
        ${sensorCard('BME680 · Humidity',reading(env.humidity_pct,1,' %'),current?(fresh?'Latest received reading':'Last received reading · stale'):'Awaiting telemetry')}
        ${sensorCard('BME680 · Pressure',reading(env.pressure_pa,0,' Pa'),current?(fresh?'Latest received reading':'Last received reading · stale'):'Awaiting telemetry')}
        ${sensorCard('BME680 · Gas resistance',env.gas_valid?reading(env.gas_resistance_ohm,0,' Ω'):'Unavailable',env.gas_valid?'Heater stable · broad response':'Gas reading invalid or unavailable')}
        ${sensorCard('MQ-135 · Analog output',reading(env.gas_adc_raw,0,' raw'),env.gas_adc_raw===0?'Zero signal · check sensor':'Uncalibrated ADC · not ppm')}
      </section>
      <section class="workspace-card live-route-card"><div class="live-section-title"><h2>Latest TX → RX transmission</h2><span>${current?html(stamp(current.backend_stored_at)):'No event yet'}</span></div>${latestPath}</section>
      <div class="workspace-two live-connectivity">
        ${bridgeCard('Wi-Fi RX bridge',snapshot.bridges.rx_http_bridge,'Laptop polling RX HTTP queue')}
        ${bridgeCard('Bluetooth receiver',snapshot.bridges.bt_alert_receiver,'Laptop COM listener; pairing not inferred')}
      </div>
      <section class="workspace-card workspace-table-wrap live-history"><div class="live-section-title"><h2>Recent physical deliveries</h2><span>${snapshot.events.length} backend-stored event${snapshot.events.length===1?'':'s'}</span></div>
        ${eventRows?`<table class="workspace-table"><thead><tr><th>Event ID / TX sequence</th><th>Backend time</th><th>Sensor sample</th><th>RX NVS</th><th>Backend</th><th>RX forward ACK</th><th>Bluetooth</th></tr></thead><tbody>${eventRows}</tbody></table>`:'<p>No physical Wi-Fi delivery has reached the backend.</p>'}</section>
      <section class="workspace-card live-bt-card"><div class="live-section-title"><h2>Bluetooth alerts without matching Wi-Fi telemetry</h2><span>Nearby laptop receipts</span></div>${btOnly||'<p>No Bluetooth-only alert receipt has been reported.</p>'}</section>
      <p class="live-provenance">RX storage and queue state are reported by the RX bridge. Bluetooth storage is reported by the paired laptop receiver after journaling. This page cannot prove that TX heard the Wi-Fi ACK, that speech played, or that anyone outside this laptop received an alert. A stale value is never labeled live.</p>`;
    target.querySelector('#live-refresh').addEventListener('click', () => refresh(true));
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
      const [response, overviewResponse] = await Promise.all([
        fetch('/api/v1/live', {cache:'no-store'}),
        fetch('/api/v1/overview', {cache:'no-store'}),
      ]);
      if (!response.ok || !overviewResponse.ok) throw new Error(`Backend returned HTTP ${response.status}/${overviewResponse.status}`);
      const physical = await response.json();
      const overview = await overviewResponse.json();
      const direct = (overview.telemetry || [])
        .filter(row => row.device_id === 'safesense-tx-usb-8c94df901fec' && row.payload?.firmware_version === 'direct-serial-bme680-mq135')
        .map(row => ({event_id:row.event_id, device_id:row.device_id, backend_stored_at:utcStamp(row.received_at),
                      environment:row.payload.environment, route:'USB_SERIAL'}));
      const combined = [...direct, ...physical.events].sort((a,b) => Date.parse(b.backend_stored_at)-Date.parse(a.backend_stored_at));
      const latest = combined[0] || null;
      const latestAge = latest ? Math.max(0,(Date.parse(physical.as_of)-Date.parse(latest.backend_stored_at))/1000) : null;
      snapshot = {...physical, direct_events:direct, events:physical.events, latest, latest_age_seconds:latestAge,
                  latest_fresh:latestAge !== null && latestAge <= physical.fresh_after_seconds};
      error = null;
      if (manual) {
        const checked = stamp(physical.as_of);
        refreshFeedback = !latest ? `Checked ${checked}: no physical sample has reached the backend.`
          : !snapshot.latest_fresh ? `Checked ${checked}: no new sensor data. Check the sensor COM port and USB bridge.`
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
