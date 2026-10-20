const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('live CSI view preserves a no-fresh-data response', async () => {
  const file = path.join(__dirname, '..', 'web', 'forecast', 'csi.js');
  const source = fs.readFileSync(file, 'utf8').replace(
    'window.csiCountDashboard={render,start,stop};',
    'window.csiCountDashboard={render,start,stop,testState:state,testFetch:fetchData};'
  );
  const context = {
    window: {},
    document: {getElementById: id => id === 'csi-error' ? {} : null},
    fetch: async () => ({ok: true, json: async () => ({
      source: 'NO_FRESH_LIVE_CSI', status: 'UNKNOWN', predicted_count: null,
      packet_count: 0, buffered_frames: 0,
    })}),
  };
  vm.runInNewContext(source, context);
  const dashboard = context.window.csiCountDashboard;
  dashboard.testState.mode = 'live';
  await dashboard.testFetch();
  assert.equal(dashboard.testState.result.source, 'NO_FRESH_LIVE_CSI');
  assert.equal(dashboard.testState.result.predicted_count, null);
});
