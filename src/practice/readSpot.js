import { generateFindBasic, generateFindAdv } from './readSpotPacks.js';

// 读题反应：识别考点 + 找数（基础/进阶）
// 不自动判对错。生成器用 answer / reason / material 给「完成」后对照。
// 识别考点：先抽考点再填槽。基期量题干必须带「上年 / 材料现期」时间差；仅「累计/截至」是累计量。

const rand = (min, max) => Math.floor(Math.random() * (max - min + 1)) + min;
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];
const wrapQ = (q) => ({
  ...q,
  answer: q.answer,
  displayAnswer: () => q.answer,
});

const YEAR = () => pick([2023, 2024, 2025]);

const fill = (tpl, ctx) =>
  tpl.replace(/\{([a-zA-Z0-9]+)\}/g, (_, k) => (ctx[k] == null ? `{${k}}` : String(ctx[k])));

const M = (need) => (key) => (need.has(key) ? 'target' : undefined);

// ---------- 识别考点：资料 ----------
// 槽位：年份 + 主体词库。考点由题干信号决定，不靠材料。
const THEMES = [
  {
    id: 'charge', kind: 'tree', open: 'stock',
    place: '该省', places: ['G省', '该省', '全省'],
    lead: '持续推进新能源汽车充电基础设施网络建设',
    tip: '充电桩：存量、电量、保有量不要串',
    stock: '累计建成各类充电桩', stockUnit: '万个',
    item: '公共充电桩数量', flow: '公共充电桩充电电量',
    unit: '万个', unit2: '亿千瓦时',
    part: '公共充电桩', whole: '各类充电桩', other: '个人专用充电桩',
    avgObj: '公共充电桩', avgHead: '新能源汽车', avgUnit: '个/辆',
    openLabel: '截至{y}年末，累计建成各类充电桩',
    wholeQty: [90, 170], partShare: [0.30, 0.40],
    cutTitle: '按设施类型分',
    regionTitle: '分区域看', regionA: '珠三角九市公共充电桩', regionB: '粤东粤西粤北公共充电桩',
    flowTitle: '充电电量方面', flowWhole: '公共充电桩充电电量', flowPart: '乘用车充电电量', flowOther: '商用车及其他充电电量',
    flowQty: [90, 200], flowPartShare: [0.55, 0.72],
    stockName: '新能源汽车保有量', stockNameUnit: '万辆', stockQty: [220, 480],
    headName: '充电运营企业数',
    extras: [
      '农村地区公共桩继续补点，高速公路服务区快充覆盖率提高。新建公共桩中超充和快充占比上升，居住区慢充以合建共享为主。',
      '「累计建成」是时点存量，充电电量是时期内发生额，保有量是车辆口径，三套数不要混着找。',
    ],
  },
  {
    id: 'digital', kind: 'tree', open: 'year',
    place: 'G省', places: ['H省', '该省', '全省'],
    lead: '深入实施数字经济核心产业提质增效行动',
    tip: '数字经济：增加值、营收、行业门类不要串',
    stock: '数字经济核心产业有效发明专利拥有量', stockUnit: '万件',
    item: '数字经济核心产业增加值', flow: '数字经济核心产业营业收入',
    unit: '亿元', unit2: '亿元',
    part: '数字产品制造业营业收入', whole: '数字经济核心产业营业收入', other: '数字技术应用业营业收入',
    avgObj: '规模以上企业', avgHead: '从业人员', avgUnit: '万元',
    openLabel: '全年数字经济核心产业实现营业收入',
    wholeQty: [12000, 21000], partShare: [0.42, 0.58],
    cutTitle: '分行业门类看',
    regionTitle: '分企业规模看', regionA: '超百亿元企业营业收入', regionB: '其余企业营业收入',
    flowTitle: '科技创新投入方面', flowWhole: '核心产业研发经费内部支出', flowPart: '企业研发经费', flowOther: '研究机构研发经费',
    flowQty: [420, 980], flowPartShare: [0.70, 0.88],
    stockName: '有效发明专利拥有量', stockNameUnit: '万件', stockQty: [5.5, 12.8],
    headName: '相关从业人员',
    extras: [
      '软件业务、云计算和大数据服务收入快于制造业。专精特新中小企业数量更多、单体营收更小。',
      '定位时先分清增加值还是营业收入，再看四个行业门类，研发经费占比不是行业增速。',
    ],
  },
  {
    id: 'ocean', kind: 'tree', open: 'year',
    place: '某沿海省', places: ['某沿海省', '该省'],
    lead: '以港航枢纽强省建设为目标，海洋经济平稳运行',
    tip: '海洋：三次产业、吞吐量单位不要串',
    stock: '海洋工程装备保有量', stockUnit: '艘',
    item: '海洋生产总值', flow: '沿海港口货物吞吐量',
    unit: '亿元', unit2: '亿吨',
    part: '海洋第三产业增加值', whole: '海洋生产总值', other: '海洋第二产业增加值',
    avgObj: '沿海港口', avgHead: '码头泊位', avgUnit: '万吨',
    openLabel: '全年实现海洋生产总值',
    wholeQty: [15000, 24000], partShare: [0.52, 0.64],
    cutTitle: '三次产业结构方面',
    regionTitle: '传统产业方面', regionA: '海洋旅游业增加值', regionB: '海洋水产品加工业增加值',
    flowTitle: '港口航运方面', flowWhole: '沿海港口货物吞吐量', flowPart: '外贸货物吞吐量', flowOther: '内贸货物吞吐量',
    flowQty: [14, 28], flowPartShare: [0.38, 0.55],
    stockName: '海洋工程装备保有量', stockNameUnit: '艘', stockQty: [180, 460],
    headName: '沿海港口生产性泊位数',
    extras: [
      '海洋生物医药、海水淡化与海上风电相关制造保持较快增长。传统捕捞产量基本稳定。',
      '生产总值、增加值、吞吐量单位不同。三次产业增加值加总应接近 GOP，不要把箱量当成吨数。',
    ],
  },
  {
    id: 'tourism', kind: 'tree', open: 'year',
    place: '该市', places: ['该市', '该省', '全省'],
    lead: '文旅市场持续恢复',
    tip: '文旅：入境、省内、过夜人次不要串',
    stock: 'A级旅游景区累计接待人次', stockUnit: '万人次',
    item: '接待游客人次', flow: '旅游总收入',
    unit: '万人次', unit2: '亿元',
    part: '省内游客', whole: '接待游客', other: '省外游客',
    avgObj: '过夜游客', avgHead: '星级饭店', avgUnit: '万人次',
    openLabel: '全年接待游客',
    wholeQty: [6200, 9800], partShare: [0.52, 0.70],
    cutTitle: '按客源分',
    regionTitle: '按停留分', regionA: '省内过夜游客', regionB: '省内一日游游客',
    flowTitle: '旅游收入方面', flowWhole: '旅游总收入', flowPart: '国内旅游收入', flowOther: '国际旅游收入',
    flowQty: [680, 1400], flowPartShare: [0.82, 0.94],
    stockName: 'A级旅游景区接待人次', stockNameUnit: '万人次', stockQty: [2100, 4500],
    headName: '星级饭店从业人员',
    extras: [
      '乡村旅游和红色旅游人次上升，但人均花费低于城市观光。民航和口岸恢复带动入境游客增速更快。',
      '「接待游客」是合计，入境、省内、过夜是切块。人次与旅游总收入单位不同。',
    ],
  },
  {
    id: 'health', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省', 'G省'],
    lead: '持续完善分级诊疗',
    tip: '医疗：基层、医院、出院人次不要串',
    stock: '医疗卫生机构床位', stockUnit: '万张',
    item: '医疗卫生机构诊疗人次', flow: '医疗卫生机构门诊量',
    unit: '亿人次', unit2: '亿人次',
    part: '基层医疗卫生机构诊疗人次', whole: '医疗卫生机构诊疗人次', other: '医院诊疗人次',
    avgObj: '社区卫生服务中心', avgHead: '服务常住人口', avgUnit: '万人',
    openLabel: '全年医疗卫生机构诊疗人次',
    wholeQty: [8.5, 18.5], partShare: [0.48, 0.60],
    cutTitle: '按机构分',
    regionTitle: '分城乡看', regionA: '县域诊疗人次', regionB: '城市医院诊疗人次',
    flowTitle: '住院服务方面', flowWhole: '出院人次', flowPart: '基层出院人次', flowOther: '医院出院人次',
    flowQty: [0.18, 0.55], flowPartShare: [0.22, 0.40],
    stockName: '医疗卫生机构床位', stockNameUnit: '万张', stockQty: [38, 72],
    headName: '社区卫生服务中心数',
    extras: [
      '中医类和专科医院门诊增速快于综合医院。县域内住院量占比稳步提高。',
      '诊疗人次和出院人次不是同一口径。床位和卫生技术人员是时点存量。',
    ],
  },
  {
    id: 'trade', kind: 'tree', open: 'year',
    place: '东部地区', places: ['东部地区', '该省', '全省'],
    lead: '外贸结构持续优化',
    tip: '外贸：出口、进口、机电不要串',
    stock: '高新技术企业累计认定数', stockUnit: '家',
    item: '进出口总额', flow: '机电产品出口额',
    unit: '亿元', unit2: '亿元',
    part: '机电产品出口额', whole: '进出口总额', other: '农产品出口额',
    avgObj: '外贸企业', avgHead: '从业人员', avgUnit: '万元',
    openLabel: '全年进出口总额',
    wholeQty: [18000, 36000], partShare: [0.38, 0.55],
    cutTitle: '按商品分',
    regionTitle: '按贸易方式分', regionA: '一般贸易进出口', regionB: '加工贸易进出口',
    flowTitle: '出口方面', flowWhole: '出口总额', flowPart: '对东盟出口额', flowOther: '对其余市场出口额',
    flowQty: [9000, 19000], flowPartShare: [0.18, 0.32],
    stockName: '备案外贸企业数', stockNameUnit: '万家', stockQty: [8.5, 22.0],
    headName: '外贸从业人员',
    extras: [
      '民营企业进出口占比继续提高，跨境电商新业态增长更快。对共建「一带一路」国家进出口快于整体。',
      '进出口总额是出口加进口。机电产品出口是出口的一部分，不要拿去当进出口总额的部分却忘了进口。',
    ],
  },
  {
    id: 'fiscal', kind: 'ytd',
    place: '该省', places: ['该省', 'G省', '全省'],
    lead: '加强财源建设，一般公共预算收入运行总体平稳',
    tip: '财政：1—11月累计、12月当月、全年不要串',
    stock: '专项债券累计发行额', stockUnit: '亿元',
    item: '一般公共预算收入', flow: '税收收入',
    unit: '亿元', unit2: '亿元',
    part: '税收收入', whole: '一般公共预算收入', other: '非税收入',
    avgObj: '纳税企业', avgHead: '从业人员', avgUnit: '万元',
    ytdQty: [3200, 6800], monthQty: [280, 720], partShare: [0.68, 0.82],
    decoyName: '政府性基金收入', decoyUnit: '亿元', decoyQty: [700, 1600],
    headName: '纳税登记户数',
    extras: [
      '企业所得税和个人所得税波动大于增值税。契税和土地相关非税收入进度更不均衡。',
      '同一指标会同时给出累计、当月和全年。一般公共预算与政府性基金不要加总后再算同比。',
    ],
  },
  {
    id: 'energy', kind: 'tree', open: 'year',
    place: '全国', places: ['全国', '该省'],
    lead: '能源保供稳价有力有序',
    tip: '能源：产量、进口、发电量不要串',
    stock: '发电装机容量', stockUnit: '亿千瓦',
    item: '原油产量', flow: '原油进口量',
    unit: '万吨', unit2: '万吨',
    part: '原油产量', whole: '一次能源生产总量', other: '天然气产量',
    avgObj: '炼厂', avgHead: '加工量', avgUnit: '万吨',
    openLabel: '全年一次能源生产总量',
    wholeQty: [48000, 72000], partShare: [0.28, 0.42],
    cutTitle: '按品种分',
    regionTitle: '分产地看', regionA: '东部原油产量', regionB: '中西部原油产量',
    flowTitle: '进出口方面', flowWhole: '原油进口量', flowPart: '来自中东的原油进口', flowOther: '其余来源原油进口',
    flowQty: [42000, 58000], flowPartShare: [0.40, 0.58],
    stockName: '发电装机容量', stockNameUnit: '亿千瓦', stockQty: [28, 36],
    headName: '规模以上发电企业数',
    extras: [
      '非化石能源发电量占比继续提高，火电仍承担调峰。煤炭产量与发电用煤不要直接替代。',
      '产量是国内生产，进口是外购。装机是时点能力，发电量是时期产出。',
    ],
  },
  {
    id: 'industry', kind: 'ytd',
    place: '该省', places: ['该省', '全省', 'G省'],
    lead: '规模以上工业生产总体平稳',
    tip: '工业：累计增速、当月增速、增加值不要串',
    stock: '规模以上工业企业累计数', stockUnit: '家',
    item: '规模以上工业增加值', flow: '高技术制造业增加值',
    unit: '亿元', unit2: '亿元',
    part: '高技术制造业增加值', whole: '规模以上工业增加值', other: '传统制造业增加值',
    avgObj: '规上企业', avgHead: '从业人员', avgUnit: '万元',
    ytdQty: [21000, 42000], monthQty: [1800, 4200], partShare: [0.14, 0.28],
    decoyName: '工业出口交货值', decoyUnit: '亿元', decoyQty: [3200, 7800],
    headName: '规模以上工业企业数',
    extras: [
      '装备制造业和汽车制造业拉动明显，高耗能行业增加值增速偏低。',
      '1—11月累计与12月当月、全年是三套数。增加值不是营业收入，出口交货值更不是增加值。',
    ],
  },
  {
    id: 'invest', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省'],
    lead: '固定资产投资保持增长，结构继续优化',
    tip: '投资：三次产业、房地产、民间投资不要串',
    stock: '在建项目累计个数', stockUnit: '个',
    item: '固定资产投资额', flow: '基础设施投资',
    unit: '亿元', unit2: '亿元',
    part: '基础设施投资', whole: '固定资产投资', other: '制造业投资',
    avgObj: '建设项目', avgHead: '完成投资', avgUnit: '万元',
    openLabel: '全年固定资产投资',
    wholeQty: [22000, 48000], partShare: [0.22, 0.38],
    cutTitle: '分领域看',
    regionTitle: '分主体看', regionA: '民间投资', regionB: '国有控股投资',
    flowTitle: '到位资金方面', flowWhole: '项目到位资金', flowPart: '国家预算资金', flowOther: '国内贷款及其他到位资金',
    flowQty: [18000, 40000], flowPartShare: [0.08, 0.18],
    stockName: '在建项目个数', stockNameUnit: '个', stockQty: [4200, 9800],
    headName: '新开工项目数',
    extras: [
      '高技术产业投资快于全部投资，房地产开发投资可能低位运行。',
      '民间投资和基础设施投资有交叉，不是互斥切块。到位资金不是完成投资。',
    ],
  },
  {
    id: 'realty', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '该市', '全省'],
    lead: '房地产市场逐步调整，保障性住房建设加快',
    tip: '房地产：销售、开工、到位资金不要串',
    stock: '商品房待售面积', stockUnit: '万平方米',
    item: '商品房销售面积', flow: '房地产开发投资',
    unit: '万平方米', unit2: '亿元',
    part: '住宅销售面积', whole: '商品房销售面积', other: '办公及商业营业用房销售面积',
    avgObj: '商品房', avgHead: '销售套数', avgUnit: '平方米',
    openLabel: '全年商品房销售面积',
    wholeQty: [4200, 9800], partShare: [0.78, 0.90],
    cutTitle: '按用途分',
    regionTitle: '分城市看', regionA: '省会城市销售面积', regionB: '其他城市销售面积',
    flowTitle: '开发投资方面', flowWhole: '房地产开发投资', flowPart: '住宅投资', flowOther: '非住宅投资',
    flowQty: [3800, 9200], flowPartShare: [0.68, 0.86],
    stockName: '商品房待售面积', stockNameUnit: '万平方米', stockQty: [1800, 5600],
    headName: '房地产开发企业数',
    extras: [
      '新开工面积和竣工面积走势可能相反。保障性住房完成投资占比上升。',
      '销售面积是时期量，待售面积是时点库存。投资额单位是亿元，面积是万平方米。',
    ],
  },
  {
    id: 'retail', kind: 'ytd',
    place: '该省', places: ['该省', '该市', '全省'],
    lead: '消费品市场稳步回升',
    tip: '社零：累计、当月、商品与餐饮不要串',
    stock: '限上商贸单位累计数', stockUnit: '家',
    item: '社会消费品零售总额', flow: '商品零售额',
    unit: '亿元', unit2: '亿元',
    part: '商品零售额', whole: '社会消费品零售总额', other: '餐饮收入',
    avgObj: '限上单位', avgHead: '从业人员', avgUnit: '万元',
    ytdQty: [18000, 36000], monthQty: [1600, 3800], partShare: [0.82, 0.92],
    decoyName: '网上零售额', decoyUnit: '亿元', decoyQty: [4200, 9800],
    headName: '限上商贸单位数',
    extras: [
      '汽车、石油及制品类拉动商品零售，餐饮收入恢复快于商品。升级类商品零售增速更高。',
      '网上零售额与社零口径不完全等同，不能直接当部分量去除。先看1—11月还是当月。',
    ],
  },
  {
    id: 'agri', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全国', '全省'],
    lead: '粮食生产再获丰收，重要农产品供应稳定',
    tip: '农业：产量、播种面积、产值不要串',
    stock: '农业机械总动力', stockUnit: '万千瓦',
    item: '粮食产量', flow: '农林牧渔业总产值',
    unit: '万吨', unit2: '亿元',
    part: '秋粮产量', whole: '粮食产量', other: '夏粮产量',
    avgObj: '播种面积', avgHead: '粮食产量', avgUnit: '公斤',
    openLabel: '全年粮食产量',
    wholeQty: [3200, 6800], partShare: [0.68, 0.82],
    cutTitle: '分季节看',
    regionTitle: '分品种看', regionA: '稻谷产量', regionB: '玉米及小麦产量',
    flowTitle: '产值方面', flowWhole: '农林牧渔业总产值', flowPart: '畜牧业产值', flowOther: '种植业产值',
    flowQty: [4800, 9800], flowPartShare: [0.28, 0.42],
    stockName: '农业机械总动力', stockNameUnit: '万千瓦', stockQty: [2800, 7200],
    headName: '乡村从业人员',
    extras: [
      '生猪出栏和肉类产量可能与粮食走势不一致。高标准农田面积继续增加。',
      '产量是实物量，总产值是价值量。播种面积在分母，不要把面积增速当成单产。',
    ],
  },
  {
    id: 'jobs', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省', '全国'],
    lead: '就业形势总体稳定，重点群体就业得到保障',
    tip: '就业：城镇新增、调查失业率、工资不要串',
    stock: '城镇就业人员', stockUnit: '万人',
    item: '城镇新增就业', flow: '城镇居民人均可支配收入',
    unit: '万人', unit2: '元',
    part: '服务业新增就业', whole: '城镇新增就业', other: '其他行业新增就业',
    avgObj: '就业人员', avgHead: '平均工资', avgUnit: '元',
    openLabel: '全年城镇新增就业',
    wholeQty: [85, 180], partShare: [0.18, 0.32],
    cutTitle: '按产业分',
    regionTitle: '分群体看', regionA: '高校毕业生就业人数', regionB: '农民工就业人数',
    flowTitle: '收入方面', flowWhole: '城镇就业人员平均工资', flowPart: '制造业平均工资', flowOther: '非制造业平均工资',
    flowQty: [72000, 128000], flowPartShare: [0.42, 0.58],
    stockName: '城镇就业人员', stockNameUnit: '万人', stockQty: [2800, 6200],
    headName: '职业介绍机构数',
    extras: [
      '调查失业率是比率，城镇新增就业是增量。平均工资是水平值，不要和增长率混读。',
      '材料若同时给失业率和新增就业，先看问的是人数还是百分点。',
    ],
  },
  {
    id: 'edu', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省', '某高校'],
    lead: '教育事业高质量发展，人才培养结构优化',
    tip: '教育：招生、在校、毕业不要串',
    stock: '在校生人数', stockUnit: '万人',
    item: '高等教育招生人数', flow: '教育经费投入',
    unit: '万人', unit2: '亿元',
    part: '研究生招生', whole: '高等教育招生', other: '本科招生',
    avgObj: '高校', avgHead: '专任教师', avgUnit: '人',
    openLabel: '全年高等教育招生',
    wholeQty: [68, 140], partShare: [0.12, 0.22],
    cutTitle: '按层次分',
    regionTitle: '分类型看', regionA: '普通本科招生', regionB: '高职专科招生',
    flowTitle: '经费方面', flowWhole: '教育经费投入', flowPart: '财政性教育经费', flowOther: '非财政教育经费',
    flowQty: [1800, 4200], flowPartShare: [0.72, 0.88],
    stockName: '在校生人数', stockNameUnit: '万人', stockQty: [220, 480],
    headName: '专任教师数',
    extras: [
      '职业本科和高职招生计划扩张，研究生招生增速可能高于本科。义务教育在校生受人口结构影响。',
      '招生是当年增量，在校生是存量。经费是亿元，人数是万人，不要看串行。',
    ],
  },
  {
    id: 'rd', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省', '全国'],
    lead: '研发投入强度稳步提升，科技成果加快转化',
    tip: '研发：经费、强度、专利不要串',
    stock: '有效发明专利拥有量', stockUnit: '万件',
    item: '研发经费投入', flow: '技术合同成交额',
    unit: '亿元', unit2: '亿元',
    part: '企业研发经费', whole: '研发经费投入', other: '高校及研究机构研发经费',
    avgObj: '规模以上企业', avgHead: '研发人员', avgUnit: '万元',
    openLabel: '全年研发经费投入',
    wholeQty: [1800, 4200], partShare: [0.72, 0.88],
    cutTitle: '按主体分',
    regionTitle: '分产业看', regionA: '高技术产业研发经费', regionB: '其他行业研发经费',
    flowTitle: '转化方面', flowWhole: '技术合同成交额', flowPart: '技术开发合同成交额', flowOther: '技术转让及其他合同成交额',
    flowQty: [2200, 6800], flowPartShare: [0.48, 0.68],
    stockName: '有效发明专利拥有量', stockNameUnit: '万件', stockQty: [12, 38],
    headName: '研发人员全时当量',
    extras: [
      '研发投入强度是经费除以 GDP 或营收，不是经费本身的增速。专利授权量是当年流量，拥有量是存量。',
      '企业经费占大头，但高校经费增速可能更快。先看问经费、强度还是专利。',
    ],
  },
  {
    id: 'transport', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省', '全国'],
    lead: '客货运输稳步恢复，综合交通网效率提升',
    tip: '交通：客运、货运、周转量不要串',
    stock: '公路通车里程', stockUnit: '万公里',
    item: '货运量', flow: '货物周转量',
    unit: '亿吨', unit2: '亿吨公里',
    part: '公路货运量', whole: '货运量', other: '水路货运量',
    avgObj: '营运车辆', avgHead: '货运量', avgUnit: '吨',
    openLabel: '全年货运量',
    wholeQty: [18, 42], partShare: [0.68, 0.82],
    cutTitle: '按运输方式分',
    regionTitle: '客运方面', regionA: '公路客运量', regionB: '铁路及民航客运量',
    flowTitle: '周转量方面', flowWhole: '货物周转量', flowPart: '水路货物周转量', flowOther: '公路货物周转量',
    flowQty: [12000, 36000], flowPartShare: [0.42, 0.62],
    stockName: '公路通车里程', stockNameUnit: '万公里', stockQty: [12, 28],
    headName: '营运性货运车辆数',
    extras: [
      '客运量恢复快于货运的年份并不少见。民航客运量绝对值小、增速高。',
      '货运量是吨，周转量是吨公里。里程是时点存量。不要把客运量写进货运问题。',
    ],
  },
  {
    id: 'express', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '该市', '全省'],
    lead: '邮政快递业高位运行，农村寄递物流加快完善',
    tip: '快递：件量、收入、农村件不要串',
    stock: '快递服务营业网点', stockUnit: '万个',
    item: '快递业务量', flow: '快递业务收入',
    unit: '亿件', unit2: '亿元',
    part: '同城快递业务量', whole: '快递业务量', other: '异地快递业务量',
    avgObj: '快递件', avgHead: '业务收入', avgUnit: '元',
    openLabel: '全年快递业务量',
    wholeQty: [80, 220], partShare: [0.12, 0.22],
    cutTitle: '按流向分',
    regionTitle: '分区域看', regionA: '农村地区快递业务量', regionB: '城市地区快递业务量',
    flowTitle: '收入方面', flowWhole: '快递业务收入', flowPart: '异地件收入', flowOther: '同城及国际件收入',
    flowQty: [680, 1800], flowPartShare: [0.55, 0.75],
    stockName: '快递服务营业网点', stockNameUnit: '万个', stockQty: [2.1, 6.8],
    headName: '快递从业人员',
    extras: [
      '单票收入可能下降，业务量高增不一定带来收入同幅增长。国际/港澳台件量小、单价高。',
      '业务量是件，收入是亿元。网点是存量。农村件是切块，不是另一套全省合计。',
    ],
  },
  {
    id: 'income', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '该市', '全省'],
    lead: '居民收入稳步增长，消费基础继续夯实',
    tip: '居民：城镇、农村、工资性收入不要串',
    stock: '住户存款余额', stockUnit: '亿元',
    item: '全体居民人均可支配收入', flow: '人均消费支出',
    unit: '元', unit2: '元',
    part: '工资性收入', whole: '全体居民人均可支配收入', other: '经营财产及转移净收入',
    avgObj: '常住居民', avgHead: '人均可支配收入', avgUnit: '元',
    openLabel: '全体居民人均可支配收入',
    wholeQty: [32000, 56000], partShare: [0.55, 0.68],
    cutTitle: '按城乡分',
    regionTitle: '按城乡分', regionA: '城镇居民工资性收入', regionB: '农村居民工资性收入',
    flowTitle: '消费方面', flowWhole: '人均消费支出', flowPart: '服务性消费支出', flowOther: '商品性消费支出',
    flowQty: [21000, 38000], flowPartShare: [0.38, 0.52],
    stockName: '住户存款余额', stockNameUnit: '亿元', stockQty: [28000, 72000],
    headName: '常住人口',
    extras: [
      '农村居民收入增速常常快于城镇，但绝对水平仍低。转移净收入占比在农村更高。',
      '全体居民收入不是城镇加农村的简单平均。存款余额是时点存量，收入是时期量。',
    ],
  },
  {
    id: 'eco', kind: 'tree', open: 'year',
    place: '该省', places: ['该省', '全省', '该市'],
    lead: '绿色转型扎实推进，主要污染物排放持续下降',
    tip: '环境：排放量、优良天数、处理率不要串',
    stock: '城市污水处理厂座数', stockUnit: '座',
    item: '化学需氧量排放量', flow: '一般工业固体废物产生量',
    unit: '万吨', unit2: '万吨',
    part: '工业化学需氧量排放量', whole: '化学需氧量排放量', other: '生活及其他化学需氧量排放量',
    avgObj: '监测城市', avgHead: '优良天数', avgUnit: '天',
    openLabel: '全年化学需氧量排放量',
    wholeQty: [28, 86], partShare: [0.28, 0.48],
    cutTitle: '按来源分',
    regionTitle: '分地区看', regionA: '工业聚集区化学需氧量排放量', regionB: '其他地区化学需氧量排放量',
    flowTitle: '固废方面', flowWhole: '一般工业固体废物产生量', flowPart: '综合利用量', flowOther: '处置及贮存量',
    flowQty: [8000, 22000], flowPartShare: [0.55, 0.78],
    stockName: '城市污水处理厂座数', stockNameUnit: '座', stockQty: [180, 620],
    headName: '环境监察执法人员',
    extras: [
      '排放量下降是减量，优良天数比例是比率。危废与一般工业固废不是同一口径。',
      '处理率和排放量可能一升一降。座数是存量，产生量是时期量。',
    ],
  },
];

const SPOT_TYPES = [
  {
    answer: '现期量',
    concepts: ['现期量', 'ABRX'],
    reason: '问的就是材料当年的绝对量，没有「上年」，也不问占比或增速。',
    tpls: [
      '{y}年，{place}{item}约为（ ）{unit}。',
      '{y}年，{place}{item}是多少{unit}？',
    ],
  },
  {
    answer: '基期量',
    concepts: ['基期量', 'ABRX'],
    reason: '问的是上一年的绝对量。材料给现期和增速，用现期÷(1+r)。指标叫不叫「累计」不影响定型。',
    tpls: [
      '材料给出{y}年{item}及同比增速，{y1}年该量约为（ ）{unit}。',
      '已知{y}年末{stock}及比上年末增速，{y1}年末该量约为（ ）{unit}。',
      '{y1}年，{place}{item}约为多少{unit}？（材料仅给出{y}年现期量与增长率）',
    ],
  },
  {
    answer: '累计量',
    concepts: ['累计量', '存量', '统计术语'],
    reason: '「累计建成 / 保有量 / 1—n月累计」问的是时点存量或年内累计。题干没有让你倒推上年，所以不是基期量；也要和当月发生额分开。',
    tpls: [
      '{y}年末，{place}{stock}约为（ ）{unit}。',
      '截至{y}年底，{place}{stock}约为多少{unit}？',
      '{y}年1—11月，{place}{flow}累计约为（ ）{unit2}。',
    ],
  },
  {
    answer: '当期量',
    concepts: ['当期量', '当月', '统计术语'],
    reason: '问的是当月/该月发生额，要和1—n月累计、全年累计区分开。',
    tpls: [
      '{y}年12月，{place}{item}当月约为（ ）{unit}。',
      '{y}年12月当月，{place}{flow}约为多少{unit2}？',
    ],
  },
  {
    answer: '增长量',
    concepts: ['增长量', 'ABRX'],
    reason: '问比上年「增加多少」，带单位的绝对变化，是增长量不是增长率。',
    tpls: [
      '{y}年，{place}{item}比上年增加约（ ）{unit}。',
      '{y}年，{place}{part}较上年末增加约多少{unit}？',
    ],
  },
  {
    answer: '增长率',
    concepts: ['增长率', '同比增速'],
    reason: '问同比增减幅度，不是绝对量，数量关系是增长率。',
    tpls: [
      '{y}年，{place}{item}的同比增长率是多少？',
      '{y}年，{place}{part}的同比增速约为：',
    ],
  },
  {
    answer: '现期比重',
    concepts: ['现期比重', '现期比重计算', '比重'],
    reason: '题目询问部分量占总体量的比例，数量关系是比重。',
    tpls: [
      '{y}年，{place}{part}占{whole}的比重约为多少？',
      '{y}年，{part}在{whole}中所占比重为（ ）。',
    ],
  },
  {
    answer: '基期比重',
    concepts: ['基期比重', '比重'],
    reason: '问的是上一年部分占总体的比例，要用现期比重×(1+b)/(1+a)。',
    tpls: [
      '材料给出{y}年数据，{y1}年{place}{part}占{whole}的比重约为多少？',
      '材料为{y}年数据，{y1}年{part}占{whole}的比重约为：',
    ],
  },
  {
    answer: '两期比重差',
    concepts: ['两期比重差', '比重升降'],
    reason: '问比重比上年提高/下降几个百分点，先看 a 与 b 再估差值。',
    tpls: [
      '{y}年，{place}{part}占{whole}的比重比上年（ ）。',
      '{y}年，{part}占{whole}的比重比上年提高/下降多少个百分点？',
    ],
  },
  {
    answer: '平均数',
    concepts: ['平均数', '均前除后'],
    reason: '问人均、每个、平均每个，分子总量、分母份数。',
    tpls: [
      '{y}年，{place}平均每个{avgObj}对应的{avgHead}约为多少{avgUnit}？',
      '{y}年，{place}{avgObj}的人均相关指标约为（ ）。',
    ],
  },
  {
    answer: '倍数',
    concepts: ['倍数', '倍数比较'],
    reason: '问 A 是 B 的多少倍，不是增速，也不是比重。',
    tpls: [
      '{y}年，{place}{part}约是{other}的多少倍？',
      '{y}年，{part}约为{other}的（ ）倍。',
    ],
  },
  {
    answer: '拉动增长率',
    concepts: ['拉动增长', '特殊考点'],
    reason: '「拉动……增长几个百分点」分母是整体基期，不是整体增量。',
    tpls: [
      '{y}年，{part}拉动{whole}增长约多少个百分点？',
      '{y}年，{place}{part}对{whole}增长的拉动约为：',
    ],
  },
  {
    answer: '贡献率',
    concepts: ['贡献率', '增量贡献'],
    reason: '「对增长的贡献率」分母是整体增量，不要和拉动混淆。',
    tpls: [
      '{y}年，{part}对{whole}增长的贡献率约为（ ）。',
      '{y}年，{place}{part}对增长的贡献率约为多少？',
    ],
  },
  {
    answer: '年均增长率',
    concepts: ['年均增长', '间隔年份'],
    reason: '跨多年问年均增速，先数间隔年份 n，再用 (1+R)^n ≈ 末期/基期。',
    tpls: [
      '{y0}—{y}年，{place}{item}的年均增长率约为：',
      '{y0}年至{y}年，{place}{stock}年均增速约为多少？',
    ],
  },
];

const spotZiliao = () => {
  const row = pick(SPOT_TYPES);
  const topic = pick(THEMES);
  const y = YEAR();
  const ctx = { ...topic, y, y1: y - 1, y0: y - 4 };
  return wrapQ({
    kind: 'spot',
    module: 'ziliao',
    tag: '识别考点 · 资料分析',
    hint: '读题干，判断它真正在问什么。不用算。',
    prompt: fill(pick(row.tpls), ctx),
    answer: row.answer,
    reason: row.reason,
    concepts: row.concepts,
  });
};

// ---------- 识别考点：数量 ----------
const QUANT_SPOTS = [
  {
    answer: '工程问题',
    reason: '给出单独完工时间或效率，问合作/交替/剩余时间，是工程。',
    stem: () =>
      `甲单独完成某工程需要 ${rand(12, 24)} 天，乙单独需要 ${rand(18, 36)} 天，两人合作需要几天？`,
  },
  {
    answer: '行程 · 相遇',
    reason: '相向而行、初始距离、求相遇时间，是相遇。',
    stem: () =>
      `甲乙两地相距 ${rand(200, 800)} 千米，两车同时相向开出，甲速 ${rand(60, 90)}、乙速 ${rand(50, 80)}，几小时相遇？`,
  },
  {
    answer: '行程 · 追及',
    reason: '同向、一前一后，快的追上慢的，是追及。',
    stem: () =>
      `甲在前乙在后相距 ${rand(40, 200)} 米，甲速 ${rand(3, 6)} 米/秒，乙速 ${rand(7, 12)} 米/秒，乙几秒追上甲？`,
  },
  {
    answer: '浓度问题',
    reason: '盐水、溶液、混合或加水稀释，盯溶质不变。',
    stem: () =>
      `${rand(80, 200)} 克 ${rand(10, 30)}% 的盐水与 ${rand(80, 200)} 克 ${rand(20, 50)}% 的盐水混合，新浓度是多少？`,
  },
  {
    answer: '利润问题',
    reason: '进价、售价、打折、利润率，是经济利润。',
    stem: () =>
      `某商品进价 ${rand(80, 200)} 元，按定价的八折出售仍获利 ${rand(10, 30)}%，定价是多少？`,
  },
  {
    answer: '排列组合',
    reason: '从 n 个里取 k 个，问有序还是无序，走排列或组合。',
    stem: () =>
      `从 ${rand(6, 10)} 名员工中选 ${rand(2, 4)} 人参加培训，有多少种选法？`,
  },
  {
    answer: '容斥',
    reason: '两集合或三集合「都喜欢 / 至少一项」，用容斥。',
    stem: () =>
      `班上 ${rand(40, 60)} 人，喜欢数学的 ${rand(20, 35)} 人，喜欢英语的 ${rand(18, 32)} 人，都不喜欢的 ${rand(4, 10)} 人，两科都喜欢多少人？`,
  },
  {
    answer: '几何',
    reason: '周长、面积、相似、方阵外层，是几何或方阵。',
    stem: () =>
      `一个 ${rand(8, 16)}×${rand(8, 16)} 方阵的最外层共有几人？`,
  },
  {
    answer: '和差倍比',
    reason: '和、差、几倍一起出现，先设小或设份。',
    stem: () =>
      `甲比乙多 ${rand(20, 80)}，甲是乙的 ${pick([2, 3, 4])} 倍少 ${rand(4, 12)}，乙是多少？`,
  },
  {
    answer: '最值 / 不定方程',
    reason: '未知数多于方程，问最大最小，先不定方程再代选项。',
    stem: () =>
      `鸡兔同笼，共 ${rand(20, 40)} 个头 ${rand(60, 120)} 只脚，兔子最多几只？`,
  },
];

const spotQuant = () => {
  const row = pick(QUANT_SPOTS);
  return wrapQ({
    kind: 'spot',
    module: 'quant',
    tag: '识别考点 · 数量关系',
    hint: '读题干，判断题型模型。不用算。',
    prompt: row.stem(),
    answer: row.answer,
    reason: row.reason,
    concepts: [row.answer],
  });
};

// ---------- 识别考点：判断（广东：图形 + 逻辑，不考定义/类比） ----------
const LOGIC_SPOTS = [
  {
    answer: '削弱',
    reason: '问「最能削弱 / 质疑」，走削弱论证。',
    stem: '一项研究表明，常喝咖啡的人心脏病发病率更低。以下哪项如果为真，最能削弱该结论？',
  },
  {
    answer: '加强',
    reason: '问「最能支持 / 加强」，优先搭桥或补前提。',
    stem: '有人认为，城市绿化率提高是空气质量改善的主要原因。以下哪项最能支持该观点？',
  },
  {
    answer: '前提',
    reason: '问「必须假设 / 论证成立的前提」，找没它就断的那一步。',
    stem: '要得出「该政策必然提升就业」的结论，必须补充以下哪项作为前提？',
  },
  {
    answer: '结论',
    reason: '问「由此可以推出」，从题干信息往下推，不加戏。',
    stem: '根据以上陈述，以下哪项可以推出？',
  },
  {
    answer: '翻译推理',
    reason: '出现如果、只有、除非，先翻译再逆否。',
    stem: '如果下雨，则比赛延期。比赛没有延期。由此可以推出：',
  },
  {
    answer: '真假推理',
    reason: '几句话有真有假，先找矛盾再定位。',
    stem: '甲乙丙丁四人只有一人说真话。甲：是乙。乙：不是我。丙：是丁。丁：不是丙。谁说了真话？',
  },
  {
    answer: '图形推理',
    reason: '一组图找规律，先看元素组成再定位置/样式/属性/数量。',
    stem: '从所给的四个选项中，选择最合适的一个填入问号处，使之呈现一定的规律性：',
  },
  {
    answer: '图形推理',
    reason: '九宫格优先横看，再竖看；问号在正中优先看米字或 Z。',
    stem: '把下面的六个图形分为两类，使每一类图形都有各自的共同特征或规律：',
  },
];

const spotLogic = () => {
  const row = pick(LOGIC_SPOTS);
  return wrapQ({
    kind: 'spot',
    module: 'logic',
    tag: '识别考点 · 判断推理',
    hint: '读设问，判断论证类型或图形路径。',
    prompt: row.stem,
    answer: row.answer,
    reason: row.reason,
    concepts: [row.answer],
  });
};

// ---------- 识别考点：言语 ----------
const VERBAL_SPOTS = [
  {
    answer: '中心理解',
    reason: '问「意在说明 / 主旨 / 主要介绍」，找中心句，不纠细节。',
    stem: '近年来城市更新加快，老旧小区加装电梯的需求持续上升。不过受限于资金分摊、产权结构和低层住户意愿，不少项目推进缓慢。这段文字意在说明：',
  },
  {
    answer: '标题拟定',
    reason: '问「最适合做标题」，压缩中心，兼顾范围和吸引。',
    stem: '最适合做这段文字标题的是：',
  },
  {
    answer: '下文推断',
    reason: '问「接下来最可能讲」，看尾句引出的新话题。',
    stem: '根据上述文字，作者接下来最可能讲述的是：',
  },
  {
    answer: '语句填入',
    reason: '横线在段中或段首，填的句子要承上启下。',
    stem: '填入画横线部分最恰当的一项是：（横线在段落中间）',
  },
  {
    answer: '语句排序',
    reason: '几句话打乱，先抓首句和捆绑，再验证顺序。',
    stem: '将以上 4 个句子重新排列，语序正确的是：',
  },
  {
    answer: '细节判断',
    reason: '问「正确 / 不正确 / 符合文意」，逐项回文比对。',
    stem: '根据这段文字，下列说法正确的是：',
  },
  {
    answer: '逻辑填空',
    reason: '空在词语上，先看逻辑对应再辨词。',
    stem: '文化传承不是简单的复制，而是在（ ）中实现创造性转化。填入画横线部分最恰当的一项是：',
  },
  {
    answer: '逻辑填空',
    reason: '多空题先看句间关系（转折、递进、解释）。',
    stem: '对传统文化既不能（ ），也不能（ ），而应在理解的基础上创造性转化。',
  },
];

const spotVerbal = () => {
  const row = pick(VERBAL_SPOTS);
  return wrapQ({
    kind: 'spot',
    module: 'verbal',
    tag: '识别考点 · 言语理解',
    hint: '读设问，判断题型。片段还是填空，一眼定。',
    prompt: row.stem,
    answer: row.answer,
    reason: row.reason,
    concepts: [row.answer],
  });
};

export const READ_SPOT_GENERATORS = {
  spotZiliao,
  spotQuant,
  spotLogic,
  spotVerbal,
  findBasic: generateFindBasic,
  findAdv: generateFindAdv,
};

export const READ_SPOT_CATEGORY = {
  id: 'readSpot',
  name: '读题反应',
  desc: '定型与找数。点完成看答案，自己点对或错。练习不计入段位，晋升计入。',
  available: true,
  weight: 14,
  tag: '自觉申报',
  kind: 'selfReport',
  subs: [
    { id: 'spotZiliao', name: '识别考点 · 资料', gen: 'spotZiliao', weight: 5 },
    { id: 'spotQuant', name: '识别考点 · 数量', gen: 'spotQuant', weight: 4 },
    { id: 'spotLogic', name: '识别考点 · 判断', gen: 'spotLogic', weight: 3 },
    { id: 'spotVerbal', name: '识别考点 · 言语', gen: 'spotVerbal', weight: 3 },
    { id: 'findBasic', name: '找数 · 基础', gen: 'findBasic', weight: 5 },
    { id: 'findAdv', name: '找数 · 进阶', gen: 'findAdv', weight: 5 },
  ],
};

export const isSelfReportCat = (cat) => cat?.kind === 'selfReport';
