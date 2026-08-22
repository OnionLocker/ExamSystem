// ============================================================
// 练习历史的读写
// ------------------------------------------------------------
// 每场的逐题 records 是体积大头（10 题约 1.4 KB），而整个 key 每次保存
// 都要整包 PUT 上云。之前统一砍到 100 场，实测两天就能刷满，更早的记录
// 连同汇总一起没了 —— 段位曲线、长期正确率都跟着断片。
//
// 现在分两档：最近 DETAIL_KEEP 场留逐题明细，供复盘和错因分析；
// 更早的只留汇总，汇总很轻，能留很久。
// ============================================================

import { cloudGet, cloudSet } from '../cloudStorage.js';

export const HISTORY_KEY = 'numeric_practice_history_v1';

const DETAIL_KEEP = 40;
const SUMMARY_KEEP = 600;

export const trimHistory = (list) =>
  list.slice(0, SUMMARY_KEEP).map((r, i) => {
    if (i < DETAIL_KEEP || !r.records) return r;
    const summary = { ...r };
    delete summary.records;
    return summary;
  });

export const loadHistory = () => cloudGet(HISTORY_KEY, []);

export const saveHistory = (list) => cloudSet(HISTORY_KEY, trimHistory(list));
