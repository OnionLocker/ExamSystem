// 公式速查面板的数据
// 分类：data 资料分析 / quant 数量关系 / sci 科学推理（广东特色）/ verbal 言语成语

export const FORMULA_GROUPS = [
  {
    id: 'data',
    name: '资料分析',
    color: '#fbc02d',
    sections: [
      {
        title: '基期量',
        formulas: [
          {
            name: '基期量（同比）',
            formula: '基期 = 现期 / (1 + r)',
            note: 'r 为同比增长率（小数），如 12% → 0.12',
            example: '现期 1200，r=20% → 基期 = 1200/1.2 = 1000',
          },
          {
            name: '基期量（百化分）',
            formula: '基期 ≈ 现期 × (1 - r/(1+r))',
            note: '把 r/(1+r) 用百化分表速记，比直接除法快',
            example: 'r=25%，r/(1+r)=20% (1/5)，基期≈现期×80%',
          },
        ],
      },
      {
        title: '增长量 / 增长率',
        formulas: [
          {
            name: '增长量',
            formula: '增长量 = 现期 - 基期 = 现期 × r/(1+r)',
            note: '"现期×r/(1+r)" 比"现期-基期"快，因为可估算',
            example: '现期 600，r=20% → 增长量 ≈ 600×1/6 = 100',
          },
          {
            name: '增长率',
            formula: 'r = (现期 - 基期) / 基期',
            note: '注意基期是分母不是现期',
          },
          {
            name: '增长率比较 N 倍法',
            formula: 'A 是 B 的 N 倍 → 增长量也大致 N 倍',
            note: '量与率方向一致时，比较增长量约等于比较增长率',
          },
        ],
      },
      {
        title: '比重',
        formulas: [
          {
            name: '现期比重',
            formula: '比重 = 部分 / 整体',
            note: '资料分析最高频公式',
          },
          {
            name: '基期比重',
            formula: '基期比重 = 现期比重 × (1+r总) / (1+r部)',
            note: '注意分子分母位置：总在上、部在下',
          },
          {
            name: '两期比重差',
            formula: '差 = 现期比重 × (r部 - r总) / (1 + r部)',
            note: '差的符号由 r部 - r总 决定：部>总 则上升',
          },
          {
            name: '比重升降判定',
            formula: 'r部 > r总 → 比重上升；反之下降',
            note: '考"是否上升"题型秒判',
          },
        ],
      },
      {
        title: '增长率合成',
        formulas: [
          {
            name: '乘积增长率',
            formula: 'r(A×B) ≈ r_A + r_B + r_A·r_B',
            note: 'r 都用百分数计算时，最后乘积项 ÷ 100',
            example: 'A 增 20%，B 增 10% → A×B 增 ≈ 32%',
          },
          {
            name: '除式增长率',
            formula: 'r(A/B) = (r_A - r_B) / (1 + r_B)',
            note: '常见于"人均"类指标（总量/人数）',
          },
          {
            name: '平均数增长率',
            formula: 'r_平 = (r_总 - r_数) / (1 + r_数)',
            note: '总量增长率减个体数增长率，再除以(1+r_数)',
          },
          {
            name: '混合增长率',
            formula: 'r_总 ≈ Σ(w_i × r_i)（按权重加权平均）',
            note: '当 r_i 相近时近似成立',
          },
        ],
      },
      {
        title: '其他',
        formulas: [
          {
            name: '拉动增长率',
            formula: '拉动 = 部分增长量 / 整体基期 × 100%',
            note: '注意分母是整体的基期，不是现期',
          },
          {
            name: '贡献率',
            formula: '贡献率 = 部分增长量 / 整体增长量 × 100%',
            note: 'Σ各部分贡献率 = 100%',
          },
          {
            name: '年均增长率',
            formula: 'r年均 = (末/基)^(1/n) - 1',
            note: 'n 为年数。粗算可用 r ≈ r_总 / n（高估）',
          },
          {
            name: '百分点 vs 百分比',
            formula: '差 X 百分点 ≠ 增 X%',
            note: '从 5% 到 7%：涨 2 个百分点 / 相对涨幅 40%',
          },
        ],
      },
    ],
  },
  {
    id: 'quant',
    name: '数量关系',
    color: '#60a5fa',
    sections: [
      {
        title: '行程问题',
        formulas: [
          {
            name: '相遇',
            formula: '相遇时间 = 总距离 / (v₁ + v₂)',
            note: '相向而行，速度相加',
          },
          {
            name: '追及',
            formula: '追及时间 = 距离差 / (v后 - v前)',
            note: '同向而行，速度相减',
          },
          {
            name: '流水行船',
            formula: '顺水速度 = v船 + v水；逆水速度 = v船 - v水',
            note: 'v船 = (顺 + 逆)/2；v水 = (顺 - 逆)/2',
          },
          {
            name: '相遇追及（环形）',
            formula: '同向相遇 = 周长 / 速度差；反向相遇 = 周长 / 速度和',
            note: '环形跑道关键',
          },
        ],
      },
      {
        title: '工程 / 浓度',
        formulas: [
          {
            name: '工程合作',
            formula: '合作时间 = 1 / (1/a + 1/b)',
            note: '总工 = 1，a/b 是各自单独完成时间',
            example: '甲 6 天乙 12 天 → 合作 = 1/(1/6+1/12) = 4 天',
          },
          {
            name: '溶液混合',
            formula: '新浓度 = (m₁c₁ + m₂c₂) / (m₁ + m₂)',
            note: '加权平均，c 是浓度（小数）',
          },
          {
            name: '溶液稀释',
            formula: '新浓度 = (原溶质) / (原溶液 + 加水)',
            note: '加水后溶质不变',
          },
          {
            name: '十字交叉',
            formula: '混合时 m₁:m₂ = (c₂-c) : (c-c₁)',
            note: '快速求混合比',
          },
        ],
      },
      {
        title: '排列组合 / 概率',
        formulas: [
          {
            name: '排列 A(n,k)',
            formula: 'A(n,k) = n! / (n-k)! = n(n-1)…(n-k+1)',
            note: '有序选取，关心顺序',
          },
          {
            name: '组合 C(n,k)',
            formula: 'C(n,k) = A(n,k) / k! = n! / [k!(n-k)!]',
            note: '无序选取',
          },
          {
            name: '组合恒等式',
            formula: 'C(n,k) = C(n,n-k)；C(n,k) = C(n-1,k-1) + C(n-1,k)',
            note: '化简组合数常用',
          },
          {
            name: '古典概率',
            formula: 'P(A) = 有利事件数 / 样本空间总数',
            note: '都是离散等可能',
          },
          {
            name: '加法 / 乘法原理',
            formula: '加法（分类）：n₁+n₂；乘法（分步）：n₁×n₂',
            note: '分清"分类"还是"分步"',
          },
        ],
      },
      {
        title: '其他经典模型',
        formulas: [
          {
            name: '容斥（两集合）',
            formula: '|A∪B| = |A| + |B| - |A∩B|',
            note: '总人数 - 都不 = |A∪B|',
          },
          {
            name: '容斥（三集合）',
            formula: '|A∪B∪C| = |A|+|B|+|C| - |A∩B| - |A∩C| - |B∩C| + |A∩B∩C|',
            note: '记忆：单 - 双 + 三',
          },
          {
            name: '均值不等式',
            formula: 'a + b ≥ 2√(ab)；ab ≤ ((a+b)/2)²',
            note: '当 a = b 时取等号；用于求最值',
          },
          {
            name: '鸡兔同笼',
            formula: '兔 = (脚数 - 2×头数) / 2',
            note: '通用：(脚 - 小×头) / (大 - 小)',
          },
          {
            name: '植树问题',
            formula: '两端栽：n = L/d + 1；环形：n = L/d',
            note: '两端不栽：n = L/d - 1',
          },
          {
            name: '方阵',
            formula: '实心 = n²；外层 = 4(n-1)；外 k 层 = n² - (n-2k)²',
            note: '记口诀"四角不重复"',
          },
        ],
      },
    ],
  },
  {
    id: 'sci',
    name: '科学推理',
    color: '#a855f7',
    sections: [
      {
        title: '物理 · 力学',
        formulas: [
          {
            name: '杠杆原理',
            formula: 'F₁·L₁ = F₂·L₂',
            note: '动力×动力臂 = 阻力×阻力臂',
          },
          {
            name: '滑轮组',
            formula: '定滑轮：F=G；动滑轮：F=G/2；滑轮组：F=G/n',
            note: 'n 为承重绳数',
          },
          {
            name: '压强',
            formula: 'p = F/S（固体）；p = ρgh（液体）',
            note: '液体压强只与深度和密度有关',
          },
          {
            name: '浮力',
            formula: 'F浮 = ρ液 · g · V排',
            note: '阿基米德原理',
          },
          {
            name: '物体浮沉',
            formula: 'ρ物 < ρ液 浮起；ρ物 = ρ液 悬浮；ρ物 > ρ液 下沉',
            note: '常考铁块 vs 木块',
          },
        ],
      },
      {
        title: '物理 · 电学',
        formulas: [
          {
            name: '欧姆定律',
            formula: 'U = IR（电压 = 电流 × 电阻）',
            note: '电学第一公式',
          },
          {
            name: '串联 / 并联',
            formula: '串联：R = R₁+R₂；并联：1/R = 1/R₁+1/R₂',
            note: '串电流相等，并电压相等',
          },
          {
            name: '电功率',
            formula: 'P = UI = I²R = U²/R',
            note: '功率公式三选一，看已知量',
          },
          {
            name: '电热',
            formula: 'Q = I²Rt（焦耳定律）',
            note: '与电流平方成正比',
          },
        ],
      },
      {
        title: '化学',
        formulas: [
          {
            name: '酸碱盐',
            formula: 'pH<7 酸性；pH=7 中性；pH>7 碱性',
            note: 'pH 越小酸性越强',
          },
          {
            name: '溶解度',
            formula: '一般温度 ↑ → 溶解度 ↑（气体相反）',
            note: '气体溶解度与温度成反比',
          },
          {
            name: '化学反应类型',
            formula: '化合 / 分解 / 置换 / 复分解',
            note: '4 种基本反应',
          },
          {
            name: '燃烧条件',
            formula: '可燃物 + 助燃物（氧气）+ 着火点',
            note: '三缺一不烧',
          },
          {
            name: '金属活动性',
            formula: 'K Ca Na Mg Al Zn Fe Sn Pb (H) Cu Hg Ag Pt Au',
            note: '前面的能置换后面的',
          },
        ],
      },
      {
        title: '生物',
        formulas: [
          {
            name: '光合 / 呼吸',
            formula: '光合：CO₂+H₂O →(光) 有机物+O₂',
            note: '呼吸是反过程',
          },
          {
            name: '细胞结构',
            formula: '动物：膜 + 质 + 核；植物：多了 壁/绿/液',
            note: '区分动植物细胞看三个特征',
          },
          {
            name: '遗传规律',
            formula: '显性掩盖隐性；后代分离比 3:1',
            note: '孟德尔豌豆实验',
          },
          {
            name: '食物链',
            formula: '能量流动 10%~20%（单向递减）',
            note: '营养级越高，能量越少',
          },
        ],
      },
    ],
  },
  {
    id: 'verbal',
    name: '言语技巧',
    color: '#22c55e',
    sections: [
      {
        title: '主旨题套路',
        formulas: [
          {
            name: '关联词法',
            formula: '"但是 / 然而 / 关键是" 后 = 主旨',
            note: '转折之后必是重点',
          },
          {
            name: '总分结构',
            formula: '"总-分-总" 或 "分-总" → 总句即主旨',
            note: '看首尾句',
          },
          {
            name: '原因 / 结果',
            formula: '"因此 / 所以 / 总之" 后 = 主旨',
            note: '结论性词语后是答案',
          },
        ],
      },
      {
        title: '陷阱识别',
        formulas: [
          {
            name: '偷换概念',
            formula: '原文是 A，选项变 A\'',
            note: '词义有细微差别',
          },
          {
            name: '无中生有',
            formula: '原文未提到，选项凭空多',
            note: '看清原文边界',
          },
          {
            name: '范围扩大 / 缩小',
            formula: '原文"部分"→选项"全部"，反之亦然',
            note: '量词陷阱',
          },
          {
            name: '正话反说',
            formula: '原文肯定 → 选项否定',
            note: '注意"不""未""无"等否定词',
          },
        ],
      },
      {
        title: '逻辑填空',
        formulas: [
          {
            name: '语境分析',
            formula: '前后语义一致 / 转折 / 递进',
            note: '看上下文关系再选词',
          },
          {
            name: '搭配习惯',
            formula: '动宾搭配 / 形名搭配看习惯用法',
            note: '"严格执行"对，"严肃执行"不对',
          },
        ],
      },
    ],
  },
];

// 扁平索引
export const FORMULA_BY_GROUP = (() => {
  const m = new Map();
  FORMULA_GROUPS.forEach((g) => m.set(g.id, g));
  return m;
})();
