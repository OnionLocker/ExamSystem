import assert from 'node:assert/strict';
import { beijingNow, east8Today, parseBeijingMs } from '../src/lib/beijingTime.js';

const noonUtc = new Date('2026-09-03T04:00:00.000Z');
assert.equal(east8Today(noonUtc), '2026-09-03');
assert.equal(beijingNow(noonUtc), '2026-09-03 12:00:00');

assert.equal(parseBeijingMs('2026-09-03 15:47:06'), Date.parse('2026-09-03T15:47:06+08:00'));
assert.equal(parseBeijingMs('2026-09-03T07:47:06.000Z'), Date.parse('2026-09-03T07:47:06.000Z'));
assert.equal(parseBeijingMs('2026-09-03T04:15:30+08:00'), Date.parse('2026-09-03T04:15:30+08:00'));

const lateUtc = new Date('2026-09-03T16:30:00.000Z');
assert.equal(east8Today(lateUtc), '2026-09-04');
assert.equal(beijingNow(lateUtc), '2026-09-04 00:30:00');

console.log('beijing time: ok');
