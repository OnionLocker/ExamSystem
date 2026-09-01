import { cloudGet, cloudSet } from '../cloudStorage.js';
import { loadStats } from './ranks.js';
import { wrongCountsBySub } from './wrongPool.js';
import {
  applyRaceToTasks,
  buildNumericTodayTasks,
  east8Today,
  fillMissingCategoryTasks,
  litCategoryIds,
  NUMERIC_TODAY_TASK_LIMIT,
} from './numericTodayPlan.js';

export const TODAY_TASKS_REFRESH_EVENT = 'today-tasks-refresh';
const STORAGE_KEY = 'numeric_today_tasks_v1';

export const normalizeTaskRoute = (task) => ({
  catId: task?.catId || task?.cat_id || task?.route?.catId,
  subId: task?.subId || task?.sub_id || task?.route?.subId,
});

const readState = () => cloudGet(STORAGE_KEY, null);

const writeState = (state) => {
  cloudSet(STORAGE_KEY, state);
  window.dispatchEvent(new Event(TODAY_TASKS_REFRESH_EVENT));
  return state.items;
};

const rebuild = (date) => {
  const items = buildNumericTodayTasks({
    date,
    stats: loadStats(),
    wrongCounts: wrongCountsBySub(),
  });
  return writeState({ date, items });
};

const hasProgress = (items) =>
  items.some((task) => task.status !== 'pending' || task.lastRace);

const persistIfGrown = (date, items, next) => {
  if (next.length === items.length) return items;
  return writeState({ date, items: next });
};

export const loadTodayNumericTasks = () => {
  const date = east8Today();
  const state = readState();
  const items = state?.date === date && Array.isArray(state.items) ? state.items : [];
  if (!items.length) return rebuild(date);
  if (items.length < NUMERIC_TODAY_TASK_LIMIT && !hasProgress(items)) return rebuild(date);
  return persistIfGrown(date, items, fillMissingCategoryTasks(items, {
    date,
    stats: loadStats(),
    wrongCounts: wrongCountsBySub(),
  }));
};

export const refreshPendingTodayTasks = () => {
  const date = east8Today();
  const state = readState();
  if (state?.date === date && hasProgress(state.items || [])) {
    return loadTodayNumericTasks();
  }
  return rebuild(date);
};

export const getTodayTasks = async () => loadTodayNumericTasks();

export const applyNumericTodayRace = (race) => {
  const date = east8Today();
  const current = readState();
  const items = current?.date === date && Array.isArray(current.items)
    ? current.items
    : buildNumericTodayTasks({
      date,
      stats: loadStats(),
      wrongCounts: wrongCountsBySub(),
    });
  const { tasks, changed } = applyRaceToTasks(items, race);
  if (!changed) return items;
  return writeState({ date, items: tasks });
};

export const litTodayCategoryIds = () => litCategoryIds(loadTodayNumericTasks());
