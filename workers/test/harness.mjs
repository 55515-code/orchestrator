// Minimal test harness for worker tests. Node >= 18 required.
let passed = 0;
let failed = 0;
const failures = [];

export function test(name, fn) {
  tests.push({ name, fn });
}

const tests = [];

export async function run() {
  for (const { name, fn } of tests) {
    try {
      await fn();
      passed += 1;
      console.log(`  ok  ${name}`);
    } catch (error) {
      failed += 1;
      failures.push({ name, error });
      console.log(`FAIL  ${name}`);
      console.log(`      ${error.message}`);
    }
  }
  console.log(`\n${passed} passed, ${failed} failed`);
  if (failed > 0) process.exit(1);
}
