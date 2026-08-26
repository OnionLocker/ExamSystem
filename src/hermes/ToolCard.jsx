import { useEffect, useState } from 'react';

import { getToolActivity, thinkingActivity } from './toolActivity.js';

const ToolCard = ({ tool }) => {
  const [tick, setTick] = useState(0);
  const activity = tool && !tool.done ? getToolActivity(tool.name) : thinkingActivity();
  const frames = activity.frames;
  const emoji = frames[tick % frames.length];

  useEffect(() => {
    const id = setInterval(() => setTick((n) => n + 1), 380);
    return () => clearInterval(id);
  }, []);

  return (
    <div
      role="status"
      aria-label={`${activity.label}中`}
      className="hermes-working my-1.5 inline-flex items-center gap-1.5 rounded-full bg-black/[0.035] px-2.5 py-1 text-[11px] font-bold text-[#7b6a4a]"
    >
      <span aria-hidden="true" className="hermes-working-emoji text-[15px] leading-none">{emoji}</span>
      <span className="relative z-[1]">{activity.label}</span>
      <span className="relative z-[1] inline-flex items-end gap-[2px]" aria-hidden="true">
        {[0, 1, 2].map((i) => (
          <span key={i} className="hermes-working-dot" style={{ animationDelay: `${i * 160}ms` }} />
        ))}
      </span>
    </div>
  );
};

export default ToolCard;
