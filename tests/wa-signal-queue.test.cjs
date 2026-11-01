const test = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const queue = require(process.env.WA_SIGNAL_QUEUE_PATH || '/app/node_modules/libsignal/src/queue_job.js');

test('a burst of Signal crypto jobs preserves FIFO and permits network heartbeat before the queue ends', async () => {
  const count = 160, order = [], key = Buffer.alloc(32, 1);
  let completed = 0, heartbeatAt = null, inFlight = 0;
  setImmediate(() => { heartbeatAt = completed; });
  const tasks = Array.from({ length: count }, (_, index) => queue('regression-peer.0', async () => {
    assert.equal(inFlight++, 0);
    for (let n = 0; n < 25; n++) crypto.createHmac('sha256', key).update('synthetic regression data').digest();
    await Promise.resolve();
    order.push(index); completed++; inFlight--;
    return index;
  }));
  const values = await Promise.all(tasks);
  assert.deepEqual(order, Array.from({ length: count }, (_, i) => i));
  assert.deepEqual(values, order);
  assert.ok(heartbeatAt !== null && heartbeatAt < count,
    'network I/O was starved until every queued crypto job completed');
});

test('a failed Signal job does not overlap or suppress the next job', async () => {
  const order = [];
  const failed = queue('regression-error.0', async () => { order.push('failed'); throw new Error('expected synthetic failure'); });
  const next = queue('regression-error.0', async () => { order.push('next'); return 'ok'; });
  await assert.rejects(failed, /expected synthetic failure/);
  assert.equal(await next, 'ok');
  assert.deepEqual(order, ['failed', 'next']);
});
