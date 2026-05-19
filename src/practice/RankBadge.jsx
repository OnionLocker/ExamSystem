// ============================================================
// 段位徽章 SVG（重设计版 v2）
// --------------------------------------
// 设计语言（参考主流游戏的段位视觉系统）：
//   - 八角形宝石底座（取代旧六边形），带分层渐变和高光，金属质感
//   - 每个段位有标志性中心图形：盾 → 双 V → 桂冠+星 → 八面切钻 → 多刃光芒 → 皇冠 → 凤凰焰
//   - 钻石及以上加径向发光晕环；王者再加流动火焰
//   - 全部矢量绘制，无外部素材依赖
// ============================================================
import { getRank } from './ranks.js';

// 八角形顶点：cx,cy 为中心，r 为外接圆半径
function octPoints(cx, cy, r) {
  const pts = [];
  for (let i = 0; i < 8; i++) {
    const a = (Math.PI / 4) * i - Math.PI / 8; // 上方两个角对称
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
}

// 星形顶点
function starPoints(cx, cy, rOuter, rInner, n) {
  const pts = [];
  for (let i = 0; i < n * 2; i++) {
    const a = (Math.PI / n) * i - Math.PI / 2;
    const r = i % 2 === 0 ? rOuter : rInner;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
}

// 盾牌路径（用于青铜/白银等）
function shieldPath(w, h) {
  return `M ${w / 2} 0 L ${w} ${h * 0.18} L ${w} ${h * 0.55} Q ${w} ${h * 0.85} ${w / 2} ${h} Q 0 ${h * 0.85} 0 ${h * 0.55} L 0 ${h * 0.18} Z`;
}

// 通用底座（八角形宝石 + 内描边 + 高光）
const Base = ({ size, gradId, edgeColor, glowColor }) => {
  const s = size;
  const cx = s / 2;
  const cy = s / 2;
  const r = s / 2 - 2;
  return (
    <>
      {glowColor && (
        <circle
          cx={cx}
          cy={cy}
          r={r}
          fill={glowColor}
          opacity="0.28"
          filter={`blur(${s / 7}px)`}
        />
      )}
      <polygon
        points={octPoints(cx, cy, r)}
        fill={`url(#${gradId})`}
        stroke={edgeColor}
        strokeWidth={s * 0.04}
        strokeLinejoin="round"
      />
      {/* 内描边，制造金属厚度 */}
      <polygon
        points={octPoints(cx, cy, r * 0.86)}
        fill="none"
        stroke={edgeColor}
        strokeWidth={s * 0.012}
        strokeLinejoin="round"
        opacity="0.6"
      />
      {/* 顶部高光弧 */}
      <path
        d={`M ${cx - r * 0.55} ${cy - r * 0.55} Q ${cx} ${cy - r * 0.85} ${cx + r * 0.55} ${cy - r * 0.55}`}
        stroke="rgba(255,255,255,0.4)"
        strokeWidth={s * 0.025}
        strokeLinecap="round"
        fill="none"
      />
    </>
  );
};

// ---------------- 各段位中心图形 ----------------

// 未评级：纯色圆 + 居中粗体问号（非斜体）
const UnrankedIcon = ({ size }) => {
  const s = size;
  return (
    <g>
      <circle cx={s / 2} cy={s / 2} r={s / 2 - 2} fill="#eef2f6" stroke="#cbd5e1" strokeWidth={s * 0.025} />
      <circle cx={s / 2} cy={s / 2} r={(s / 2 - 2) * 0.78} fill="none" stroke="#cbd5e1" strokeWidth={s * 0.012} strokeDasharray={`${s * 0.05} ${s * 0.04}`} />
      <text
        x={s / 2}
        y={s / 2 + s * 0.13}
        textAnchor="middle"
        fill="#94a3b8"
        fontSize={s * 0.42}
        fontWeight="900"
        fontFamily="ui-sans-serif, system-ui"
      >
        ?
      </text>
    </g>
  );
};

// 青铜：盾牌 + 单 V 形向上箭
const BronzeIcon = ({ size }) => {
  const s = size;
  return (
    <g transform={`translate(${s * 0.26}, ${s * 0.22})`}>
      <path d={shieldPath(s * 0.48, s * 0.56)} fill="#a17b5d" stroke="#5d3f25" strokeWidth={s * 0.022} />
      <path d={shieldPath(s * 0.48, s * 0.56)} fill="url(#bronzeShine)" opacity="0.45" />
      {/* 单 V */}
      <path
        d={`M ${s * 0.08} ${s * 0.20} L ${s * 0.24} ${s * 0.36} L ${s * 0.40} ${s * 0.20}`}
        fill="none"
        stroke="#3d2817"
        strokeWidth={s * 0.05}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
};

// 白银：盾 + 双 V
const SilverIcon = ({ size }) => {
  const s = size;
  return (
    <g transform={`translate(${s * 0.26}, ${s * 0.22})`}>
      <path d={shieldPath(s * 0.48, s * 0.56)} fill="#d4dae3" stroke="#5b6473" strokeWidth={s * 0.022} />
      <path d={shieldPath(s * 0.48, s * 0.56)} fill="url(#silverShine)" opacity="0.65" />
      {/* 双 V */}
      <path
        d={`M ${s * 0.08} ${s * 0.16} L ${s * 0.24} ${s * 0.30} L ${s * 0.40} ${s * 0.16}`}
        fill="none"
        stroke="#3d4556"
        strokeWidth={s * 0.045}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d={`M ${s * 0.08} ${s * 0.30} L ${s * 0.24} ${s * 0.44} L ${s * 0.40} ${s * 0.30}`}
        fill="none"
        stroke="#3d4556"
        strokeWidth={s * 0.045}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </g>
  );
};

// 黄金：盾 + 桂冠夹星
const GoldIcon = ({ size }) => {
  const s = size;
  return (
    <g>
      <g transform={`translate(${s * 0.26}, ${s * 0.22})`}>
        <path d={shieldPath(s * 0.48, s * 0.56)} fill="#fbc02d" stroke="#7a5400" strokeWidth={s * 0.022} />
        <path d={shieldPath(s * 0.48, s * 0.56)} fill="url(#goldShine)" opacity="0.55" />
      </g>
      {/* 中心五角星 */}
      <polygon
        points={starPoints(s / 2, s / 2 + s * 0.02, s * 0.16, s * 0.07, 5)}
        fill="#7a5400"
        stroke="#fde68a"
        strokeWidth={s * 0.012}
        strokeLinejoin="round"
      />
      {/* 左右桂冠（简化为两条弧形叶） */}
      <path
        d={`M ${s * 0.20} ${s * 0.55} Q ${s * 0.10} ${s * 0.50} ${s * 0.18} ${s * 0.36} Q ${s * 0.28} ${s * 0.46} ${s * 0.20} ${s * 0.55} Z`}
        fill="#7a5400"
        opacity="0.7"
      />
      <path
        d={`M ${s * 0.80} ${s * 0.55} Q ${s * 0.90} ${s * 0.50} ${s * 0.82} ${s * 0.36} Q ${s * 0.72} ${s * 0.46} ${s * 0.80} ${s * 0.55} Z`}
        fill="#7a5400"
        opacity="0.7"
      />
    </g>
  );
};

// 铂金：八面切钻（六边形钻石视图）
const PlatinumIcon = ({ size }) => {
  const s = size;
  const cx = s / 2;
  const cy = s / 2;
  const w = s * 0.40;
  const h = s * 0.46;
  // 钻石轮廓：上宽下尖六边形
  const top = `${cx},${cy - h / 2}`;
  const upR = `${cx + w / 2},${cy - h / 6}`;
  const downR = `${cx + w / 3.5},${cy + h / 5}`;
  const bottom = `${cx},${cy + h / 2}`;
  const downL = `${cx - w / 3.5},${cy + h / 5}`;
  const upL = `${cx - w / 2},${cy - h / 6}`;
  return (
    <g>
      <polygon
        points={`${top} ${upR} ${downR} ${bottom} ${downL} ${upL}`}
        fill="url(#platMain)"
        stroke="#0f766e"
        strokeWidth={s * 0.022}
        strokeLinejoin="round"
      />
      {/* 顶部分面 */}
      <polygon points={`${top} ${upR} ${cx},${cy - h / 6}`} fill="#a7f3d0" opacity="0.85" />
      <polygon points={`${top} ${upL} ${cx},${cy - h / 6}`} fill="#ecfdf5" opacity="0.9" />
      {/* 中间高光 */}
      <line
        x1={cx - w * 0.42}
        y1={cy - h / 6}
        x2={cx + w * 0.42}
        y2={cy - h / 6}
        stroke="rgba(255,255,255,0.5)"
        strokeWidth={s * 0.01}
      />
    </g>
  );
};

// 钻石：双层八芒星 + 中心光点
const DiamondIcon = ({ size }) => {
  const s = size;
  const cx = s / 2;
  const cy = s / 2;
  // 大八芒星
  const r1 = s * 0.36;
  const r2 = s * 0.16;
  const pts = [];
  for (let i = 0; i < 16; i++) {
    const a = (Math.PI / 8) * i - Math.PI / 2;
    const r = i % 2 === 0 ? r1 : r2;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return (
    <g>
      <polygon points={pts.join(' ')} fill="url(#diamondGrad)" stroke="#1e3a8a" strokeWidth={s * 0.022} strokeLinejoin="round" />
      {/* 内层小八芒星 */}
      <polygon
        points={starPoints(cx, cy, s * 0.14, s * 0.06, 8)}
        fill="#dbeafe"
        opacity="0.85"
      />
      <circle cx={cx} cy={cy} r={s * 0.04} fill="#fff" opacity="0.95" />
      {/* 闪光颗粒 */}
      <circle cx={cx + s * 0.22} cy={cy - s * 0.22} r={s * 0.012} fill="#fff" />
      <circle cx={cx - s * 0.20} cy={cy + s * 0.18} r={s * 0.01} fill="#fff" opacity="0.7" />
    </g>
  );
};

// 大师：双层皇冠 + 浮动宝石
const MasterIcon = ({ size }) => {
  const s = size;
  return (
    <g>
      {/* 底座环（皇冠的座底） */}
      <rect
        x={s * 0.22}
        y={s * 0.62}
        width={s * 0.56}
        height={s * 0.08}
        rx={s * 0.02}
        fill="#7e22ce"
        stroke="#3b0764"
        strokeWidth={s * 0.018}
      />
      {/* 皇冠主体（5 尖） */}
      <path
        d={`
          M ${s * 0.22} ${s * 0.62}
          L ${s * 0.22} ${s * 0.42}
          L ${s * 0.32} ${s * 0.52}
          L ${s * 0.40} ${s * 0.28}
          L ${s * 0.50} ${s * 0.46}
          L ${s * 0.60} ${s * 0.28}
          L ${s * 0.68} ${s * 0.52}
          L ${s * 0.78} ${s * 0.42}
          L ${s * 0.78} ${s * 0.62}
          Z
        `}
        fill="url(#masterGrad)"
        stroke="#3b0764"
        strokeWidth={s * 0.02}
        strokeLinejoin="round"
      />
      {/* 顶部宝石 */}
      <circle cx={s * 0.40} cy={s * 0.27} r={s * 0.04} fill="#fde047" stroke="#854d0e" strokeWidth={s * 0.012} />
      <circle cx={s * 0.50} cy={s * 0.45} r={s * 0.05} fill="#f43f5e" stroke="#881337" strokeWidth={s * 0.012} />
      <circle cx={s * 0.60} cy={s * 0.27} r={s * 0.04} fill="#fde047" stroke="#854d0e" strokeWidth={s * 0.012} />
      {/* 高光 */}
      <path
        d={`M ${s * 0.28} ${s * 0.46} Q ${s * 0.5} ${s * 0.38} ${s * 0.72} ${s * 0.46}`}
        stroke="rgba(255,255,255,0.5)"
        strokeWidth={s * 0.012}
        fill="none"
      />
    </g>
  );
};

// 王者：凤凰焰 + 皇冠 + 中心 K 字火焰
const KingIcon = ({ size }) => {
  const s = size;
  return (
    <g>
      {/* 外圈火焰光环 */}
      <path
        d={`
          M ${s * 0.5} ${s * 0.10}
          Q ${s * 0.22} ${s * 0.25} ${s * 0.20} ${s * 0.55}
          Q ${s * 0.10} ${s * 0.45} ${s * 0.16} ${s * 0.66}
          Q ${s * 0.22} ${s * 0.85} ${s * 0.5} ${s * 0.88}
          Q ${s * 0.78} ${s * 0.85} ${s * 0.84} ${s * 0.66}
          Q ${s * 0.90} ${s * 0.45} ${s * 0.80} ${s * 0.55}
          Q ${s * 0.78} ${s * 0.25} ${s * 0.5} ${s * 0.10} Z
        `}
        fill="url(#kingFlame)"
      />
      {/* 内层火焰 */}
      <path
        d={`
          M ${s * 0.5} ${s * 0.22}
          Q ${s * 0.34} ${s * 0.36} ${s * 0.34} ${s * 0.58}
          Q ${s * 0.5} ${s * 0.78} ${s * 0.66} ${s * 0.58}
          Q ${s * 0.66} ${s * 0.36} ${s * 0.5} ${s * 0.22} Z
        `}
        fill="url(#kingInner)"
        opacity="0.85"
      />
      {/* 王者皇冠 */}
      <path
        d={`
          M ${s * 0.30} ${s * 0.62}
          L ${s * 0.30} ${s * 0.48}
          L ${s * 0.38} ${s * 0.55}
          L ${s * 0.44} ${s * 0.38}
          L ${s * 0.50} ${s * 0.50}
          L ${s * 0.56} ${s * 0.38}
          L ${s * 0.62} ${s * 0.55}
          L ${s * 0.70} ${s * 0.48}
          L ${s * 0.70} ${s * 0.62}
          Z
        `}
        fill="#fde047"
        stroke="#7c2d12"
        strokeWidth={s * 0.018}
        strokeLinejoin="round"
      />
      {/* 皇冠座底 */}
      <rect x={s * 0.30} y={s * 0.62} width={s * 0.40} height={s * 0.05} fill="#b45309" stroke="#7c2d12" strokeWidth={s * 0.012} />
      {/* 中心红宝石 */}
      <circle cx={s * 0.5} cy={s * 0.50} r={s * 0.04} fill="#dc2626" stroke="#fde047" strokeWidth={s * 0.012} />
      {/* 高光 */}
      <path d={`M ${s * 0.36} ${s * 0.55} Q ${s * 0.5} ${s * 0.48} ${s * 0.64} ${s * 0.55}`}
            stroke="rgba(255,255,255,0.5)" strokeWidth={s * 0.012} fill="none" />
    </g>
  );
};

const ICONS = {
  unranked: UnrankedIcon,
  bronze: BronzeIcon,
  silver: SilverIcon,
  gold: GoldIcon,
  platinum: PlatinumIcon,
  diamond: DiamondIcon,
  master: MasterIcon,
  king: KingIcon,
};

// 主导出组件
const RankBadge = ({ rankId = 'unranked', size = 64, withBase = true }) => {
  const rank = getRank(rankId);
  const Icon = ICONS[rankId] || UnrankedIcon;
  const uid = `${rankId}-${size}`;
  const gradId = `octGrad-${uid}`;

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ display: 'inline-block', verticalAlign: 'middle' }}
    >
      <defs>
        {/* 八角形主渐变（按段位染色） */}
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={lighten(rank.bg, 0.25)} />
          <stop offset="50%" stopColor={rank.bg} />
          <stop offset="100%" stopColor={darken(rank.bg, 0.35)} />
        </linearGradient>
        {/* 复用的金属高光 */}
        <linearGradient id="bronzeShine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.7" />
          <stop offset="60%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="silverShine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.85" />
          <stop offset="60%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="goldShine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#fff" stopOpacity="0.7" />
          <stop offset="60%" stopColor="#fff" stopOpacity="0" />
        </linearGradient>
        {/* 铂金钻石主面 */}
        <linearGradient id="platMain" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#a7f3d0" />
          <stop offset="50%" stopColor="#4fd1c5" />
          <stop offset="100%" stopColor="#0d9488" />
        </linearGradient>
        {/* 钻石八芒星 */}
        <radialGradient id="diamondGrad" cx="0.5" cy="0.5" r="0.55">
          <stop offset="0%" stopColor="#dbeafe" />
          <stop offset="55%" stopColor="#60a5fa" />
          <stop offset="100%" stopColor="#1e40af" />
        </radialGradient>
        {/* 大师皇冠 */}
        <linearGradient id="masterGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#d8b4fe" />
          <stop offset="50%" stopColor="#a855f7" />
          <stop offset="100%" stopColor="#6b21a8" />
        </linearGradient>
        {/* 王者火焰 */}
        <radialGradient id="kingFlame" cx="0.5" cy="0.6" r="0.55">
          <stop offset="0%" stopColor="#fde047" stopOpacity="0.9" />
          <stop offset="55%" stopColor="#f97316" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#7f1d1d" stopOpacity="0.2" />
        </radialGradient>
        <radialGradient id="kingInner" cx="0.5" cy="0.55" r="0.5">
          <stop offset="0%" stopColor="#fef3c7" stopOpacity="1" />
          <stop offset="60%" stopColor="#f59e0b" stopOpacity="0.85" />
          <stop offset="100%" stopColor="#dc2626" stopOpacity="0.6" />
        </radialGradient>
      </defs>

      {withBase && rank.value > 0 && (
        <Base size={size} gradId={gradId} edgeColor={rank.color} glowColor={rank.glow} />
      )}
      <Icon size={size} />
    </svg>
  );
};

// ----- 颜色工具：在 hex 上加亮 / 加暗 -----
function lighten(hex, amount) {
  const { r, g, b } = hexToRgb(hex);
  const f = (c) => Math.min(255, Math.round(c + (255 - c) * amount));
  return rgbToHex(f(r), f(g), f(b));
}
function darken(hex, amount) {
  const { r, g, b } = hexToRgb(hex);
  const f = (c) => Math.max(0, Math.round(c * (1 - amount)));
  return rgbToHex(f(r), f(g), f(b));
}
function hexToRgb(hex) {
  const m = hex.replace('#', '');
  const n = m.length === 3 ? m.split('').map((c) => c + c).join('') : m;
  return {
    r: parseInt(n.slice(0, 2), 16),
    g: parseInt(n.slice(2, 4), 16),
    b: parseInt(n.slice(4, 6), 16),
  };
}
function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map((c) => c.toString(16).padStart(2, '0')).join('');
}

export default RankBadge;
