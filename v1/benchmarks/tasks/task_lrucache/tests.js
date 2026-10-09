const { LRUCache } = require('./solution.js');

let passed = 0; let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  [PASS] ${name}`); passed++; }
  catch(e) { console.log(`  [FAIL] ${name}: ${e.message}`); failed++; }
}
function assert(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

console.log('Task: LRU Cache\n');

test('get returns -1 for missing key', () => {
  const c = new LRUCache(2);
  assert(c.get('a') === -1, `Expected -1, got ${c.get('a')}`);
});

test('set and get basic value', () => {
  const c = new LRUCache(2);
  c.set('a', 1);
  assert(c.get('a') === 1, `Expected 1, got ${c.get('a')}`);
});

test('set overwrites existing key', () => {
  const c = new LRUCache(2);
  c.set('a', 1);
  c.set('a', 99);
  assert(c.get('a') === 99, `Expected 99, got ${c.get('a')}`);
});

test('evicts LRU item when full', () => {
  const c = new LRUCache(2);
  c.set('a', 1);
  c.set('b', 2);
  c.set('c', 3); // 'a' should be evicted
  assert(c.get('a') === -1, `'a' should be evicted, got ${c.get('a')}`);
});

test('evicted item is truly LRU not FIFO', () => {
  const c = new LRUCache(2);
  c.set('a', 1);
  c.set('b', 2);
  c.get('a');    // 'a' is now recently used
  c.set('c', 3); // 'b' should be evicted, not 'a'
  assert(c.get('a') === 1, `'a' should survive, got ${c.get('a')}`);
  assert(c.get('b') === -1, `'b' should be evicted, got ${c.get('b')}`);
});

test('get updates recency', () => {
  const c = new LRUCache(2);
  c.set('a', 1);
  c.set('b', 2);
  c.get('a');
  c.set('c', 3);
  assert(c.get('a') === 1, `'a' recency not updated on get`);
});

test('size 1 cache evicts on every new set', () => {
  const c = new LRUCache(1);
  c.set('a', 1);
  c.set('b', 2);
  assert(c.get('a') === -1, `'a' should be evicted`);
  assert(c.get('b') === 2, `'b' should be present`);
});

test('cache respects capacity exactly', () => {
  const c = new LRUCache(3);
  c.set('a', 1); c.set('b', 2); c.set('c', 3);
  c.set('d', 4); // evicts 'a'
  assert(c.get('b') === 2, `'b' should still be present`);
  assert(c.get('c') === 3, `'c' should still be present`);
  assert(c.get('d') === 4, `'d' should be present`);
  assert(c.get('a') === -1, `'a' should be evicted`);
});

test('set on existing key does not evict anything', () => {
  const c = new LRUCache(2);
  c.set('a', 1);
  c.set('b', 2);
  c.set('a', 99); // update, not new entry
  c.set('c', 3);  // now 'b' should be evicted (a was just used)
  assert(c.get('a') === 99, `'a' should be 99`);
  assert(c.get('b') === -1, `'b' should be evicted`);
});

test('independent caches do not share state', () => {
  const c1 = new LRUCache(2);
  const c2 = new LRUCache(2);
  c1.set('x', 1);
  assert(c2.get('x') === -1, `Caches share state!`);
});

console.log(`\nResults: ${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
