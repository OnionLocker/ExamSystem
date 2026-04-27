// ============================================================
// 段位徽章 SVG
// --------------------------------------
// 7 个段位图标采用"盾 → 盾+V → 盾+星 → 菱钻 → 八芒星 → 皇冠 → 火焰皇冠"演进，
// 所有图标都嵌在一枚"六边形奖章"底座里，视觉一致。
// 高档位（钻石以上）带发光外圈。
// ============================================================
import { getRank } from './ranks.js';

// 六边形奖章底座（所有徽章共用）
const HexBase = ({ color, glow, size = 64, gradId }) => (
  <>
    {glow && (
      <circle cx={size / 2} cy={size / 2} r={size / 2 - 1}
              fill={glow} opacity="0.25"
              filter={`blur(${size / 8}px)`} />
    )}
    <polygon
      points={hexPoints(size / 2, size / 2, size / 2 - 2)}
      fill={`url(#${gradId})`}
      stroke={color}
      strokeWidth="1.5"
    />
  </>
);

function hexPoints(cx, cy, r) {
  const pts = [];
  for (let i = 0; i < 6; i++) {
    const a = (Math.PI / 3) * i - Math.PI / 2;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
}

// 未评级：灰色问号
const UnrankedIcon = ({ size }) => {
  const s = size;
  return (
    <g>
      <circle cx={s / 2} cy={s / 2} r={s / 2 - 2} fill="#e2e8f0" />
      <text x={s / 2} y={s / 2 + s * 0.12} textAnchor="middle"
            fill="#94a3b8" fontSize={s * 0.45} fontWeight="900" fontStyle="italic">
        ?
      </text>
    </g>
  );
};

// 青铜：基础盾
const BronzeIcon = ({ size }) => {
  const s = size;
  return (
    <g transform={`translate(${s * 0.22}, ${s * 0.18})`}>
      <path d={shieldPath(s * 0.56, s * 0.64)} fill="#a17b5d" stroke="#6b4e38" strokeWidth="1.5" />
      <path d={shieldPath(s * 0.56, s * 0.64)} fill="url(#bronzeShine)" opacity="0.5" />
    </g>
  );
};

// 白银：盾 + V 字
const SilverIcon = ({ size }) => {
  const s = size;
  return (
    <g transform={`translate(${s * 0.22}, ${s * 0.18})`}>
      <path d={shieldPath(s * 0.56, s * 0.64)} fill="#c0c7d1" stroke="#7a8494" strokeWidth="1.5" />
      <path d={shieldPath(s * 0.56, s * 0.64)} fill="url(#silverShine)" opacity="0.6" />
      <path
        d={`M ${s * 0.14} ${s * 0.22} L ${s * 0.28} ${s * 0.42} L ${s * 0.42} ${s * 0.22}`}
        fill="none" stroke="#3d4556" strokeWidth={s * 0.04} strokeLinecap="round" strokeLinejoin="round"
      />
    </g>
  );
};

// 黄金：盾 + 星星
const GoldIcon = ({ size }) => {
  const s = size;
  return (
    <g transform={`translate(${s * 0.22}, ${s * 0.18})`}>
      <path d={shieldPath(s * 0.56, s * 0.64)} fill="#fbc02d" stroke="#a47a0e" strokeWidth="1.5" />
      <path d={shieldPath(s * 0.56, s * 0.64)} fill="url(#goldShine)" opacity="0.55" />
      <polygon
        points={starPoints(s * 0.28, s * 0.32, s * 0.14, s * 0.06, 5)}
        fill="#a47a0e"
      />
    </g>
  );
};

// 铂金：菱形钻石
const PlatinumIcon = ({ size }) => {
  const s = size;
  const cx = s / 2, cy = s / 2;
  const w = s * 0.34, h = s * 0.42;
  return (
    <g>
      <polygon
        points={`${cx},${cy - h / 2} ${cx + w / 2},${cy - h / 8} ${cx + w / 3},${cy + h / 2} ${cx - w / 3},${cy + h / 2} ${cx - w / 2},${cy - h / 8}`}
        fill="#4fd1c5" stroke="#0f766e" strokeWidth="1.5"
      />
      <polygon
        points={`${cx},${cy - h / 2} ${cx + w / 2},${cy - h / 8} ${cx},${cy - h / 8}`}
        fill="#a7f3d0" opacity="0.7"
      />
      <polygon
        points={`${cx},${cy - h / 2} ${cx - w / 2},${cy - h / 8} ${cx},${cy - h / 8}`}
        fill="#e6fffa" opacity="0.5"
      />
    </g>
  );
};

// 钻石：八芒星（光芒四射）
const DiamondIcon = ({ size }) => {
  const s = size;
  const cx = s / 2, cy = s / 2;
  const r1 = s * 0.32, r2 = s * 0.14;
  const pts = [];
  for (let i = 0; i < 16; i++) {
    const a = (Math.PI / 8) * i - Math.PI / 2;
    const r = i % 2 === 0 ? r1 : r2;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return (
    <g>
      <polygon points={pts.join(' ')} fill="#60a5fa" stroke="#1e40af" strokeWidth="1.5" />
      <circle cx={cx} cy={cy} r={s * 0.08} fill="#dbeafe" opacity="0.9" />
    </g>
  );
};

// 大师：皇冠
const MasterIcon = ({ size }) => {
  const s = size;
  return (
    <g transform={`translate(${s * 0.18}, ${s * 0.22})`}>
      <path
        d={crownPath(s * 0.64, s * 0.4)}
        fill="#a855f7" stroke="#581c87" strokeWidth="1.5"
      />
      <circle cx={s * 0.12} cy={s * 0.08} r={s * 0.04} fill="#fde047" />
      <circle cx={s * 0.32} cy={s * 0.04} r={s * 0.05} fill="#fde047" />
      <circle cx={s * 0.52} cy={s * 0.08} r={s * 0.04} fill="#fde047" />
      <rect x={s * 0.04} y={s * 0.28} width={s * 0.56} height={s * 0.06} fill="#7e22ce" />
    </g>
  );
};

// 王者：火焰皇冠
const KingIcon = ({ size }) => {
  const s = size;
  return (
    <g>
      {/* 火焰背景 */}
      <path
        d={`M ${s * 0.5} ${s * 0.15}
            Q ${s * 0.3} ${s * 0.3} ${s * 0.32} ${s * 0.55}
            Q ${s * 0.25} ${s * 0.45} ${s * 0.22} ${s * 0.6}
            Q ${s * 0.28} ${s * 0.8} ${s * 0.5} ${s * 0.82}
            Q ${s * 0.72} ${s * 0.8} ${s * 0.78} ${s * 0.6}
            Q ${s * 0.75} ${s * 0.45} ${s * 0.68} ${s * 0.55}
            Q ${s * 0.7} ${s * 0.3} ${s * 0.5} ${s * 0.15} Z`}
        fill="url(#kingFlame)"
      />
      {/* 皇冠 */}
      <g transform={`translate(${s * 0.22}, ${s * 0.36})`}>
        <path
          d={crownPath(s * 0.56, s * 0.34)}
          fill="#fde047" stroke="#b45309" strokeWidth="1.5"
        />
        <circle cx={s * 0.08} cy={s * 0.06} r={s * 0.035} fill="#dc2626" />
        <circle cx={s * 0.28} cy={s * 0.02} r={s * 0.045} fill="#dc2626" />
        <circle cx={s * 0.48} cy={s * 0.06} r={s * 0.035} fill="#dc2626" />
        <rect x={s * 0.02} y={s * 0.24} width={s * 0.52} height={s * 0.06} fill="#b45309" />
      </g>
    </g>
  );
};

// 盾牌路径（宽 w 高 h，从 (0,0) 开始）
function shieldPath(w, h) {
  return `
    M ${w / 2} 0
    L ${w} ${h * 0.18}
    L ${w} ${h * 0.55}
    Q ${w} ${h * 0.85} ${w / 2} ${h}
    Q 0 ${h * 0.85} 0 ${h * 0.55}
    L 0 ${h * 0.18}
    Z
  `;
}

// 皇冠路径（三尖皇冠）
function crownPath(w, h) {
  return `
    M 0 ${h * 0.9}
    L 0 ${h * 0.3}
    L ${w * 0.2} ${h * 0.55}
    L ${w * 0.35} 0
    L ${w * 0.5} ${h * 0.45}
    L ${w * 0.65} 0
    L ${w * 0.8} ${h * 0.55}
    L ${w} ${h * 0.3}
    L ${w} ${h * 0.9}
    Z
  `;
}

function starPoints(cx, cy, rOuter, rInner, n) {
  const pts = [];
  for (let i = 0; i < n * 2; i++) {
    const a = (Math.PI / n) * i - Math.PI / 2;
    const r = i % 2 === 0 ? rOuter : rInner;
    pts.push(`${(cx + r * Math.cos(a)).toFixed(2)},${(cy + r * Math.sin(a)).toFixed(2)}`);
  }
  return pts.join(' ');
}

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
  const gradId = `hexGrad-${uid}`;
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}
         style={{ display: 'inline-block', verticalAlign: 'middle' }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={rank.bg} stopOpacity="1" />
          <stop offset="100%" stopColor="#000000" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="bronzeShine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="silverShine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.8" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="goldShine" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#ffffff" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="kingFlame" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fde047" stopOpacity="0.8" />
          <stop offset="60%" stopColor="#ff6b6b" stopOpacity="0.7" />
          <stop offset="100%" stopColor="#7f1d1d" stopOpacity="0.3" />
        </linearGradient>
      </defs>
      {withBase && rank.value > 0 && (
        <HexBase color={rank.color} glow={rank.glow} size={size} gradId={gradId} />
      )}
      {withBase && rank.value === 0 && (
        <circle cx={size / 2} cy={size / 2} r={size / 2 - 2} fill="#f1f5f9" stroke="#cbd5e1" strokeWidth="1.5" />
      )}
      <Icon size={size} />
    </svg>
  );
};

export default RankBadge;
