import { avgRemaining, combineQuota } from '../src/hermes/quotaMath.js';

const assert = (ok, msg) => {
  if (!ok) throw new Error(msg);
};

assert(avgRemaining([0.95, 0.92]) === 0.935, 'avg 5h');
assert(avgRemaining([0.99, 0.82]) === 0.905, 'avg week');

const combined = combineQuota([
  {
    email: 'russellyuan168@x',
    groups: [
      {
        name: 'GEMINI MODELS',
        buckets: [
          { window: '5h', remaining: 0.95 },
          { window: 'weekly', remaining: 0.99 },
        ],
      },
      {
        name: 'CLAUDE AND GPT MODELS',
        buckets: [
          { window: '5h', remaining: 1 },
          { window: 'weekly', remaining: 1 },
        ],
      },
    ],
  },
  {
    email: 'russellywc@x',
    groups: [
      {
        name: 'GEMINI MODELS',
        buckets: [
          { window: '5h', remaining: 0.92 },
          { window: 'weekly', remaining: 0.82 },
        ],
      },
    ],
  },
]);

assert(combined.accountCount === 2, 'two live accounts');
assert(combined.preferred?.name === 'GEMINI MODELS', 'prefer gemini');
assert(Math.round(combined.headline[0].remaining * 100) === 94, 'combined 5h');
assert(Math.round(combined.headline[1].remaining * 100) === 91, 'combined week');
console.log('quota math: ok');
