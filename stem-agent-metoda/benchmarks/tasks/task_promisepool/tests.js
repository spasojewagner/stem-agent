const { PromisePool } = require('./solution.js');

let passed = 0; let failed = 0;
function test(name, fn) {
  try { fn(); console.log(`  [PASS] ${name}`); passed++; }
  catch(e) { console.log(`  [FAIL] ${name}: ${e.message}`); failed++; }
}
function assert(c, m) { if (!c) throw new Error(m || 'assertion failed'); }

// Longer delays = stable async tests, no timing flakiness
function delay(ms, val) {
  return () => new Promise(res => setTimeout(() => res(val), ms));
}

console.log('Task: Promise Pool\n');

async function run() {
  // Test 1: all tasks complete and results array has correct length
  const r1 = await new PromisePool([delay(50,'a'), delay(50,'b'), delay(50,'c')], 2).run();
  test('all tasks complete', () => assert(Array.isArray(r1) && r1.length === 3,
    `Expected array of 3, got ${JSON.stringify(r1)}`));

  // Test 2: results in original task order
  const r2 = await new PromisePool([delay(150,'a'), delay(50,'b'), delay(100,'c')], 3).run();
  test('results are in task order', () =>
    assert(r2[0]==='a' && r2[1]==='b' && r2[2]==='c',
      `Expected [a,b,c], got ${JSON.stringify(r2)}`));

  // Test 3: concurrency limit — track max simultaneous
  let concurrent = 0; let maxConcurrent = 0;
  const tasks3 = Array(6).fill(null).map(() => () => {
    concurrent++;
    maxConcurrent = Math.max(maxConcurrent, concurrent);
    return new Promise(res => setTimeout(() => { concurrent--; res(); }, 100));
  });
  await new PromisePool(tasks3, 2).run();
  test('concurrency limit respected (max 2)', () =>
    assert(maxConcurrent <= 2, `Max was ${maxConcurrent}, expected <= 2`));

  // Test 4: actually reaches full concurrency
  let concurrent4 = 0; let max4 = 0;
  const tasks4 = Array(6).fill(null).map(() => () => {
    concurrent4++;
    max4 = Math.max(max4, concurrent4);
    return new Promise(res => setTimeout(() => { concurrent4--; res(); }, 100));
  });
  await new PromisePool(tasks4, 3).run();
  test('uses full concurrency (reaches 3)', () =>
    assert(max4 >= 3, `Never reached 3, max was ${max4}`));

  // Test 5: empty task list
  const r5 = await new PromisePool([], 2).run();
  test('empty task list returns []', () =>
    assert(Array.isArray(r5) && r5.length === 0,
      `Expected [], got ${JSON.stringify(r5)}`));

  // Test 6: concurrency=1 must be strictly sequential
  const order = [];
  const tasks6 = ['a','b','c'].map(v => () =>
    new Promise(res => setTimeout(() => { order.push(v); res(v); }, 80))
  );
  await new PromisePool(tasks6, 1).run();
  test('concurrency=1 runs sequentially', () =>
    assert(JSON.stringify(order) === '["a","b","c"]',
      `Expected ["a","b","c"], got ${JSON.stringify(order)}`));

  // Test 7: large batch
  const tasks7 = Array(9).fill(null).map((_, i) => delay(30, i));
  const r7 = await new PromisePool(tasks7, 3).run();
  test('9 tasks with concurrency 3 all complete', () =>
    assert(r7.length === 9, `Expected 9, got ${r7.length}`));

  // Test 8: rejection propagates
  let threw = false;
  try {
    await new PromisePool([
      delay(50, 'ok'),
      () => new Promise((_, rej) => setTimeout(() => rej(new Error('boom')), 50)),
      delay(50, 'ok2')
    ], 2).run();
  } catch(e) { threw = true; }
  test('rejected task causes run() to reject', () =>
    assert(threw, 'Expected run() to throw on task rejection'));

  console.log(`\nResults: ${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

run().catch(e => { console.error('UNHANDLED:', e.message); process.exit(1); });
