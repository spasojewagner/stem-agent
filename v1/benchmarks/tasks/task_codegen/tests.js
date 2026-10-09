const { EventBus } = require('./solution.js');

let passed = 0; let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  [PASS] ${name}`); passed++; }
  catch (e) { console.log(`  [FAIL] ${name}: ${e.message}`); failed++; }
}
async function testAsync(name, fn) {
  try { await fn(); console.log(`  [PASS] ${name}`); passed++; }
  catch (e) { console.log(`  [FAIL] ${name}: ${e.message}`); failed++; }
}
function assert(cond, msg) { if (!cond) throw new Error(msg || 'Assertion failed'); }

console.log('Task codegen: EventBus\n');

// --- Basic pub/sub ---
test('subscriber receives published event', () => {
  const bus = new EventBus();
  let got = null;
  bus.on('msg', (data) => { got = data; });
  bus.emit('msg', 42);
  assert(got === 42, `Expected 42, got ${got}`);
});

test('multiple subscribers all receive event', () => {
  const bus = new EventBus();
  let a = 0, b = 0;
  bus.on('x', () => a++);
  bus.on('x', () => b++);
  bus.emit('x');
  assert(a === 1 && b === 1, `a=${a} b=${b}`);
});

test('different events do not cross-fire', () => {
  const bus = new EventBus();
  let count = 0;
  bus.on('a', () => count++);
  bus.emit('b');
  assert(count === 0, `Expected 0, got ${count}`);
});

// --- Unsubscribe ---
test('off() removes a specific listener', () => {
  const bus = new EventBus();
  let count = 0;
  const handler = () => count++;
  bus.on('e', handler);
  bus.off('e', handler);
  bus.emit('e');
  assert(count === 0, `Expected 0 after off(), got ${count}`);
});

test('off() removes only the specified listener, not others', () => {
  const bus = new EventBus();
  let a = 0, b = 0;
  const ha = () => a++;
  const hb = () => b++;
  bus.on('e', ha);
  bus.on('e', hb);
  bus.off('e', ha);
  bus.emit('e');
  assert(a === 0 && b === 1, `a=${a} b=${b}`);
});

test('off() on non-existent event does not throw', () => {
  const bus = new EventBus();
  bus.off('ghost', () => {});
});

// --- once() ---
test('once() fires exactly once', () => {
  const bus = new EventBus();
  let count = 0;
  bus.once('ping', () => count++);
  bus.emit('ping');
  bus.emit('ping');
  bus.emit('ping');
  assert(count === 1, `Expected 1, got ${count}`);
});

test('once() receives correct data', () => {
  const bus = new EventBus();
  let got = null;
  bus.once('val', (v) => { got = v; });
  bus.emit('val', 'hello');
  assert(got === 'hello', `Expected hello, got ${got}`);
});

// --- Error isolation ---
test('throwing listener does not prevent other listeners from firing', () => {
  const bus = new EventBus();
  let reached = false;
  bus.on('e', () => { throw new Error('intentional'); });
  bus.on('e', () => { reached = true; });
  try { bus.emit('e'); } catch (_) {}
  assert(reached, 'Second listener was never called');
});

// --- Edge cases ---
test('emit with no subscribers does not throw', () => {
  const bus = new EventBus();
  bus.emit('nobody-home', { data: 1 });
});

test('listener count returns correct number', () => {
  const bus = new EventBus();
  bus.on('e', () => {});
  bus.on('e', () => {});
  const count = bus.listenerCount('e');
  assert(count === 2, `Expected 2, got ${count}`);
});

test('listenerCount returns 0 for unknown event', () => {
  const bus = new EventBus();
  const count = bus.listenerCount('unknown');
  assert(count === 0, `Expected 0, got ${count}`);
});

test('listeners added during emit do not fire in same emit cycle', () => {
  const bus = new EventBus();
  let extra = 0;
  bus.on('e', () => {
    bus.on('e', () => { extra++; });
  });
  bus.emit('e');
  assert(extra === 0, `Expected 0, got ${extra}`);
});

test('removeAllListeners() clears all listeners for event', () => {
  const bus = new EventBus();
  let count = 0;
  bus.on('e', () => count++);
  bus.on('e', () => count++);
  bus.removeAllListeners('e');
  bus.emit('e');
  assert(count === 0, `Expected 0, got ${count}`);
});

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
