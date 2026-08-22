#!/usr/bin/env bash
# 由 examsystem-heat.timer 定时调用，把 Hermes 的学习对话折算成热力写进库。
#
# 以前这步只能手动跑，结果是：昨天明明学了，第二天打开仪表盘热力图还是空的，
# 得等人想起来执行一次。现在交给 systemd 定时，跟登录与否无关。
set -u
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$PROJECT_ROOT" || exit 1

# 凌晨那几次顺手把昨天封账：跨零点后昨天的对话才算齐
HOUR=$(date +%H)
if [ "$((10#$HOUR))" -lt 4 ]; then
  python3 scripts/daily_mentor_eval.py --date "$(date -d yesterday +%F)" || true
fi

python3 scripts/daily_mentor_eval.py || true
