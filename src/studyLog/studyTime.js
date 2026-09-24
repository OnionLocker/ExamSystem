const DAY_MS = 86400000;
const OFFSET_MS = 8 * 3600000;

export const studyDayKey = ts => new Date(ts + OFFSET_MS).toISOString().slice(0, 10);

export function validSegments(segments, now = Date.now()) {
  return Array.isArray(segments) && segments.length <= 10000 && segments.every(segment =>
    Array.isArray(segment) && segment.length === 2
    && segment.every(value => typeof value === 'number' && Number.isFinite(value))
    && segment[0] > 0 && segment[1] > segment[0]
    && segment[1] - segment[0] <= DAY_MS && segment[1] <= now + 60000);
}

export function mergeSegments(segments) {
  const merged = [];
  for (const [start, end] of [...segments].sort((a, b) => a[0] - b[0])) {
    const last = merged.at(-1);
    if (last && start <= last[1]) last[1] = Math.max(last[1], end);
    else merged.push([start, end]);
  }
  return merged;
}

export const segmentMinutes = segments => Math.round(
  mergeSegments(segments).reduce((sum, [start, end]) => sum + end - start, 0) / 6000,
) / 10;

export const emptyStudyDay = () => ({ minutes: 0, unknownCount: 0, entries: [], segments: [] });

export function closeTimerSegments(state, end) {
  const segments = state.timeSegments || [];
  return state.runStartedAt > 0 && end > state.runStartedAt
    ? [...segments, [state.runStartedAt, end]] : segments;
}

// Only measured intervals contribute to intensity. Legacy scores/minutes stay on the source entry.
export function aggregateStudyTime(entries, now = Date.now()) {
  const days = new Map();
  const seen = new Set();
  for (const entry of entries) {
    if (!entry || entry.preview || !Number.isFinite(entry.ts) || entry.ts <= 0 || entry.ts > now + DAY_MS) continue;
    const identity = entry.id == null ? null : `${entry.type}:${entry.id}`;
    if (identity && seen.has(identity)) continue;
    if (identity) seen.add(identity);
    const completionDay = entry.day || studyDayKey(Math.min(entry.ts, now));
    if (!/^\d{4}-\d{2}-\d{2}$/.test(completionDay)) continue;
    const segments = validSegments(entry.timeSegments, now) ? mergeSegments(entry.timeSegments) : [];
    const parts = new Map([[completionDay, []]]);
    for (const [from, end] of segments) {
      let start = from;
      while (start < end) {
        const boundary = (Math.floor((start + OFFSET_MS) / DAY_MS) + 1) * DAY_MS - OFFSET_MS;
        const stop = Math.min(end, boundary);
        const key = studyDayKey(start);
        if (!parts.has(key)) parts.set(key, []);
        parts.get(key).push([start, stop]);
        start = stop;
      }
    }
    for (const [key, intervals] of parts) {
      if (!days.has(key)) days.set(key, emptyStudyDay());
      const day = days.get(key);
      day.segments.push(...intervals);
      const timed = segments.length > 0;
      if (!timed) day.unknownCount += 1;
      day.entries.push({ ...entry, sourceEntry: entry, timeSegments: intervals,
        measuredMinutes: segmentMinutes(intervals), timingKnown: timed,
        ...(key !== completionDay ? { count: 0, correct: null, firstCount: 0, repeatCount: 0 } : {}),
      });
    }
  }
  for (const day of days.values()) {
    day.segments = mergeSegments(day.segments);
    day.minutes = segmentMinutes(day.segments);
  }
  return days;
}

export function timeLevel(minutes) {
  if (!(minutes > 0)) return 0;
  return [30, 60, 120, 180, 240, 360, 480].filter(limit => minutes >= limit).length + 1;
}

export function studyOutputs(entries) {
  return entries.reduce((out, entry) => {
    const count = Math.max(0, Number(entry.count) || 0);
    if (entry.module === '申论') out.writing += count;
    else if (entry.type === 'review') out.reviewed += count;
    else if (['aiquiz', 'numeric', 'import', 'vocab'].includes(entry.type)) {
      out.answered += entry.type === 'numeric' ? Math.max(0, count - (Number(entry.skipped) || 0)) : count;
    }
    out.first += Number(entry.firstCount) || 0;
    out.repeat += Number(entry.repeatCount) || 0;
    return out;
  }, { answered: 0, reviewed: 0, writing: 0, first: 0, repeat: 0 });
}
