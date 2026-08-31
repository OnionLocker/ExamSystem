import { ARCHIVED_READ_SPOT_PACKS } from './readSpotArchivedPacks.js';

// 找数找词材料库：使用固定且自洽的公报数据，避免随机拼数破坏统计口径。
// [[key|原文]] 只用于字段定位；展示时会还原为普通正文。

const PACKS = [
  {
    id: 'rd',
    sums: [{ total: 'rd_total', parts: ['rd_basic', 'rd_apply', 'rd_test'] }],
    theme: '研究与试验发展经费',
    paragraphs: [
      '[[rd_year|2023年]]，全国共投入研究与试验发展（R&D）经费[[rd_total|33278.2亿元]]，比上年增加2574.2亿元，增长[[rd_total_r|8.4%]]；R&D经费投入强度为[[rd_intensity|2.64%]]，比上年提高0.08个百分点。按活动类型分，基础研究经费[[rd_basic|2212.4亿元]]，增长[[rd_basic_r|9.3%]]；应用研究经费[[rd_apply|3661.5亿元]]，增长6.7%；试验发展经费[[rd_test|27404.3亿元]]，增长[[rd_test_r|8.6%]]。',
      '按活动主体分，各类企业R&D经费[[rd_enterprise|25964.5亿元]]，比上年增长[[rd_enterprise_r|8.6%]]；[[rd_gov_subject|政府属研究机构]]经费[[rd_gov|3814.4亿元]]，增长[[rd_gov_r|1.1%]]；高等学校经费[[rd_college|2753.3亿元]]，增长[[rd_college_r|14.1%]]；其他主体经费746.0亿元，增长2.5%。企业、政府属研究机构和高等学校经费所占比重分别为[[rd_enterprise_share|78.0%]]、11.5%和8.3%。',
      '规模以上工业企业R&D经费[[rd_industry|21398.8亿元]]，比上年增长[[rd_industry_r|7.7%]]。其中，高技术制造业R&D经费[[rd_hightech|6245.5亿元]]，投入强度为2.91%；装备制造业R&D经费[[rd_equipment|12105.7亿元]]，增长[[rd_equipment_r|9.1%]]，占规模以上工业企业R&D经费的56.6%。',
    ],
    labels: {
      rd_gov_subject: '政府属研究机构主体名称',
      rd_enterprise_share: '企业R&D经费占比',
      rd_hightech: '高技术制造业R&D经费现期量',
      rd_total: '全国R&D经费现期量',
      rd_total_r: '全国R&D经费增速',
      rd_basic: '基础研究经费现期量',
      rd_basic_r: '基础研究经费增速',
      rd_test: '试验发展经费现期量',
      rd_test_r: '试验发展经费增速',
      rd_enterprise: '企业R&D经费现期量',
      rd_enterprise_r: '企业R&D经费增速',
      rd_gov: '政府属研究机构R&D经费现期量',
      rd_gov_r: '政府属研究机构R&D经费增速',
      rd_college: '高等学校R&D经费现期量',
      rd_college_r: '高等学校R&D经费增速',
      rd_industry: '规上工业企业R&D经费现期量',
      rd_industry_r: '规上工业企业R&D经费增速',
      rd_equipment: '装备制造业R&D经费现期量',
      rd_equipment_r: '装备制造业R&D经费增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年全国基础研究经费是多少？', keys: ['rd_basic'], reason: '第一段按活动类型分列，基础研究经费为2212.4亿元。' },
      { skill: '找率', prompt: '2023年政府属研究机构R&D经费同比增长多少？', keys: ['rd_gov_r'], reason: '第二段按活动主体分列，政府属研究机构经费对应增速为1.1%。' },
      { skill: '找主体', prompt: '材料中，3814.4亿元R&D经费对应哪类活动主体？', keys: ['rd_gov_subject'], reason: '3814.4亿元紧跟在“政府属研究机构”之后，不是全部研究机构或高等学校。' },
      { skill: '辨口径', prompt: '2023年各类企业R&D经费占全国R&D经费的比重是多少？', keys: ['rd_enterprise_share'], reason: '第二段直接给出企业经费所占比重为78.0%。' },
      { skill: '成对找数', prompt: '2023年规模以上工业企业R&D经费及其增速分别是多少？', keys: ['rd_industry', 'rd_industry_r'], reason: '第三段首句同时给出规上工业企业R&D经费和对应增速。' },
    ],
    advanced: [
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年全国基础研究经费约为多少亿元？', keys: ['rd_basic', 'rd_basic_r'], reason: '只需定位基础研究经费的现期量和同比增速。' },
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年高技术制造业R&D经费占规模以上工业企业R&D经费的比重约为多少？', keys: ['rd_hightech', 'rd_industry'], reason: '分子是高技术制造业R&D经费，分母是规上工业企业R&D经费。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年各类企业R&D经费占全国R&D经费的比重约为多少？', keys: ['rd_enterprise', 'rd_enterprise_r', 'rd_total', 'rd_total_r'], reason: '需找企业与全国R&D经费各自的现期量和增速，共四个数。' },
      { title: '两期比重差', formula: '比重差 = A/B ×（a-b）/（1+a）', prompt: '2023年装备制造业R&D经费占规上工业企业R&D经费的比重比上年变化多少个百分点？', keys: ['rd_equipment', 'rd_equipment_r', 'rd_industry', 'rd_industry_r'], reason: '需找部分与整体的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年基础研究经费和高等学校R&D经费，哪一项同比增量更大？', keys: ['rd_basic', 'rd_basic_r', 'rd_college', 'rd_college_r'], reason: '两个主体都要找齐现期量和增速。' },
    ],
  },
  {
    id: 'medical-insurance',
    sums: [{ total: 'mi_people', parts: ['mi_active', 'mi_retired'] }],
    theme: '职工基本医疗保险',
    paragraphs: [
      '[[mi_end|截至2023年末]]，全国参加职工基本医疗保险人数为[[mi_people|37094万人]]，比上年末增加851万人，增长[[mi_people_r|2.3%]]。从参保结构看，在职职工[[mi_active|27116万人]]，增长[[mi_active_r|1.9%]]；退休人员[[mi_retired|9978万人]]，增长[[mi_retired_r|3.6%]]。在职退休比为2.72。参加职工医保的人员中，企业职工28690万人，机关事业及灵活就业等其他人员8404万人。',
      '2023年，全国职工医保基金总收入[[mi_income|22880亿元]]，比上年增长[[mi_income_r|7.9%]]。其中，统筹基金收入[[mi_pool_income|14780亿元]]，增长[[mi_pool_income_r|8.5%]]；个人账户收入8100亿元，增长6.9%。基金总支出[[mi_expense|17750亿元]]，增长[[mi_expense_r|11.2%]]。其中，统筹基金支出[[mi_pool_expense|11650亿元]]，增长[[mi_pool_expense_r|13.8%]]；个人账户支出6100亿元，增长6.5%。',
      '2023年，全国职工医保基金[[mi_current_subject|当期结存]][[mi_current|5130亿元]]，其中统筹基金当期结存[[mi_pool_current|3130亿元]]，个人账户当期结存2000亿元。[[mi_cumulative_end|截至2023年末]]，职工医保基金[[mi_cumulative_subject|累计结存]][[mi_cumulative|34100亿元]]，其中统筹基金累计结存[[mi_pool_cumulative|20500亿元]]，个人账户累计结存13600亿元。',
    ],
    labels: {
      mi_pool_current: '统筹基金当期结存',
      mi_pool_cumulative: '统筹基金累计结存',
      mi_cumulative_end: '累计结存统计时点',
      mi_people: '职工医保参保人数现期量',
      mi_people_r: '职工医保参保人数增速',
      mi_active: '在职职工参保人数现期量',
      mi_active_r: '在职职工参保人数增速',
      mi_retired: '退休人员参保人数现期量',
      mi_retired_r: '退休人员参保人数增速',
      mi_income: '职工医保基金总收入',
      mi_income_r: '基金总收入增速',
      mi_pool_income: '统筹基金收入',
      mi_pool_income_r: '统筹基金收入增速',
      mi_expense: '职工医保基金总支出',
      mi_expense_r: '基金总支出增速',
      mi_pool_expense: '统筹基金支出',
      mi_pool_expense_r: '统筹基金支出增速',
    },
    basic: [
      { skill: '找数', prompt: '截至2023年末，全国职工医保退休人员有多少万人？', keys: ['mi_retired'], reason: '第一段参保结构中，退休人员为9978万人。' },
      { skill: '找率', prompt: '2023年全国职工医保统筹基金收入同比增长多少？', keys: ['mi_pool_income_r'], reason: '第二段统筹基金收入后对应的增速为8.5%。' },
      { skill: '辨累计与当期', prompt: '2023年全国职工医保统筹基金当期结存是多少？', keys: ['mi_pool_current'], reason: '第三段先列当期结存，统筹基金当期结存为3130亿元。' },
      { skill: '辨累计与当期', prompt: '截至2023年末，全国职工医保统筹基金累计结存是多少？', keys: ['mi_pool_cumulative'], reason: '第三段后半句列累计结存，统筹基金累计结存为20500亿元。' },
      { skill: '找时间', prompt: '材料中“职工医保基金累计结存34100亿元”对应的统计时间是什么？', keys: ['mi_cumulative_end'], reason: '累计结存是截至2023年末的时点存量。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年统筹基金收入占职工医保基金总收入的比重约为多少？', keys: ['mi_pool_income', 'mi_income'], reason: '需找统筹基金收入与基金总收入。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年全国职工医保统筹基金支出约为多少亿元？', keys: ['mi_pool_expense', 'mi_pool_expense_r'], reason: '需找统筹基金支出现期量和同比增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年全国职工医保基金总支出比上年增加约多少亿元？', keys: ['mi_expense', 'mi_expense_r'], reason: '需找基金总支出现期量和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年退休人员占职工医保参保人数的比重约为多少？', keys: ['mi_retired', 'mi_retired_r', 'mi_people', 'mi_people_r'], reason: '需找退休人员与参保总人数各自的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年职工医保基金总收入和总支出，哪一项同比增量更大？', keys: ['mi_income', 'mi_income_r', 'mi_expense', 'mi_expense_r'], reason: '收入和支出都要找齐现期量与增速。' },
    ],
  },
  {
    id: 'power',
    theme: '电力装机与发电',
    paragraphs: [
      '[[pw_end|截至2023年末]]，全国全口径发电装机容量[[pw_total|29.2亿千瓦]]，比上年末增长[[pw_total_r|13.9%]]。其中，火电装机容量[[pw_thermal|13.9亿千瓦]]，增长[[pw_thermal_r|4.1%]]；水电4.2亿千瓦，增长1.8%；核电5691万千瓦，增长2.4%；风电[[pw_wind|4.4亿千瓦]]，增长[[pw_wind_r|20.7%]]；太阳能发电[[pw_solar|6.1亿千瓦]]，增长[[pw_solar_r|55.2%]]。非化石能源发电装机容量[[pw_nonfossil|15.7亿千瓦]]，占总装机容量比重为53.9%。',
      '2023年，全国新增发电装机容量[[pw_added|3.7亿千瓦]]，比上年增加1.7亿千瓦。其中，新增火电5793万千瓦，新增风电7566万千瓦，新增太阳能发电[[pw_solar_added|2.2亿千瓦]]，新增水电914万千瓦。全国并网风电和太阳能发电合计装机规模从2022年底的7.6亿千瓦连续突破8亿、9亿、10亿千瓦大关，2023年底达到10.5亿千瓦。',
      '2023年，全国规模以上工业发电量[[pw_output|8.9万亿千瓦时]]，比上年增长[[pw_output_r|5.2%]]。其中，火电发电量[[pw_thermal_output|6.2万亿千瓦时]]，增长[[pw_thermal_output_r|6.1%]]；水电1.1万亿千瓦时，下降5.0%；核电4333亿千瓦时，增长3.7%；风电8090亿千瓦时，增长12.3%；太阳能发电2941亿千瓦时，增长17.2%。全国6000千瓦及以上电厂发电设备平均利用时间[[pw_hours|3592小时]]，比上年减少101小时；其中火电4466小时，水电3133小时。',
    ],
    labels: {
      pw_end: '发电装机统计时点',
      pw_solar_added: '全年新增太阳能装机容量',
      pw_hours: '发电设备平均利用时间',
      pw_total: '全国发电装机总容量',
      pw_total_r: '全国发电装机总容量增速',
      pw_thermal: '火电装机容量',
      pw_thermal_r: '火电装机容量增速',
      pw_wind: '风电装机容量',
      pw_wind_r: '风电装机容量增速',
      pw_solar: '太阳能发电装机容量',
      pw_solar_r: '太阳能发电装机容量增速',
      pw_output: '规上工业发电量',
      pw_output_r: '规上工业发电量增速',
      pw_thermal_output: '火电发电量',
      pw_thermal_output_r: '火电发电量增速',
    },
    basic: [
      { skill: '找时间', prompt: '材料中“非化石能源发电装机容量15.7亿千瓦”对应的统计时间是什么？', keys: ['pw_end'], reason: '该数据位于“截至2023年末”这一时点口径下。' },
      { skill: '找数', prompt: '截至2023年末，全国太阳能发电装机容量是多少？', keys: ['pw_solar'], reason: '第一段按电源类型分列，太阳能发电装机容量为6.1亿千瓦。' },
      { skill: '辨存量与增量', prompt: '2023年全国新增太阳能发电装机容量是多少？', keys: ['pw_solar_added'], reason: '第二段列的是全年新增装机，不是年末装机存量。' },
      { skill: '找率', prompt: '2023年全国规模以上工业火电发电量同比增长多少？', keys: ['pw_thermal_output_r'], reason: '第三段火电发电量后对应增速为6.1%。' },
      { skill: '辨统计范围', prompt: '2023年全国6000千瓦及以上电厂发电设备平均利用时间是多少？', keys: ['pw_hours'], reason: '第三段末明确给出统计范围和平均利用时间。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年末太阳能发电装机容量占全国发电装机总容量的比重约为多少？', keys: ['pw_solar', 'pw_total'], reason: '分子为太阳能装机，分母为全口径发电装机。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年末全国风电装机容量约为多少亿千瓦？', keys: ['pw_wind', 'pw_wind_r'], reason: '需找风电装机现期量及其比上年末增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年火电发电量占规模以上工业发电量的比重约为多少？', keys: ['pw_thermal_output', 'pw_thermal_output_r', 'pw_output', 'pw_output_r'], reason: '需找火电发电量与总发电量各自的现期量和增速。' },
      { title: '两期比重差', formula: '比重差 = A/B ×（a-b）/（1+a）', prompt: '2023年末火电装机容量占全国发电装机总容量的比重比上年变化多少个百分点？', keys: ['pw_thermal', 'pw_thermal_r', 'pw_total', 'pw_total_r'], reason: '需找火电装机与总装机各自的现期量和增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年全国规模以上工业发电量比上年增加约多少万亿千瓦时？', keys: ['pw_output', 'pw_output_r'], reason: '需找规上工业发电量现期值及同比增速。' },
    ],
  },
  {
    id: 'income',
    theme: '居民收支与住户存款',
    paragraphs: [
      '[[in_year|2023年]]，全国居民人均可支配收入[[in_disposable|39218元]]，比上年名义增长[[in_disposable_r|6.3%]]，扣除价格因素实际增长[[in_real_r|6.1%]]。分城乡看，城镇居民人均可支配收入[[in_urban|51821元]]，名义增长[[in_urban_r|5.1%]]；农村居民人均可支配收入[[in_rural|21691元]]，名义增长[[in_rural_r|7.7%]]。城乡居民人均可支配收入比为2.39，比上年缩小0.06。',
      '按收入来源分，全国居民人均工资性收入[[in_wage|22053元]]，增长[[in_wage_r|7.1%]]，占可支配收入的56.2%；人均经营净收入6542元，增长6.6%；人均财产净收入[[in_property|3362元]]，增长[[in_property_r|4.2%]]；人均转移净收入[[in_transfer|7261元]]，增长5.4%。全国居民人均消费支出[[in_consumption|26796元]]，增长[[in_consumption_r|9.2%]]；其中城镇居民32994元，增长8.6%，农村居民[[in_rural_consumption|18175元]]，增长[[in_rural_consumption_r|9.3%]]。',
      '[[in_end|截至2023年末]]，住户人民币存款余额[[in_deposit|137.9万亿元]]，比年初增加[[in_deposit_add|16.7万亿元]]，同比增长[[in_deposit_r|13.8%]]。全年人民币存款增加25.7万亿元，其中住户存款增加16.7万亿元，非金融企业存款增加4.2万亿元，财政性存款增加2481亿元，非银行业金融机构存款增加2.0万亿元。',
    ],
    labels: {
      in_real_r: '居民人均可支配收入实际增速',
      in_transfer: '居民人均转移净收入',
      in_end: '住户存款余额统计时点',
      in_deposit_add: '住户存款比年初增加额',
      in_disposable: '居民人均可支配收入',
      in_disposable_r: '居民人均可支配收入名义增速',
      in_urban: '城镇居民人均可支配收入',
      in_urban_r: '城镇居民人均可支配收入名义增速',
      in_rural: '农村居民人均可支配收入',
      in_rural_r: '农村居民人均可支配收入名义增速',
      in_wage: '居民人均工资性收入',
      in_wage_r: '居民人均工资性收入增速',
      in_property: '居民人均财产净收入',
      in_property_r: '居民人均财产净收入增速',
      in_consumption: '居民人均消费支出',
      in_consumption_r: '居民人均消费支出增速',
      in_rural_consumption: '农村居民人均消费支出',
      in_rural_consumption_r: '农村居民人均消费支出增速',
    },
    basic: [
      { skill: '辨名义与实际', prompt: '2023年全国居民人均可支配收入实际增长多少？', keys: ['in_real_r'], reason: '第一段先列名义增速6.3%，随后列扣除价格因素后的实际增速6.1%。' },
      { skill: '找数', prompt: '2023年全国居民人均转移净收入是多少？', keys: ['in_transfer'], reason: '第二段按收入来源分列，人均转移净收入为7261元。' },
      { skill: '辨城乡', prompt: '2023年农村居民人均消费支出是多少？', keys: ['in_rural_consumption'], reason: '第二段消费支出部分，农村居民对应18175元。' },
      { skill: '找时间', prompt: '材料中“住户人民币存款余额137.9万亿元”对应的统计时间是什么？', keys: ['in_end'], reason: '存款余额对应截至2023年末这一时点。' },
      { skill: '辨余额与增量', prompt: '2023年住户人民币存款比年初增加多少？', keys: ['in_deposit_add'], reason: '第三段137.9万亿元是余额，16.7万亿元才是比年初增加额。' },
    ],
    advanced: [
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年城镇居民人均可支配收入约为多少元？', keys: ['in_urban', 'in_urban_r'], reason: '需找城镇居民收入现期量和名义增速。' },
      { title: '现期比重', formula: '消费率 = 人均消费支出 ÷ 人均可支配收入', prompt: '2023年全国居民平均消费率约为多少？', keys: ['in_consumption', 'in_disposable'], reason: '需找全国居民人均消费支出和人均可支配收入。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年全国居民人均工资性收入占人均可支配收入的比重约为多少？', keys: ['in_wage', 'in_wage_r', 'in_disposable', 'in_disposable_r'], reason: '需找工资性收入与可支配收入各自的现期量和增速。' },
      { title: '两期比重差', formula: '比重差 = A/B ×（a-b）/（1+a）', prompt: '2023年人均财产净收入占人均可支配收入的比重比上年变化多少个百分点？', keys: ['in_property', 'in_property_r', 'in_disposable', 'in_disposable_r'], reason: '需找财产净收入与可支配收入各自的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年城镇和农村居民人均可支配收入，哪一项同比增加额更大？', keys: ['in_urban', 'in_urban_r', 'in_rural', 'in_rural_r'], reason: '城镇、农村两组现期量和增速都要定位。' },
    ],
  },
  {
    id: 'trade',
    sums: [{ total: 'tr_total', parts: ['tr_export', 'tr_import'] }],
    theme: '货物进出口',
    paragraphs: [
      '[[tr_year|2023年]]，我国货物进出口总额[[tr_total|417568亿元]]，比上年增长[[tr_total_r|0.2%]]。其中，出口[[tr_export|237726亿元]]，增长[[tr_export_r|0.6%]]；进口[[tr_import|179842亿元]]，下降[[tr_import_r|0.3%]]。货物进出口顺差[[tr_balance|57884亿元]]，比上年增加[[tr_balance_add|1938亿元]]。',
      '从贸易方式看，一般贸易进出口[[tr_general|269781亿元]]，增长[[tr_general_r|2.0%]]；加工贸易进出口76432亿元，下降4.1%。从企业性质看，民营企业进出口[[tr_private|223601亿元]]，增长[[tr_private_r|6.3%]]；外商投资企业进出口[[tr_foreign|126172亿元]]，下降[[tr_foreign_r|3.9%]]；国有企业进出口67795亿元，增长0.3%。',
      '从主要商品看，机电产品出口[[tr_machinery|139205亿元]]，增长[[tr_machinery_r|2.9%]]，占出口总额的58.6%；高新技术产品出口49520亿元，下降4.5%。进口原油56399万吨，增长11.0%；进口集成电路4795亿个，下降10.8%。从主要贸易伙伴看，对东盟进出口[[tr_asean|64140亿元]]，增长[[tr_asean_r|0.5%]]；对欧盟55060亿元，下降1.9%；对美国46728亿元，下降6.6%；对共建“一带一路”国家进出口194719亿元，增长2.8%。',
    ],
    labels: {
      tr_year: '货物进出口统计年份',
      tr_balance_add: '货物进出口顺差增加额',
      tr_general: '一般贸易进出口额',
      tr_total: '货物进出口总额',
      tr_total_r: '货物进出口总额增速',
      tr_export: '货物出口额',
      tr_export_r: '货物出口额增速',
      tr_import: '货物进口额',
      tr_import_r: '货物进口额降幅',
      tr_private: '民营企业进出口额',
      tr_private_r: '民营企业进出口额增速',
      tr_foreign: '外商投资企业进出口额',
      tr_foreign_r: '外商投资企业进出口额降幅',
      tr_machinery: '机电产品出口额',
      tr_machinery_r: '机电产品出口额增速',
      tr_asean: '对东盟进出口额',
      tr_asean_r: '对东盟进出口额增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年我国民营企业进出口额是多少？', keys: ['tr_private'], reason: '第二段企业性质中，民营企业进出口额为223601亿元。' },
      { skill: '找率', prompt: '2023年我国机电产品出口额同比增长多少？', keys: ['tr_machinery_r'], reason: '第三段机电产品出口额后对应增速为2.9%。' },
      { skill: '找时间', prompt: '材料反映的是哪一年的货物进出口情况？', keys: ['tr_year'], reason: '首段首句给出统计年份为2023年。' },
      { skill: '辨现期与增量', prompt: '2023年我国货物进出口顺差比上年增加多少？', keys: ['tr_balance_add'], reason: '57884亿元是顺差现期值，1938亿元是同比增加额。' },
      { skill: '成对找数', prompt: '2023年我国货物进口额及其同比降幅分别是多少？', keys: ['tr_import', 'tr_import_r'], reason: '第一段进口数据同时给出进口额与下降幅度。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年一般贸易进出口额占我国货物进出口总额的比重约为多少？', keys: ['tr_general', 'tr_total'], reason: '需找一般贸易进出口额和货物进出口总额。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年我国货物出口额约为多少亿元？', keys: ['tr_export', 'tr_export_r'], reason: '需找出口现期额和同比增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年民营企业进出口额比上年增加约多少亿元？', keys: ['tr_private', 'tr_private_r'], reason: '需找民营企业进出口额和对应增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年机电产品出口额占货物出口额的比重约为多少？', keys: ['tr_machinery', 'tr_machinery_r', 'tr_export', 'tr_export_r'], reason: '需找机电产品出口和出口总额各自的现期量、增速。' },
      { title: '两期比重差', formula: '比重差 = A/B ×（a-b）/（1+a）', prompt: '2023年对东盟进出口额占我国进出口总额的比重比上年变化多少个百分点？', keys: ['tr_asean', 'tr_asean_r', 'tr_total', 'tr_total_r'], reason: '需找对东盟进出口与进出口总额各自的现期量和增速。' },
    ],
  },
  {
    id: 'express',
    sums: [{ total: 'ex_volume', parts: ['ex_city_volume', 'ex_remote_volume', 'ex_intl_volume'] }],
    theme: '邮政快递',
    paragraphs: [
      '[[ex_year|2023年]]，邮政行业寄递业务量完成[[ex_post_volume|1624.8亿件]]，同比增长[[ex_post_volume_r|16.8%]]；邮政行业业务收入（不包括邮政储蓄银行直接营业收入）完成[[ex_post_revenue|15293.8亿元]]，增长[[ex_post_revenue_r|13.2%]]。其中，快递业务量[[ex_volume|1320.7亿件]]，增长[[ex_volume_r|19.4%]]；快递业务收入[[ex_revenue|12074.0亿元]]，增长[[ex_revenue_r|14.3%]]。',
      '分专业类别看，同城快递业务量[[ex_city_volume|136.4亿件]]，增长[[ex_city_volume_r|6.6%]]，业务收入1188.8亿元，增长2.6%；异地快递业务量[[ex_remote_volume|1153.6亿件]]，增长[[ex_remote_volume_r|20.5%]]，业务收入6191.7亿元，增长14.7%；国际及港澳台快递业务量[[ex_intl_volume|30.7亿件]]，增长[[ex_intl_volume_r|52.0%]]，业务收入1469.0亿元，增长11.0%。',
      '分地区看，东、中、西部地区快递业务量比重分别为[[ex_east_share|75.2%]]、16.7%和8.1%，业务收入比重分别为76.2%、14.1%和9.7%。[[ex_end|年末]]全行业拥有各类营业网点[[ex_sites|43.4万处]]，其中快递营业网点23.4万处；农村邮政快递公共取送点[[ex_rural_sites|10.6万处]]，比上年末增长[[ex_rural_sites_r|5.1%]]。',
    ],
    labels: {
      ex_end: '营业网点统计时点',
      ex_east_share: '东部地区快递业务量比重',
      ex_post_volume: '邮政行业寄递业务量',
      ex_post_volume_r: '邮政行业寄递业务量增速',
      ex_post_revenue: '邮政行业业务收入',
      ex_post_revenue_r: '邮政行业业务收入增速',
      ex_volume: '快递业务量',
      ex_volume_r: '快递业务量增速',
      ex_revenue: '快递业务收入',
      ex_revenue_r: '快递业务收入增速',
      ex_city_volume: '同城快递业务量',
      ex_city_volume_r: '同城快递业务量增速',
      ex_remote_volume: '异地快递业务量',
      ex_remote_volume_r: '异地快递业务量增速',
      ex_intl_volume: '国际及港澳台快递业务量',
      ex_intl_volume_r: '国际及港澳台快递业务量增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年异地快递业务量是多少？', keys: ['ex_remote_volume'], reason: '第二段异地快递业务量为1153.6亿件。' },
      { skill: '找率', prompt: '2023年国际及港澳台快递业务量同比增长多少？', keys: ['ex_intl_volume_r'], reason: '第二段国际及港澳台快递业务量对应增速为52.0%。' },
      { skill: '找时间', prompt: '材料中“全行业拥有各类营业网点43.4万处”对应什么时间口径？', keys: ['ex_end'], reason: '网点数量对应年末时点。' },
      { skill: '辨大小口径', prompt: '2023年邮政行业业务收入和快递业务收入分别是多少？', keys: ['ex_post_revenue', 'ex_revenue'], reason: '第一段先给邮政行业大口径收入，再给其中快递业务收入。' },
      { skill: '辨量与率', prompt: '2023年东部地区快递业务量占全国的比重是多少？', keys: ['ex_east_share'], reason: '第三段地区结构中，东部业务量比重为75.2%。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年快递业务收入占邮政行业业务收入的比重约为多少？', keys: ['ex_revenue', 'ex_post_revenue'], reason: '需找快递业务收入和邮政行业业务收入。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年全国快递业务量约为多少亿件？', keys: ['ex_volume', 'ex_volume_r'], reason: '需找快递业务量现期值和增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年国际及港澳台快递业务量同比增加约多少亿件？', keys: ['ex_intl_volume', 'ex_intl_volume_r'], reason: '需找国际及港澳台业务量和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年异地快递业务量占快递业务总量的比重约为多少？', keys: ['ex_remote_volume', 'ex_remote_volume_r', 'ex_volume', 'ex_volume_r'], reason: '需找异地快递与快递总量各自的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年同城和国际及港澳台快递业务量，哪一项同比增量更大？', keys: ['ex_city_volume', 'ex_city_volume_r', 'ex_intl_volume', 'ex_intl_volume_r'], reason: '两个专业类别均需找现期量与增速。' },
    ],
  },
  {
    id: 'fiscal',
    sums: [{ total: 'fi_revenue', parts: ['fi_tax', 'fi_nontax'] }],
    theme: '财政收支',
    paragraphs: [
      '[[fi_year|2023年]]，某省一般公共预算收入[[fi_revenue|4860.5亿元]]，比上年增长[[fi_revenue_r|6.4%]]。其中，税收收入[[fi_tax|3402.3亿元]]，增长[[fi_tax_r|7.8%]]，占一般公共预算收入的70.0%；非税收入[[fi_nontax|1458.2亿元]]，增长3.2%。主要税种中，增值税1520.4亿元，增长15.6%；企业所得税680.5亿元，下降3.4%；个人所得税295.6亿元，增长1.8%。',
      '一般公共预算支出[[fi_expense|9240.8亿元]]，增长[[fi_expense_r|4.5%]]。其中，民生支出7207.8亿元，占一般公共预算支出的78.0%；教育支出[[fi_edu|1685.2亿元]]，增长[[fi_edu_r|5.2%]]；社会保障和就业支出[[fi_social|1450.6亿元]]，增长[[fi_social_r|8.0%]]；卫生健康支出965.4亿元，下降2.1%；农林水支出850.3亿元，增长4.0%。',
      '政府性基金预算收入[[fi_fund_revenue|2350.6亿元]]，比上年下降[[fi_fund_revenue_r|12.8%]]，其中[[fi_land_subject|国有土地使用权出让收入]]2085.4亿元，下降14.2%；政府性基金预算支出3120.4亿元，下降8.5%。[[fi_end|截至2023年末]]，地方政府[[fi_debt_subject|法定债务余额]][[fi_debt|16840.5亿元]]，其中一般债务6120.2亿元、专项债务10720.3亿元；当年发行地方政府新增债券[[fi_bond|1850.0亿元]]。',
    ],
    labels: {
      fi_end: '地方政府债务统计时点',
      fi_land_subject: '政府性基金收入项目名称',
      fi_debt_subject: '地方政府债务统计口径',
      fi_revenue: '一般公共预算收入',
      fi_revenue_r: '一般公共预算收入增速',
      fi_tax: '税收收入',
      fi_tax_r: '税收收入增速',
      fi_expense: '一般公共预算支出',
      fi_expense_r: '一般公共预算支出增速',
      fi_edu: '教育支出',
      fi_edu_r: '教育支出增速',
      fi_social: '社会保障和就业支出',
      fi_social_r: '社会保障和就业支出增速',
      fi_fund_revenue: '政府性基金预算收入',
      fi_fund_revenue_r: '政府性基金预算收入降幅',
    },
    basic: [
      { skill: '找数', prompt: '2023年该省社会保障和就业支出是多少？', keys: ['fi_social'], reason: '第二段主要支出项目中，社会保障和就业支出为1450.6亿元。' },
      { skill: '找率', prompt: '2023年该省政府性基金预算收入同比下降多少？', keys: ['fi_fund_revenue_r'], reason: '第三段政府性基金预算收入对应降幅为12.8%。' },
      { skill: '找时间', prompt: '材料中“地方政府法定债务余额16840.5亿元”对应的统计时间是什么？', keys: ['fi_end'], reason: '债务余额对应截至2023年末这一时点。' },
      { skill: '找主体', prompt: '2023年政府性基金预算收入中，2085.4亿元对应哪个收入项目？', keys: ['fi_land_subject'], reason: '该数值对应国有土地使用权出让收入。' },
      { skill: '辨口径', prompt: '2023年末该省16840.5亿元反映的是什么债务口径？', keys: ['fi_debt_subject'], reason: '第三段明确该数值为地方政府法定债务余额。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年税收收入占一般公共预算收入的比重约为多少？', keys: ['fi_tax', 'fi_revenue'], reason: '需找税收收入和一般公共预算收入。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该省一般公共预算支出约为多少亿元？', keys: ['fi_expense', 'fi_expense_r'], reason: '需找一般公共预算支出现期值和增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年该省税收收入同比增加约多少亿元？', keys: ['fi_tax', 'fi_tax_r'], reason: '需找税收收入现期值和对应增速。' },
      { title: '两期比重差', formula: '比重差 = A/B ×（a-b）/（1+a）', prompt: '2023年教育支出占一般公共预算支出的比重比上年变化多少个百分点？', keys: ['fi_edu', 'fi_edu_r', 'fi_expense', 'fi_expense_r'], reason: '需找教育支出与总支出各自的现期量、增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年教育支出和社会保障就业支出，哪项同比增量更大？', keys: ['fi_edu', 'fi_edu_r', 'fi_social', 'fi_social_r'], reason: '两个支出项目都要找齐现期量和增速。' },
    ],
  },
  {
    id: 'transport',
    theme: '综合交通运输',
    paragraphs: [
      '[[tp_year|2023年]]，某市综合交通客运量[[tp_passenger|38540万人次]]，比上年增长[[tp_passenger_r|24.5%]]。分运输方式看，铁路客运量[[tp_rail_passenger|12450万人次]]，增长[[tp_rail_passenger_r|35.2%]]；公路客运量[[tp_road_passenger|21560万人次]]，增长[[tp_road_passenger_r|16.8%]]；水路客运量680万人次，增长12.0%；民航客运量3850万人次，增长45.0%。旅客周转量852.4亿人公里，增长32.6%。',
      '全年货运量[[tp_freight|94620万吨]]，比上年增长[[tp_freight_r|8.2%]]。分运输方式看，铁路货运量8650万吨，增长3.5%；公路货运量[[tp_road_freight|68420万吨]]，增长[[tp_road_freight_r|9.1%]]；[[tp_second_subject|水路货运量]][[tp_water_freight|17520万吨]]，增长[[tp_water_freight_r|7.4%]]；民航货运量30万吨，增长15.4%。货物周转量[[tp_turnover|2180.5亿吨公里]]，增长6.8%，其中水路货物周转量[[tp_water_turnover|1340.2亿吨公里]]，增长7.5%。',
      '[[tp_end|年末]]综合交通网络总里程[[tp_network|28650公里]]。其中，公路线路里程26820公里，比上年末增加450公里；高速公路里程2180公里，增加65公里；铁路营业里程1420公里，其中[[tp_hsr_subject|高速铁路营业里程]][[tp_hsr|685公里]]；内河航道通航里程410公里。',
    ],
    labels: {
      tp_second_subject: '货运量第二大运输方式',
      tp_end: '交通网络里程统计时点',
      tp_hsr_subject: '685公里对应的铁路口径',
      tp_water_turnover: '水路货物周转量',
      tp_turnover: '货物周转总量',
      tp_passenger: '客运总量',
      tp_passenger_r: '客运总量增速',
      tp_rail_passenger: '铁路客运量',
      tp_rail_passenger_r: '铁路客运量增速',
      tp_road_passenger: '公路客运量',
      tp_road_passenger_r: '公路客运量增速',
      tp_freight: '货运总量',
      tp_freight_r: '货运总量增速',
      tp_road_freight: '公路货运量',
      tp_road_freight_r: '公路货运量增速',
      tp_water_freight: '水路货运量',
      tp_water_freight_r: '水路货运量增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年该市水路货运量是多少？', keys: ['tp_water_freight'], reason: '第二段分运输方式列出水路货运量17520万吨。' },
      { skill: '找率', prompt: '2023年该市铁路客运量同比增长多少？', keys: ['tp_rail_passenger_r'], reason: '第一段铁路客运量后对应增速为35.2%。' },
      { skill: '找主体', prompt: '2023年该市仅次于公路的第二大货运方式是什么？', keys: ['tp_second_subject'], reason: '比较各运输方式货运量，水路居第二。' },
      { skill: '找时间', prompt: '材料中“综合交通网络总里程28650公里”对应什么时间口径？', keys: ['tp_end'], reason: '线路里程是年末时点数据。' },
      { skill: '辨口径', prompt: '材料中685公里铁路线路具体指哪类营业里程？', keys: ['tp_hsr_subject'], reason: '第三段明确685公里对应高速铁路营业里程。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年水路货物周转量占全市货物周转量的比重约为多少？', keys: ['tp_water_turnover', 'tp_turnover'], reason: '需找水路货物周转量与货物周转总量。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该市铁路客运量约为多少万人次？', keys: ['tp_rail_passenger', 'tp_rail_passenger_r'], reason: '需找铁路客运量现期值和增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年该市货运总量比上年增加约多少万吨？', keys: ['tp_freight', 'tp_freight_r'], reason: '需找货运总量现期值和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年公路货运量占全市货运总量的比重约为多少？', keys: ['tp_road_freight', 'tp_road_freight_r', 'tp_freight', 'tp_freight_r'], reason: '需找公路货运量与货运总量各自的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年铁路和公路客运量，哪一项同比增量更大？', keys: ['tp_rail_passenger', 'tp_rail_passenger_r', 'tp_road_passenger', 'tp_road_passenger_r'], reason: '铁路、公路两组现期量和增速都要定位。' },
    ],
  },
  {
    id: 'agriculture',
    theme: '农业生产',
    paragraphs: [
      '[[ag_year|2023年]]，某省粮食播种面积[[ag_area|5462.8千公顷]]，比上年增加31.5千公顷，增长[[ag_area_r|0.6%]]。其中，夏粮播种面积[[ag_summer_area|1785.4千公顷]]，增长[[ag_summer_area_r|0.4%]]；秋粮播种面积3677.4千公顷，增长0.7%。粮食总产量[[ag_grain|3856.2万吨]]，比上年增产65.8万吨，增长[[ag_grain_r|1.7%]]。其中，夏粮产量[[ag_summer|1245.6万吨]]，增长[[ag_summer_r|1.2%]]；秋粮产量2610.6万吨，增长2.0%；谷物、豆类和薯类产量分别为3520.4万吨、185.3万吨和150.5万吨。',
      '油料种植面积[[ag_oil_area|890.5千公顷]]，增长[[ag_oil_area_r|2.5%]]；油料产量[[ag_oil|325.8万吨]]，增长[[ag_oil_r|3.8%]]。蔬菜及食用菌种植面积1420.0千公顷，增长1.8%，产量5860.5万吨，增长2.9%；园林水果产量1820.4万吨，增长4.2%。',
      '猪牛羊禽肉产量[[ag_meat|468.5万吨]]，增长[[ag_meat_r|3.5%]]。其中，猪肉[[ag_pork|342.1万吨]]，增长[[ag_pork_r|4.1%]]；牛肉35.6万吨，增长1.8%；羊肉[[ag_mutton|24.2万吨]]，下降[[ag_mutton_r|0.8%]]；禽肉66.6万吨，增长2.3%。[[ag_end|年末]]生猪存栏[[ag_pig_stock|2850.4万头]]，下降1.6%；全年生猪出栏[[ag_pig_output|4412.8万头]]，增长3.9%。农业机械总动力7250.6万千瓦，增长2.1%；主要农作物耕种收综合机械化率85.6%，提高1.2个百分点。',
    ],
    labels: {
      ag_pig_output: '全年生猪出栏量',
      ag_end: '生猪存栏统计时点',
      ag_mutton: '羊肉产量',
      ag_pig_stock: '年末生猪存栏量',
      ag_area: '粮食播种面积',
      ag_area_r: '粮食播种面积增速',
      ag_summer_area: '夏粮播种面积',
      ag_summer_area_r: '夏粮播种面积增速',
      ag_grain: '粮食总产量',
      ag_grain_r: '粮食总产量增速',
      ag_summer: '夏粮产量',
      ag_summer_r: '夏粮产量增速',
      ag_oil_area: '油料种植面积',
      ag_oil_area_r: '油料种植面积增速',
      ag_oil: '油料产量',
      ag_oil_r: '油料产量增速',
      ag_meat: '猪牛羊禽肉总产量',
      ag_meat_r: '猪牛羊禽肉总产量增速',
      ag_pork: '猪肉产量',
      ag_pork_r: '猪肉产量增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年该省全年生猪出栏量是多少？', keys: ['ag_pig_output'], reason: '第三段区分年末存栏与全年出栏，出栏量为4412.8万头。' },
      { skill: '找率', prompt: '2023年该省夏粮产量同比增长多少？', keys: ['ag_summer_r'], reason: '第一段夏粮产量后对应增速为1.2%。' },
      { skill: '找时间', prompt: '材料中“生猪存栏2850.4万头”对应什么时间口径？', keys: ['ag_end'], reason: '生猪存栏为年末时点数据。' },
      { skill: '找主体', prompt: '2023年猪牛羊禽肉中，哪一品种产量同比下降？', keys: ['ag_mutton'], answer: '羊肉', reason: '第三段四类肉产量中，仅羊肉下降0.8%。' },
      { skill: '辨存栏与出栏', prompt: '2023年末生猪存栏量是多少？', keys: ['ag_pig_stock'], reason: '第三段年末存栏为2850.4万头，不能取全年出栏量。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年夏粮产量占粮食总产量的比重约为多少？', keys: ['ag_summer', 'ag_grain'], reason: '需找夏粮产量与全年粮食总产量。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该省猪牛羊禽肉总产量约为多少万吨？', keys: ['ag_meat', 'ag_meat_r'], reason: '需找肉类总产量现期值和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年夏粮播种面积占粮食播种面积的比重约为多少？', keys: ['ag_summer_area', 'ag_summer_area_r', 'ag_area', 'ag_area_r'], reason: '需找夏粮与粮食总播种面积各自的现期量和增速。' },
      { title: '平均数', formula: '平均单产 = 总产量 ÷ 播种面积', prompt: '2023年该省粮食平均单产约为多少吨/公顷？', keys: ['ag_grain', 'ag_area'], reason: '需找粮食总产量和播种面积，并注意万吨与千公顷换算。' },
      { title: '平均数增长率', formula: '平均数增速 =（产量增速-面积增速）÷（1+面积增速）', prompt: '2023年该省油料平均单产同比增长约多少？', keys: ['ag_oil_r', 'ag_oil_area_r'], reason: '平均单产只需定位油料产量增速和种植面积增速。' },
    ],
  },
  {
    id: 'education',
    theme: '教育事业',
    paragraphs: [
      '[[ed_year|2023年]]，某省共有各级各类学校2.15万所，在校生[[ed_students|1468.2万人]]，专任教师98.6万人。学前教育毛入园率92.8%，提高0.5个百分点；幼儿园1.02万所，在园幼儿320.5万人，下降3.8%。义务教育阶段学校8560所，其中普通小学[[ed_primary_schools|5820所]]，招生105.4万人，在校生[[ed_primary_students|618.5万人]]，增长[[ed_primary_students_r|1.5%]]；初中2740所，招生96.8万人，在校生[[ed_junior_students|284.6万人]]，增长[[ed_junior_students_r|2.6%]]。',
      '高中阶段教育毛入学率94.2%。普通高中980所，招生[[ed_high_enrol|52.6万人]]，增长[[ed_high_enrol_r|4.2%]]，在校生151.2万人，毕业生46.8万人；[[ed_decline_subject|中等职业教育]]学校520所，招生[[ed_voc_enrol|31.5万人]]，下降[[ed_voc_enrol_r|1.6%]]，在校生88.4万人，下降0.9%，毕业生28.6万人，增长1.4%。',
      '高等教育毛入学率[[ed_higher_rate|61.5%]]，比上年提高1.2个百分点。普通高校及成人高校168所，研究生培养机构32个；招收研究生[[ed_postgrad|6.8万人]]，增长[[ed_postgrad_r|5.4%]]，在学研究生20.2万人，毕业研究生5.4万人。普通本专科招生62.4万人，在校生[[ed_undergrad|215.6万人]]，增长[[ed_undergrad_r|2.8%]]，毕业生54.8万人。',
    ],
    labels: {
      ed_higher_rate: '高等教育毛入学率',
      ed_decline_subject: '招生同比下降的学校类型',
      ed_students: '各级各类学校在校生总数',
      ed_primary_schools: '普通小学校数',
      ed_primary_students: '普通小学在校生数',
      ed_primary_students_r: '普通小学在校生增速',
      ed_junior_students: '初中在校生数',
      ed_junior_students_r: '初中在校生增速',
      ed_high_enrol: '普通高中招生数',
      ed_high_enrol_r: '普通高中招生增速',
      ed_postgrad: '研究生招生数',
      ed_postgrad_r: '研究生招生增速',
      ed_undergrad: '普通本专科在校生数',
      ed_undergrad_r: '普通本专科在校生增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年该省普通本专科在校生有多少万人？', keys: ['ed_undergrad'], reason: '第三段普通本专科在校生为215.6万人。' },
      { skill: '找率', prompt: '2023年该省高等教育毛入学率是多少？', keys: ['ed_higher_rate'], reason: '第三段首句给出高等教育毛入学率61.5%。' },
      { skill: '找主体', prompt: '2023年高中阶段教育中，招生人数同比下降的是哪一类学校？', keys: ['ed_decline_subject'], reason: '第二段普通高中招生增长，中等职业教育招生下降。' },
      { skill: '辨招生与在校生', prompt: '2023年该省研究生招生人数是多少？', keys: ['ed_postgrad'], reason: '第三段6.8万人是招生数，20.2万人是在学人数。' },
      { skill: '成对找数', prompt: '2023年普通高中招生人数及其同比增速分别是多少？', keys: ['ed_high_enrol', 'ed_high_enrol_r'], reason: '第二段普通高中招生数据后紧跟对应增速。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年普通小学在校生占各级各类学校在校生的比重约为多少？', keys: ['ed_primary_students', 'ed_students'], reason: '需找普通小学在校生与全口径在校生。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该省普通高中招生人数约为多少万人？', keys: ['ed_high_enrol', 'ed_high_enrol_r'], reason: '需找普通高中招生现期量和增速。' },
      { title: '平均数', formula: '校均在校生 = 在校生数 ÷ 学校数', prompt: '2023年该省平均每所普通小学有多少名在校生？', keys: ['ed_primary_students', 'ed_primary_schools'], reason: '需找普通小学在校生数与学校数，注意万人和所的换算。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年该省研究生招生人数同比增加约多少万人？', keys: ['ed_postgrad', 'ed_postgrad_r'], reason: '需找研究生招生现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年普通小学和初中在校生人数，哪一项同比增量更大？', keys: ['ed_primary_students', 'ed_primary_students_r', 'ed_junior_students', 'ed_junior_students_r'], reason: '小学、初中两组在校生现期量与增速都要定位。' },
    ],
  },
  {
    id: 'tourism',
    sums: [{ total: 'to_visitors', parts: ['to_domestic', 'to_inbound'] }],
    theme: '文化旅游',
    paragraphs: [
      '[[to_year|2023年]]，某省接待国内外游客[[to_visitors|48500万人次]]，比上年增长[[to_visitors_r|18.5%]]。其中，国内游客[[to_domestic|48120万人次]]，增长[[to_domestic_r|18.2%]]；入境过夜游客[[to_inbound|380万人次]]，增长[[to_inbound_r|72.4%]]。旅游总收入5620.8亿元，增长21.6%；其中国内旅游收入[[to_domestic_revenue|5498.5亿元]]，增长[[to_domestic_revenue_r|21.2%]]，国际旅游外汇收入[[to_foreign_revenue|17.2亿美元]]，增长65.8%。',
      'A级旅游景区接待游客[[to_scenic|26500万人次]]，增长[[to_scenic_r|15.4%]]，实现门票及综合收入218.4亿元，增长16.2%。其中，5A级旅游景区接待游客[[to_5a|9800万人次]]，占A级景区接待总量的37.0%。[[to_end|年末]]拥有星级饭店[[to_hotels|420家]]，客房平均出租率[[to_occupancy|64.2%]]，比上年提高[[to_occupancy_add|7.5个百分点]]；星级饭店营业收入186.5亿元，增长14.8%。',
      '年末共有公共图书馆142个、文化馆124个、博物馆185个。博物馆全年举办陈列展览[[to_exhibitions|1620个]]，接待观众[[to_museum_visitors|5260万人次]]，增长28.6%；公共图书馆总流通3450万人次，增长12.1%。各类艺术表演团体组织演出[[to_performances|4.8万场]]，国内观众[[to_audience|2180万人次]]。',
    ],
    labels: {
      to_museum_visitors: '博物馆接待观众人次',
      to_end: '星级饭店统计时点',
      to_foreign_revenue: '国际旅游外汇收入',
      to_5a: '5A级景区接待游客人次',
      to_scenic: 'A级景区接待游客总人次',
      to_exhibitions: '博物馆陈列展览数量',
      to_visitors: '游客总人次',
      to_visitors_r: '游客总人次增速',
      to_domestic: '国内游客人次',
      to_domestic_r: '国内游客人次增速',
      to_inbound: '入境过夜游客人次',
      to_inbound_r: '入境过夜游客人次增速',
      to_domestic_revenue: '国内旅游收入',
      to_domestic_revenue_r: '国内旅游收入增速',
    },
    basic: [
      { skill: '找数', prompt: '2023年该省博物馆接待观众多少万人次？', keys: ['to_museum_visitors'], reason: '第三段博物馆接待观众为5260万人次。' },
      { skill: '找率', prompt: '2023年该省入境过夜游客人次同比增长多少？', keys: ['to_inbound_r'], reason: '第一段入境过夜游客对应增速为72.4%。' },
      { skill: '找时间', prompt: '材料中“拥有星级饭店420家”对应什么时间口径？', keys: ['to_end'], reason: '星级饭店数量是年末时点数据。' },
      { skill: '辨币种', prompt: '2023年该省国际旅游外汇收入是多少？', keys: ['to_foreign_revenue'], reason: '第一段国际旅游外汇收入以亿美元计，不能取国内旅游收入。' },
      { skill: '辨总量与部分', prompt: '2023年5A级旅游景区接待游客多少万人次？', keys: ['to_5a'], reason: '第二段A级景区总量为26500万人次，其中5A级为9800万人次。' },
    ],
    advanced: [
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该省国内旅游收入约为多少亿元？', keys: ['to_domestic_revenue', 'to_domestic_revenue_r'], reason: '需找国内旅游收入现期值和增速。' },
      { title: '平均数', formula: '人均花费 = 旅游收入 ÷ 游客人次', prompt: '2023年该省国内游客人均旅游花费约为多少元？', keys: ['to_domestic_revenue', 'to_domestic'], reason: '需找国内旅游收入和国内游客人次，并换算亿元、万人次。' },
      { title: '部分量差', formula: '其他A级景区 = A级景区总量 - 5A级景区', prompt: '2023年除5A级外的其他A级景区接待游客多少万人次？', keys: ['to_scenic', 'to_5a'], reason: '需找A级景区接待总量和5A级景区接待量。' },
      { title: '平均数', formula: '场均观众 = 观众人次 ÷ 展览数', prompt: '2023年平均每个博物馆陈列展览接待观众约多少人次？', keys: ['to_museum_visitors', 'to_exhibitions'], reason: '需找博物馆观众总人次与陈列展览数量。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年国内游客和入境过夜游客人次，哪一项同比增量更大？', keys: ['to_domestic', 'to_domestic_r', 'to_inbound', 'to_inbound_r'], reason: '两个游客口径都要找齐现期量和增速。' },
    ],
  },
  {
    id: 'environment',
    theme: '生态环境',
    paragraphs: [
      '[[en_year|2023年]]，某省城市环境空气质量优良天数比率[[en_air|87.6%]]，比上年提高[[en_air_add|1.8个百分点]]。细颗粒物（PM2.5）年平均浓度[[en_pm25|28微克/立方米]]，下降[[en_pm25_r|6.7%]]；可吸入颗粒物（PM10）年平均浓度[[en_pm10|49微克/立方米]]，下降5.8%；二氧化硫和二氧化氮年平均浓度分别为7微克/立方米和22微克/立方米。',
      '地表水国考断面共[[en_sections|160个]]，水质优良（Ⅰ—Ⅲ类）断面比例[[en_good_water|90.0%]]，比上年提高2.5个百分点；劣Ⅴ类水质断面比例为0。县级及以上城市集中式饮用水水源地水质达标率[[en_drinking|100.0%]]。',
      '城市污水处理厂集中处理污水[[en_sewage|18.4亿立方米]]，比上年增长[[en_sewage_r|4.2%]]；城市污水处理率97.8%，提高0.6个百分点。一般工业固体废物产生量[[en_waste|4520万吨]]，增长[[en_waste_r|3.1%]]；综合利用量[[en_used|4110万吨]]，综合利用率90.9%。工业危险废物产生量[[en_danger|248万吨]]，利用处置率[[en_danger_rate|99.5%]]。',
    ],
    labels: {
      en_year: '生态环境指标统计年份',
      en_air: '空气质量优良天数比率',
      en_air_add: '空气优良天数比率提高幅度',
      en_pm25: 'PM2.5年平均浓度',
      en_pm25_r: 'PM2.5浓度降幅',
      en_sections: '地表水国考断面总数',
      en_good_water: '优良水质断面比例',
      en_sewage: '城市污水集中处理量',
      en_sewage_r: '城市污水集中处理量增速',
      en_waste: '一般工业固废产生量',
      en_waste_r: '一般工业固废产生量增速',
      en_used: '一般工业固废综合利用量',
      en_danger: '工业危险废物产生量',
      en_danger_rate: '工业危险废物利用处置率',
    },
    basic: [
      { skill: '找数', prompt: '2023年该省地表水国考断面共有多少个？', keys: ['en_sections'], reason: '第二段地表水国考断面总数为160个。' },
      { skill: '找率', prompt: '2023年该省工业危险废物利用处置率是多少？', keys: ['en_danger_rate'], reason: '第三段危废产生量后给出利用处置率99.5%。' },
      { skill: '找时间', prompt: '材料所列生态环境指标对应哪一统计年份？', keys: ['en_year'], reason: '首段开头给出统计年份为2023年。' },
      { skill: '辨污染物', prompt: '2023年该省PM2.5年平均浓度是多少？', keys: ['en_pm25'], reason: '第一段PM2.5为28微克/立方米，PM10为49微克/立方米。' },
      { skill: '辨一般固废与危废', prompt: '2023年该省工业危险废物产生量是多少？', keys: ['en_danger'], reason: '第三段一般工业固废为4520万吨，工业危险废物为248万吨。' },
    ],
    advanced: [
      { title: '基期百分数', formula: '基期比率 = 现期比率 - 提高百分点', prompt: '2022年该省城市空气质量优良天数比率是多少？', keys: ['en_air', 'en_air_add'], reason: '需找现期优良天数比率和提高的百分点。' },
      { title: '基期量（下降）', formula: '基期量 = 现期量 ÷（1-降幅）', prompt: '2022年该省PM2.5年平均浓度约为多少微克/立方米？', keys: ['en_pm25', 'en_pm25_r'], reason: '需找PM2.5现期浓度及同比降幅。' },
      { title: '部分量', formula: '部分量 = 总量 × 比重', prompt: '2023年该省水质优良的国考断面约有多少个？', keys: ['en_sections', 'en_good_water'], reason: '需找国考断面总数和优良断面比例。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该省城市污水集中处理量约为多少亿立方米？', keys: ['en_sewage', 'en_sewage_r'], reason: '需找污水处理量现期值和增速。' },
      { title: '剩余量', formula: '未利用量 = 产生量 - 综合利用量', prompt: '2023年该省未被综合利用的一般工业固体废物约为多少万吨？', keys: ['en_waste', 'en_used'], reason: '需找一般工业固废产生总量和综合利用量。' },
    ],
  },
  {
    id: 'charging',
    sums: [{ total: 'ch_total', parts: ['ch_public', 'ch_private'] }],
    theme: '新能源汽车充电设施',
    paragraphs: [
      '[[ch_end|截至2023年末]]，某省累计建成各类充电桩[[ch_total|86.0万个]]，比上年末增长[[ch_total_r|36.4%]]。其中，公共充电桩[[ch_public|31.0万个]]，增长[[ch_public_r|28.6%]]；个人专用充电桩[[ch_private|55.0万个]]，增长41.2%。公共充电桩中，直流快充桩18.6万个，交流慢充桩12.4万个；珠三角九市公共充电桩23.4万个，粤东粤西粤北地区7.6万个。',
      '2023年，全省新增充电桩[[ch_added|18.5万个]]，比上年增长[[ch_added_r|22.5%]]。其中，新增公共充电桩[[ch_public_added|7.9万个]]，增长18.0%；新增个人专用充电桩10.6万个，增长26.1%。全省高速公路服务区累计建成充电站912座、充电桩6384个，分别比上年末增长20.6%和31.5%。',
      '全年公共充电桩充电电量[[ch_power|96.4亿千瓦时]]，同比增长[[ch_power_r|42.8%]]。其中，乘用车充电电量61.7亿千瓦时，增长45.3%；商用车及其他公共车辆充电电量34.7亿千瓦时，增长38.6%。年末全省新能源汽车保有量[[ch_cars|420.0万辆]]，增长[[ch_cars_r|36.4%]]；公共车桩比为13.5∶1，比上年末缩小0.8。',
    ],
    labels: {
      ch_end: '充电桩存量统计时点', ch_total: '各类充电桩总量', ch_total_r: '各类充电桩总量增速',
      ch_public: '公共充电桩数量', ch_public_r: '公共充电桩数量增速', ch_added: '全年新增充电桩数量',
      ch_added_r: '新增充电桩增速', ch_public_added: '新增公共充电桩数量', ch_power: '公共充电桩充电电量',
      ch_power_r: '公共充电桩充电电量增速', ch_cars: '新能源汽车保有量', ch_cars_r: '新能源汽车保有量增速',
    },
    basic: [
      { skill: '找时间', prompt: '材料中“累计建成各类充电桩86.0万个”对应的统计时间是什么？', keys: ['ch_end'], reason: '累计建成数量对应截至2023年末这一时点。' },
      { skill: '找数', prompt: '截至2023年末，该省公共充电桩有多少万个？', keys: ['ch_public'], reason: '第一段按设施属性分列，公共充电桩为31.0万个。' },
      { skill: '辨存量与新增', prompt: '2023年该省新增公共充电桩多少万个？', keys: ['ch_public_added'], reason: '第二段7.9万个是全年新增量，第一段31.0万个是年末存量。' },
      { skill: '辨桩数与电量', prompt: '2023年该省公共充电桩充电电量是多少？', keys: ['ch_power'], reason: '第三段充电电量单位为亿千瓦时，不能取充电桩数量。' },
      { skill: '成对找数', prompt: '2023年末新能源汽车保有量及其同比增速分别是多少？', keys: ['ch_cars', 'ch_cars_r'], reason: '第三段末同时给出新能源汽车保有量和增速。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年末公共充电桩占各类充电桩的比重约为多少？', keys: ['ch_public', 'ch_total'], reason: '需找公共充电桩数量与各类充电桩总量。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年末该省各类充电桩约有多少万个？', keys: ['ch_total', 'ch_total_r'], reason: '需找充电桩年末现期量和比上年末增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年公共充电桩充电电量同比增加约多少亿千瓦时？', keys: ['ch_power', 'ch_power_r'], reason: '需找公共充电电量现期值和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年末公共充电桩占各类充电桩的比重约为多少？', keys: ['ch_public', 'ch_public_r', 'ch_total', 'ch_total_r'], reason: '需找公共桩与全部充电桩各自的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年各类充电桩存量和新能源汽车保有量，哪一项同比增量更大？', keys: ['ch_total', 'ch_total_r', 'ch_cars', 'ch_cars_r'], reason: '两类存量都要找齐现期量与增速，并注意单位。' },
    ],
  },
  {
    id: 'industry-ytd',
    theme: '规模以上工业运行',
    paragraphs: [
      '[[iy_period|2024年1—11月]]，某省规模以上工业增加值同比增长[[iy_value_r|5.8%]]，增速比1—10月加快0.2个百分点；[[iy_month|11月当月]]增长[[iy_month_r|6.6%]]。分三大门类看，采矿业增加值增长2.1%，制造业增长[[iy_manufacture_r|6.3%]]，电力、热力、燃气及水生产和供应业增长3.7%。高技术制造业增加值增长[[iy_hightech_r|9.2%]]，装备制造业增长7.6%，分别快于规上工业3.4个和1.8个百分点。',
      '1—11月，规模以上工业企业营业收入[[iy_revenue|120560.4亿元]]，同比增长[[iy_revenue_r|4.9%]]；实现利润总额[[iy_profit|7235.8亿元]]，增长[[iy_profit_r|7.2%]]。其中，制造业营业收入102486.3亿元，增长5.3%，利润总额[[iy_manu_profit|5980.6亿元]]，增长[[iy_manu_profit_r|7.9%]]；采矿业利润总额515.2亿元，下降6.4%；电力、热力、燃气及水生产和供应业利润总额740.0亿元，增长12.6%。',
      '主要产品产量中，新能源汽车[[iy_nev|186.4万辆]]，同比增长[[iy_nev_r|32.8%]]；集成电路412.6亿块，增长18.5%；工业机器人18.2万套，增长21.4%；锂离子电池126.8亿只，增长15.3%。1—11月规模以上工业企业每百元营业收入中的成本84.7元，同比减少0.3元；营业收入利润率[[iy_margin|6.00%]]，同比提高0.13个百分点。',
    ],
    labels: {
      iy_period: '累计统计期', iy_value_r: '1—11月规上工业增加值增速', iy_month: '当月统计期', iy_month_r: '11月规上工业增加值增速',
      iy_manufacture_r: '制造业增加值增速', iy_hightech_r: '高技术制造业增加值增速', iy_revenue: '规上工业营业收入',
      iy_revenue_r: '规上工业营业收入增速', iy_profit: '规上工业利润总额', iy_profit_r: '规上工业利润总额增速',
      iy_manu_profit: '制造业利润总额', iy_manu_profit_r: '制造业利润总额增速', iy_nev: '新能源汽车产量', iy_nev_r: '新能源汽车产量增速', iy_margin: '营业收入利润率',
    },
    basic: [
      { skill: '找时间', prompt: '材料中“规模以上工业增加值同比增长5.8%”对应的统计时期是什么？', keys: ['iy_period'], reason: '5.8%对应2024年1—11月累计增速。' },
      { skill: '辨累计与当月', prompt: '2024年11月当月规模以上工业增加值同比增长多少？', keys: ['iy_month_r'], reason: '第一段6.6%是11月当月增速，5.8%是1—11月累计增速。' },
      { skill: '找数', prompt: '2024年1—11月该省规上工业企业利润总额是多少？', keys: ['iy_profit'], reason: '第二段规上工业企业利润总额为7235.8亿元。' },
      { skill: '找率', prompt: '2024年1—11月该省高技术制造业增加值同比增长多少？', keys: ['iy_hightech_r'], reason: '第一段高技术制造业增加值对应增速为9.2%。' },
      { skill: '成对找数', prompt: '2024年1—11月新能源汽车产量及其增速分别是多少？', keys: ['iy_nev', 'iy_nev_r'], reason: '第三段同时给出新能源汽车产量与同比增速。' },
    ],
    advanced: [
      { title: '现期利润率', formula: '利润率 = 利润总额 ÷ 营业收入', prompt: '2024年1—11月规上工业企业营业收入利润率约为多少？', keys: ['iy_profit', 'iy_revenue'], reason: '需找规上工业利润总额和营业收入。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2023年1—11月规上工业企业营业收入约为多少亿元？', keys: ['iy_revenue', 'iy_revenue_r'], reason: '需找本期营业收入和同比增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2024年1—11月规上工业利润总额同比增加约多少亿元？', keys: ['iy_profit', 'iy_profit_r'], reason: '需找利润总额现期值和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2023年1—11月制造业利润占规上工业利润总额的比重约为多少？', keys: ['iy_manu_profit', 'iy_manu_profit_r', 'iy_profit', 'iy_profit_r'], reason: '需找制造业与规上工业利润各自的现期量和增速。' },
      { title: '平均数增长率', formula: '利润率增速 =（利润增速-收入增速）÷（1+收入增速）', prompt: '2024年1—11月规上工业企业营业收入利润率同比约增长多少？', keys: ['iy_profit_r', 'iy_revenue_r'], reason: '只需找利润总额增速与营业收入增速。' },
    ],
  },
  {
    id: 'retail-ytd',
    sums: [
      { total: 'ry_total', parts: ['ry_urban', 'ry_rural'] },
      { total: 'ry_total', parts: ['ry_goods', 'ry_catering'] },
    ],
    theme: '社会消费品零售',
    paragraphs: [
      '[[ry_period|2023年1—11月]]，社会消费品零售总额[[ry_total|427945亿元]]，同比增长[[ry_total_r|7.2%]]。其中，除汽车以外的消费品零售额384665亿元，增长7.9%。[[ry_month|11月份]]，社会消费品零售总额[[ry_month_total|42505亿元]]，同比增长[[ry_month_r|10.1%]]，环比增长0.06%；其中除汽车以外的消费品零售额38191亿元，增长9.6%。',
      '按经营单位所在地分，1—11月城镇消费品零售额[[ry_urban|371748亿元]]，增长[[ry_urban_r|7.1%]]；乡村消费品零售额[[ry_rural|56197亿元]]，增长[[ry_rural_r|7.9%]]。按消费类型分，商品零售[[ry_goods|381385亿元]]，增长[[ry_goods_r|5.9%]]；餐饮收入[[ry_catering|46560亿元]]，增长[[ry_catering_r|19.4%]]。',
      '1—11月，全国网上零售额[[ry_online|139571亿元]]，同比增长11.0%。其中，实物商品网上零售额[[ry_physical|117709亿元]]，增长[[ry_physical_r|8.3%]]，占社会消费品零售总额的[[ry_online_share|27.5%]]；在实物商品网上零售额中，吃类、穿类、用类商品分别增长12.0%、9.2%和7.5%。限额以上单位粮油食品类、服装鞋帽针纺织品类和汽车类商品零售额分别增长5.1%、11.5%和5.0%。',
    ],
    labels: {
      ry_period: '累计统计期', ry_total: '1—11月社会消费品零售总额', ry_total_r: '1—11月社零总额增速', ry_month: '当月统计期',
      ry_month_total: '11月社会消费品零售总额', ry_month_r: '11月社零总额增速', ry_urban: '城镇消费品零售额', ry_urban_r: '城镇零售额增速',
      ry_rural: '乡村消费品零售额', ry_rural_r: '乡村零售额增速', ry_goods: '商品零售额', ry_goods_r: '商品零售额增速',
      ry_catering: '餐饮收入', ry_catering_r: '餐饮收入增速', ry_online: '网上零售额', ry_physical: '实物商品网上零售额',
      ry_physical_r: '实物商品网上零售额增速', ry_online_share: '实物商品网上零售额占比',
    },
    basic: [
      { skill: '找时间', prompt: '材料中“社会消费品零售总额427945亿元”对应的统计时期是什么？', keys: ['ry_period'], reason: '该总额对应2023年1—11月累计口径。' },
      { skill: '辨累计与当月', prompt: '2023年11月当月社会消费品零售总额是多少？', keys: ['ry_month_total'], reason: '第一段42505亿元为11月当月值，427945亿元为1—11月累计值。' },
      { skill: '找率', prompt: '2023年1—11月乡村消费品零售额同比增长多少？', keys: ['ry_rural_r'], reason: '第二段乡村消费品零售额对应增速为7.9%。' },
      { skill: '辨商品与餐饮', prompt: '2023年1—11月餐饮收入是多少？', keys: ['ry_catering'], reason: '第二段按消费类型分列，餐饮收入为46560亿元。' },
      { skill: '辨网上与实物', prompt: '2023年1—11月实物商品网上零售额占社零总额的比重是多少？', keys: ['ry_online_share'], reason: '第三段直接给出实物商品网上零售额占比27.5%。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年1—11月乡村消费品零售额占社零总额的比重约为多少？', keys: ['ry_rural', 'ry_total'], reason: '需找乡村消费品零售额和社零总额。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年1—11月商品零售额约为多少亿元？', keys: ['ry_goods', 'ry_goods_r'], reason: '需找商品零售现期额和同比增速。' },
      { title: '增长量', formula: '增长量 = 现期量×增长率÷（1+增长率）', prompt: '2023年1—11月餐饮收入同比增加约多少亿元？', keys: ['ry_catering', 'ry_catering_r'], reason: '需找餐饮收入现期值和增速。' },
      { title: '基期比重', formula: '基期比重 = A/B ×（1+b）/（1+a）', prompt: '2022年1—11月乡村零售额占社零总额的比重约为多少？', keys: ['ry_rural', 'ry_rural_r', 'ry_total', 'ry_total_r'], reason: '需找乡村零售额与社零总额各自的现期量和增速。' },
      { title: '比较增长量', formula: '分别计算 A×r/（1+r）后比较', prompt: '2023年1—11月商品零售和餐饮收入，哪一项同比增量更大？', keys: ['ry_goods', 'ry_goods_r', 'ry_catering', 'ry_catering_r'], reason: '两个消费类型都要找齐现期量和增速。' },
    ],
  },
  {
    id: 'marine',
    sums: [{ total: 'ma_total', parts: ['ma_first', 'ma_second', 'ma_third'] }],
    theme: '海洋经济与港口运输',
    paragraphs: [
      '[[ma_year|2023年]]，某沿海省海洋生产总值[[ma_total|19500亿元]]，比上年增长[[ma_total_r|6.0%]]。其中，海洋第一产业增加值[[ma_first|780亿元]]，增长[[ma_first_r|4.0%]]；海洋第二产业增加值[[ma_second|7020亿元]]，增长[[ma_second_r|5.0%]]；海洋第三产业增加值[[ma_third|11700亿元]]，增长[[ma_third_r|6.8%]]，三次产业增加值占比分别为4.0%、36.0%和60.0%。',
      '主要海洋传统产业中，海洋水产品加工业增加值620亿元，增长3.0%；海洋船舶工业增加值480亿元，增长15.0%；海洋工程建筑业增加值850亿元，增长8.0%；海洋旅游业增加值[[ma_tourism|3750亿元]]，增长[[ma_tourism_r|12.0%]]。海洋新兴产业增加值[[ma_emerging|2400亿元]]，增长[[ma_emerging_r|10.0%]]，占海洋生产总值的比重比上年提高0.45个百分点。',
      '全年沿海港口完成货物吞吐量[[ma_cargo|20.0亿吨]]，同比增长[[ma_cargo_r|5.0%]]；完成集装箱吞吐量[[ma_container|7200万标准箱]]，增长[[ma_container_r|6.0%]]。其中，外贸货物吞吐量7.8亿吨，增长4.1%；内贸货物吞吐量12.2亿吨，增长5.6%。[[ma_end|年末]]全省拥有生产性泊位1860个，其中万吨级以上泊位615个，分别比上年末增加42个和18个。',
    ],
    labels: {
      ma_total: '海洋生产总值', ma_total_r: '海洋生产总值增速', ma_first: '海洋第一产业增加值', ma_first_r: '海洋第一产业增速',
      ma_second: '海洋第二产业增加值', ma_second_r: '海洋第二产业增速', ma_third: '海洋第三产业增加值', ma_third_r: '海洋第三产业增速',
      ma_tourism: '海洋旅游业增加值', ma_tourism_r: '海洋旅游业增加值增速', ma_emerging: '海洋新兴产业增加值',
      ma_emerging_r: '海洋新兴产业增加值增速', ma_cargo: '沿海港口货物吞吐量', ma_cargo_r: '货物吞吐量增速',
      ma_container: '集装箱吞吐量', ma_container_r: '集装箱吞吐量增速', ma_end: '泊位数量统计时点',
    },
    basic: [
      { skill: '找数', prompt: '2023年该省海洋第三产业增加值是多少？', keys: ['ma_third'], reason: '第一段三次产业中，海洋第三产业增加值为11700亿元。' },
      { skill: '找率', prompt: '2023年该省海洋新兴产业增加值同比增长多少？', keys: ['ma_emerging_r'], reason: '第二段海洋新兴产业增加值对应增速为10.0%。' },
      { skill: '辨行业口径', prompt: '2023年该省海洋旅游业增加值是多少？', keys: ['ma_tourism'], reason: '第二段海洋旅游业为传统产业细分项，增加值3750亿元。' },
      { skill: '找时间', prompt: '材料中“全省拥有生产性泊位1860个”对应什么时间口径？', keys: ['ma_end'], reason: '泊位数量是年末时点存量。' },
      { skill: '成对找数', prompt: '2023年沿海港口集装箱吞吐量及其增速分别是多少？', keys: ['ma_container', 'ma_container_r'], reason: '第三段同时给出集装箱吞吐量和同比增速。' },
    ],
    advanced: [
      { title: '现期比重', formula: '现期比重 = 部分量 ÷ 整体量', prompt: '2023年海洋旅游业增加值占海洋生产总值的比重约为多少？', keys: ['ma_tourism', 'ma_total'], reason: '需找海洋旅游业增加值和海洋生产总值。' },
      { title: '基期量', formula: '基期量 = 现期量 ÷（1+增长率）', prompt: '2022年该省海洋生产总值约为多少亿元？', keys: ['ma_total', 'ma_total_r'], reason: '需找海洋生产总值现期值和增速。' },
      { title: '混合增长率', formula: '先分别还原两部分基期量，再用总增量÷总基期量', prompt: '2023年海洋第一、第二产业增加值合计同比增长约多少？', keys: ['ma_first', 'ma_first_r', 'ma_second', 'ma_second_r'], reason: '第一、第二产业均需找现期量和各自增速。' },
      { title: '两期比重差', formula: '比重差 = A/B ×（a-b）/（1+a）', prompt: '2023年海洋第三产业占海洋生产总值的比重比上年变化多少个百分点？', keys: ['ma_third', 'ma_third_r', 'ma_total', 'ma_total_r'], reason: '需找第三产业和海洋生产总值各自的现期量、增速。' },
      { title: '平均数', formula: '平均每万标准箱货运量 = 货物吞吐量 ÷ 集装箱吞吐量', prompt: '2023年沿海港口平均每万标准箱对应多少万吨货物吞吐量？', keys: ['ma_cargo', 'ma_container'], reason: '需找货物吞吐量和集装箱吞吐量，并统一亿、万单位。' },
    ],
  },
];

PACKS.push(...ARCHIVED_READ_SPOT_PACKS);

const SUPPLEMENTS = {
  "rd": "分地区看，东部地区R&D经费投入[[rd_east|21280.6亿元]]，同比增长9.0%，占全国的63.9%；中部地区投入6185.7亿元，增长10.2%；西部地区投入4936.4亿元，增长6.7%；东北地区投入875.5亿元，增长2.4%。全年R&D人员全时当量[[rd_people|724.1万人年]]，比上年增长8.3%；每万名就业人员中R&D人员为82.4人年。全年授予发明专利92.1万件，其中境内发明专利授权81.3万件；年末每万人口高价值发明专利拥有量达到11.8件。",
  "medical-insurance": "全年职工医保参保人员享受待遇[[mi_treatments|25.3亿人次]]，比上年增加4.8亿人次。其中，普通门急诊待遇18.6亿人次，门诊慢特病待遇3.9亿人次，住院待遇2.8亿人次；次均住院费用12165元，比上年下降1.2%，政策范围内住院费用基金支付比例84.6%。年末职工医保定点医疗机构19.8万家，定点零售药店49.5万家，分别比上年末增加1.7万家和6.8万家。异地就医直接结算惠及[[mi_settlement_times|1.29亿人次]]，基金支付[[mi_settlement_pay|1854.7亿元]]。",
  "power": "全国6000千瓦及以上电厂发电设备利用时间中，水电3133小时，比上年减少285小时；核电7670小时，增加54小时；风电2225小时，增加7小时；太阳能发电1286小时，减少51小时。全年全社会用电量[[pw_consumption|9.22万亿千瓦时]]，同比增长6.7%。第一产业用电量1278亿千瓦时，增长11.5%；第二产业[[pw_second_power|6.07万亿千瓦时]]，增长6.5%；第三产业1.67万亿千瓦时，增长12.2%；城乡居民生活用电量1.35万亿千瓦时，增长0.9%。",
  "income": "按全国居民五等份收入分组，低收入组人均可支配收入[[in_low|9215元]]，中间偏下收入组20442元，中间收入组32195元，中间偏上收入组50220元，高收入组[[in_high|95058元]]。按消费类别分，人均食品烟酒消费支出7983元，增长6.7%；衣着支出1479元，增长8.4%；居住支出6095元，增长3.6%；生活用品及服务支出1526元，增长6.6%；交通通信支出3652元，增长14.3%；教育文化娱乐支出2904元，增长17.6%；医疗保健支出2460元，增长16.0%。",
  "trade": "跨境电商进出口[[tr_ecommerce|2.38万亿元]]，比上年增长15.6%；市场采购贸易出口9304亿元，增长9.3%。对区域全面经济伙伴关系协定其他成员国进出口12.60万亿元，占货物进出口总额的30.2%；对拉丁美洲、非洲进出口分别为3.44万亿元和1.98万亿元，分别增长6.8%和7.1%。民营企业出口[[tr_private_export|14.33万亿元]]，增长8.9%，占出口总额的60.3%；外商投资企业出口6.61万亿元，下降6.3%；国有企业出口2.83万亿元，增长0.2%。",
  "express": "全年邮政函件业务完成9.7亿件，包裹业务完成2470.2万件，订销报纸业务完成167.0亿份，订销杂志业务完成6.5亿份，汇兑业务完成349.0万笔。年末邮政普遍服务营业场所5.4万处，建制村直接通邮率保持100%；邮路总条数[[ex_routes|3.9万条]]，邮路总长度[[ex_route_length|1187.4万公里]]。快递服务营业网点23.4万处，快递专用货机190架，智能快件箱投递量达到167.3亿件。全年人均快递使用量[[ex_per_capita|93.7件]]，较上年增加14.9件。",
  "fiscal": "中央对该省转移支付收入[[fi_transfer|2685.4亿元]]，比上年增长8.2%，其中一般性转移支付2136.7亿元，专项转移支付[[fi_special_transfer|548.7亿元]]。全省一般公共预算支出中，节能环保支出236.8亿元，增长6.1%；交通运输支出512.4亿元，增长9.5%；住房保障支出418.7亿元，增长4.8%；科学技术支出376.2亿元，增长11.3%。全年发行地方政府债券3420.0亿元，其中新增债券1850.0亿元、再融资债券1570.0亿元；新增债券中专项债券1426.0亿元，占77.1%。",
  "transport": "城市公共交通方面，全年公共汽电车客运量18.6亿人次，比上年增长21.5%；轨道交通客运量12.4亿人次，增长38.7%；巡游出租汽车客运量5.8亿人次，增长16.2%。年末公共汽电车运营车辆4.26万辆，其中新能源车辆3.71万辆，占87.1%；轨道交通运营线路14条，运营里程612.5公里，车站386座。全市民用汽车保有量[[tp_cars|536.8万辆]]，比上年末增长5.6%，其中私人汽车458.2万辆，增长6.1%；新能源汽车保有量[[tp_nev_cars|128.4万辆]]，增长32.5%。",
  "agriculture": "水产品总产量[[ag_aquatic|842.6万吨]]，比上年增长3.2%。其中，海水产品486.1万吨，增长2.5%；淡水产品356.5万吨，增长4.1%；水产养殖产量[[ag_aquaculture|711.8万吨]]，占水产品总产量的84.5%。农田有效灌溉面积3186.4千公顷，比上年增加24.7千公顷；高标准农田累计建成2865.2千公顷。全年化肥施用量折纯量132.8万吨，下降2.6%；农药使用量4.7万吨，下降3.8%。农业机械作业方面，机耕、机播、机收面积分别为6842.5、5126.8和4984.3千公顷。",
  "education": "全省特殊教育学校162所，招收学生1.18万人，在校生7.46万人，专任教师0.59万人；义务教育阶段随班就读和送教上门学生3.82万人。民办学校共有4260所，在校生318.6万人，其中民办普通小学在校生126.4万人、民办初中78.5万人、民办普通高中42.7万人。全年地方财政教育支出[[ed_fiscal|1685.2亿元]]，比上年增长5.2%；普通小学、初中、高中生均一般公共预算教育经费分别为[[ed_primary_fund|1.42万元]]、2.06万元和[[ed_high_fund|2.18万元]]，分别增长3.1%、4.6%和5.0%。",
  "tourism": "旅行社组织国内旅游2680万人次，比上年增长46.7%，接待国内旅游3145万人次，增长39.2%；组织出境旅游186万人次，接待入境旅游92万人次。全省乡村旅游接待游客[[to_rural_visitors|1.82亿人次]]，实现旅游收入[[to_rural_revenue|685.4亿元]]，分别增长24.6%和28.1%。星级饭店客房总数8.6万间，全年平均房价438元/间夜，每间可供出租客房收入281元，分别增长12.4%和21.8%。年末拥有旅行社[[to_agencies|2860家]]，其中具有出境旅游业务资质的旅行社436家。",
  "environment": "全年化学需氧量排放量42.6万吨，比上年下降3.1%；氨氮排放量2.8万吨，下降4.5%；二氧化硫排放量18.2万吨，下降6.7%；氮氧化物排放量52.4万吨，下降5.9%。城市生活垃圾无害化处理量[[en_garbage|2865.4万吨]]，无害化处理率[[en_garbage_rate|99.8%]]；农村生活污水治理率达到61.5%，比上年提高8.3个百分点。年末共有自然保护地[[en_reserves|1362处]]，面积[[en_reserve_area|284.7万公顷]]；全年完成造林更新面积18.6万公顷，森林覆盖率达到60.3%，湿地保护率为52.8%；近岸海域优良水质面积比例为86.5%，比上年提高1.2个百分点。",
  "charging": "分地区看，珠三角九市年末公共充电桩23.4万个，占全省公共充电桩的75.5%；粤东、粤西、粤北地区分别为2.1万个、2.4万个和3.1万个。全省累计建成公共充电站[[ch_stations|3.26万座]]，其中城市公共充电站[[ch_city_stations|2.48万座]]、高速公路服务区充电站912座、公交及物流专用充电站6888座。全年新增换电站286座，年末换电站达到762座；充电运营企业共[[ch_operators|418家]]，其中接入省级监管平台的企业356家、公共充电桩28.7万个，平台接入率分别为85.2%和92.6%。",
  "industry-ytd": "分经济类型看，1—11月国有控股企业增加值同比增长4.2%，股份制企业增长6.4%，外商及港澳台商投资企业增长3.8%，私营企业增长5.7%。分企业规模看，大型企业增加值增长[[iy_large_r|5.2%]]，中型企业增长6.1%，小微型企业增长[[iy_small_r|6.5%]]。在统计的612种主要工业产品中，产量同比增长的有367种，增长面为60.0%。其中，服务机器人产量[[iy_service_robot|592.8万套]]，增长24.7%；太阳能电池产量53.6吉瓦，增长18.9%；民用无人机产量386.4万架，增长31.6%；智能手机产量1.42亿台，增长8.5%。",
  "retail-ytd": "限额以上单位商品零售中，粮油食品类零售额[[ry_food|17013亿元]]，同比增长5.8%；饮料类2747亿元，增长2.8%；烟酒类5003亿元，增长10.9%；服装鞋帽针纺织品类12170亿元，增长11.5%；化妆品类3779亿元，增长5.2%；金银珠宝类3042亿元，增长12.2%；家用电器和音像器材类7877亿元，增长0.6%；中西药品类5920亿元，增长5.1%；文化办公用品类3736亿元，下降6.1%；通讯器材类6554亿元，增长7.0%；汽车类[[ry_auto|42205亿元]]，增长6.2%。",
  "marine": "海洋科研教育管理服务业增加值4986亿元，比上年增长7.2%；海洋信息服务业增加值[[ma_info|1265亿元]]，增长12.8%；海洋药物和生物制品业增加值687亿元，增长11.5%；海水利用业增加值412亿元，增长8.3%。全年海水产品产量[[ma_seafood|486.1万吨]]，其中海水养殖产量[[ma_aquaculture|382.6万吨]]、海洋捕捞产量103.5万吨。年末海洋牧场示范区达到42个，深水网箱1.86万个。沿海港口开通外贸集装箱航线268条，比上年增加18条；国际航行船舶进出港8.42万艘次，增长9.6%。"
};

const SUPPLEMENT_QUESTIONS = {
  "rd": {
    "labels": {
      "rd_east": "东部地区R&D经费",
      "rd_people": "R&D人员全时当量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年东部地区R&D经费投入是多少？",
        "keys": [
          "rd_east"
        ],
        "reason": "补充段落按地区分列，东部地区R&D经费为21280.6亿元。"
      }
    ],
    "advanced": [
      {
        "title": "现期平均数",
        "formula": "人均R&D经费 = R&D经费 ÷ R&D人员全时当量",
        "prompt": "2023年平均每个R&D人员全时当量对应多少研发经费？",
        "keys": [
          "rd_total",
          "rd_people"
        ],
        "reason": "需找全国R&D经费和R&D人员全时当量。"
      }
    ]
  },
  "medical-insurance": {
    "labels": {
      "mi_treatments": "职工医保待遇人次",
      "mi_settlement_times": "异地就医直接结算人次",
      "mi_settlement_pay": "异地就医基金支付额"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年职工医保参保人员享受待遇多少亿人次？",
        "keys": [
          "mi_treatments"
        ],
        "reason": "补充段落首句给出享受待遇25.3亿人次。"
      }
    ],
    "advanced": [
      {
        "title": "现期平均数",
        "formula": "次均基金支付 = 基金支付额 ÷ 结算人次",
        "prompt": "2023年异地就医直接结算次均基金支付约为多少元？",
        "keys": [
          "mi_settlement_pay",
          "mi_settlement_times"
        ],
        "reason": "需找异地就医基金支付额和直接结算人次。"
      }
    ]
  },
  "power": {
    "labels": {
      "pw_consumption": "全社会用电量",
      "pw_second_power": "第二产业用电量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年全国全社会用电量是多少？",
        "keys": [
          "pw_consumption"
        ],
        "reason": "补充段落给出全社会用电量9.22万亿千瓦时。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年第二产业用电量占全社会用电量的比重约为多少？",
        "keys": [
          "pw_second_power",
          "pw_consumption"
        ],
        "reason": "需找第二产业用电量和全社会用电量。"
      }
    ]
  },
  "income": {
    "labels": {
      "in_low": "低收入组人均可支配收入",
      "in_high": "高收入组人均可支配收入"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年高收入组人均可支配收入是多少？",
        "keys": [
          "in_high"
        ],
        "reason": "补充段落五等份收入分组中，高收入组为95058元。"
      }
    ],
    "advanced": [
      {
        "title": "现期倍数",
        "formula": "倍数 = 高收入组收入 ÷ 低收入组收入",
        "prompt": "2023年高收入组人均可支配收入约是低收入组的多少倍？",
        "keys": [
          "in_high",
          "in_low"
        ],
        "reason": "需找高、低收入组各自的人均可支配收入。"
      }
    ]
  },
  "trade": {
    "labels": {
      "tr_ecommerce": "跨境电商进出口额",
      "tr_private_export": "民营企业出口额"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年我国跨境电商进出口额是多少？",
        "keys": [
          "tr_ecommerce"
        ],
        "reason": "补充段落首句给出跨境电商进出口2.38万亿元。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年民营企业出口额占货物出口额的比重约为多少？",
        "keys": [
          "tr_private_export",
          "tr_export"
        ],
        "reason": "需找民营企业出口额和货物出口总额。"
      }
    ]
  },
  "express": {
    "labels": {
      "ex_routes": "邮路总条数",
      "ex_route_length": "邮路总长度",
      "ex_per_capita": "人均快递使用量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年全国人均快递使用量是多少件？",
        "keys": [
          "ex_per_capita"
        ],
        "reason": "补充段落末句给出人均快递使用量93.7件。"
      }
    ],
    "advanced": [
      {
        "title": "现期平均数",
        "formula": "平均邮路长度 = 邮路总长度 ÷ 邮路条数",
        "prompt": "2023年平均每条邮路长度约为多少公里？",
        "keys": [
          "ex_route_length",
          "ex_routes"
        ],
        "reason": "需找邮路总长度和邮路总条数。"
      }
    ]
  },
  "fiscal": {
    "labels": {
      "fi_transfer": "中央转移支付收入",
      "fi_special_transfer": "专项转移支付"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年中央对该省转移支付收入是多少？",
        "keys": [
          "fi_transfer"
        ],
        "reason": "补充段落首句给出转移支付收入2685.4亿元。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年专项转移支付占中央对该省转移支付收入的比重约为多少？",
        "keys": [
          "fi_special_transfer",
          "fi_transfer"
        ],
        "reason": "需找专项转移支付和转移支付总收入。"
      }
    ]
  },
  "transport": {
    "labels": {
      "tp_cars": "民用汽车保有量",
      "tp_nev_cars": "新能源汽车保有量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年末该市新能源汽车保有量是多少？",
        "keys": [
          "tp_nev_cars"
        ],
        "reason": "补充段落末句给出新能源汽车保有量128.4万辆。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年末新能源汽车占民用汽车保有量的比重约为多少？",
        "keys": [
          "tp_nev_cars",
          "tp_cars"
        ],
        "reason": "需找新能源汽车和民用汽车保有量。"
      }
    ]
  },
  "agriculture": {
    "labels": {
      "ag_aquatic": "水产品总产量",
      "ag_aquaculture": "水产养殖产量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年该省水产品总产量是多少？",
        "keys": [
          "ag_aquatic"
        ],
        "reason": "补充段落首句给出水产品总产量842.6万吨。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年水产养殖产量占水产品总产量的比重约为多少？",
        "keys": [
          "ag_aquaculture",
          "ag_aquatic"
        ],
        "reason": "需找水产养殖产量和水产品总产量。"
      }
    ]
  },
  "education": {
    "labels": {
      "ed_fiscal": "地方财政教育支出",
      "ed_primary_fund": "普通小学生均教育经费",
      "ed_high_fund": "普通高中生均教育经费"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年该省地方财政教育支出是多少？",
        "keys": [
          "ed_fiscal"
        ],
        "reason": "补充段落给出地方财政教育支出1685.2亿元。"
      }
    ],
    "advanced": [
      {
        "title": "现期倍数",
        "formula": "倍数 = 高中生均经费 ÷ 小学生均经费",
        "prompt": "2023年普通高中生均教育经费约是普通小学的多少倍？",
        "keys": [
          "ed_high_fund",
          "ed_primary_fund"
        ],
        "reason": "需找普通高中和普通小学生均教育经费。"
      }
    ]
  },
  "tourism": {
    "labels": {
      "to_rural_visitors": "乡村旅游游客人次",
      "to_rural_revenue": "乡村旅游收入",
      "to_agencies": "旅行社数量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年末该省拥有旅行社多少家？",
        "keys": [
          "to_agencies"
        ],
        "reason": "补充段落末句给出旅行社2860家。"
      }
    ],
    "advanced": [
      {
        "title": "现期平均数",
        "formula": "人均花费 = 旅游收入 ÷ 游客人次",
        "prompt": "2023年该省乡村旅游人均花费约为多少元？",
        "keys": [
          "to_rural_revenue",
          "to_rural_visitors"
        ],
        "reason": "需找乡村旅游收入和接待游客人次。"
      }
    ]
  },
  "environment": {
    "labels": {
      "en_garbage": "生活垃圾无害化处理量",
      "en_garbage_rate": "生活垃圾无害化处理率",
      "en_reserves": "自然保护地数量",
      "en_reserve_area": "自然保护地面积"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年末该省共有自然保护地多少处？",
        "keys": [
          "en_reserves"
        ],
        "reason": "补充段落给出自然保护地1362处。"
      }
    ],
    "advanced": [
      {
        "title": "现期平均数",
        "formula": "平均面积 = 自然保护地面积 ÷ 自然保护地数量",
        "prompt": "2023年末平均每处自然保护地面积约为多少公顷？",
        "keys": [
          "en_reserve_area",
          "en_reserves"
        ],
        "reason": "需找自然保护地总面积和数量。"
      }
    ]
  },
  "charging": {
    "labels": {
      "ch_stations": "公共充电站数量",
      "ch_city_stations": "城市公共充电站数量",
      "ch_operators": "充电运营企业数量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年末该省充电运营企业共有多少家？",
        "keys": [
          "ch_operators"
        ],
        "reason": "补充段落给出充电运营企业418家。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年末城市公共充电站占公共充电站的比重约为多少？",
        "keys": [
          "ch_city_stations",
          "ch_stations"
        ],
        "reason": "需找城市公共充电站和公共充电站总数。"
      }
    ]
  },
  "industry-ytd": {
    "labels": {
      "iy_large_r": "大型企业增加值增速",
      "iy_small_r": "小微型企业增加值增速",
      "iy_service_robot": "服务机器人产量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2024年1—11月该省服务机器人产量是多少？",
        "keys": [
          "iy_service_robot"
        ],
        "reason": "补充段落给出服务机器人产量592.8万套。"
      }
    ],
    "advanced": [
      {
        "title": "增速百分点差",
        "formula": "百分点差 = 小微型企业增速 - 大型企业增速",
        "prompt": "2024年1—11月小微型企业增加值增速比大型企业快多少个百分点？",
        "keys": [
          "iy_small_r",
          "iy_large_r"
        ],
        "reason": "需找小微型企业和大型企业增加值增速。"
      }
    ]
  },
  "retail-ytd": {
    "labels": {
      "ry_food": "粮油食品类零售额",
      "ry_auto": "汽车类零售额"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年1—11月限额以上单位汽车类零售额是多少？",
        "keys": [
          "ry_auto"
        ],
        "reason": "补充段落汽车类零售额为42205亿元。"
      }
    ],
    "advanced": [
      {
        "title": "现期倍数",
        "formula": "倍数 = 汽车类零售额 ÷ 粮油食品类零售额",
        "prompt": "2023年1—11月汽车类零售额约是粮油食品类的多少倍？",
        "keys": [
          "ry_auto",
          "ry_food"
        ],
        "reason": "需找汽车类和粮油食品类零售额。"
      }
    ]
  },
  "marine": {
    "labels": {
      "ma_info": "海洋信息服务业增加值",
      "ma_seafood": "海水产品总产量",
      "ma_aquaculture": "海水养殖产量"
    },
    "basic": [
      {
        "skill": "找数",
        "prompt": "2023年该省海洋信息服务业增加值是多少？",
        "keys": [
          "ma_info"
        ],
        "reason": "补充段落给出海洋信息服务业增加值1265亿元。"
      }
    ],
    "advanced": [
      {
        "title": "现期比重",
        "formula": "现期比重 = 部分量 ÷ 整体量",
        "prompt": "2023年海水养殖产量占海水产品产量的比重约为多少？",
        "keys": [
          "ma_aquaculture",
          "ma_seafood"
        ],
        "reason": "需找海水养殖产量和海水产品总产量。"
      }
    ]
  }
};

const FIELD_RE = /\[\[([a-zA-Z0-9_]+)\|([^\]]+)]]/g;

const parsePack = (pack, wanted = new Set()) => {
  const values = {};
  const tokens = [];
  const paragraphs = [...pack.paragraphs, ...(SUPPLEMENTS[pack.id] ? [SUPPLEMENTS[pack.id]] : [])];
  paragraphs.forEach((paragraph, paragraphIndex) => {
    if (paragraphIndex) tokens.push({ text: '\n' });
    let cursor = 0;
    for (const match of paragraph.matchAll(FIELD_RE)) {
      if (match.index > cursor) tokens.push({ text: paragraph.slice(cursor, match.index) });
      values[match[1]] = match[2];
      tokens.push({ text: match[2], ...(wanted.has(match[1]) ? { mark: 'target' } : {}) });
      cursor = match.index + match[0].length;
    }
    if (cursor < paragraph.length) tokens.push({ text: paragraph.slice(cursor) });
  });
  return { tokens, values };
};

const questionsFor = (pack, kind) => [
  ...pack[kind],
  ...(SUPPLEMENT_QUESTIONS[pack.id]?.[kind] || []),
];

const allQuestions = (kind) =>
  PACKS.flatMap((pack) => questionsFor(pack, kind).map((question, index) => ({ pack, question, index })));

const shuffle = (items) => {
  const result = [...items];
  for (let i = result.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [result[i], result[j]] = [result[j], result[i]];
  }
  return result;
};

const decks = { basic: [], advanced: [] };
const draw = (kind) => {
  if (!decks[kind].length) decks[kind] = shuffle(allQuestions(kind));
  return decks[kind].pop();
};

const answerFor = (question, values) =>
  question.answer || question.keys.map((key) => values[key]).join('；');

const checklistFor = (pack, question, values) =>
  question.keys.map((key) => ({
    key,
    label: pack.labels[key] || SUPPLEMENT_QUESTIONS[pack.id]?.labels?.[key] || '题干所需信息',
    value: values[key],
  }));

const makeQuestion = (kind) => {
  const { pack, question, index } = draw(kind);
  const { tokens, values } = parsePack(pack, new Set(question.keys));
  const checklist = checklistFor(pack, question, values);
  const advanced = kind === 'advanced';
  return {
    kind: advanced ? 'findAdv' : 'findBasic',
    tag: advanced ? '进阶 · 结合题干找数' : '基础 · 真题式找数找词',
    hint: question.skill || question.title,
    themeId: pack.id,
    theme: pack.theme,
    prompt: advanced
      ? `请在材料中定位解答下列问题所需的全部已知信息：\n${question.prompt}`
      : question.prompt,
    formula: advanced ? { title: `公式提示 · ${question.title}`, text: question.formula } : undefined,
    checklist: advanced || question.keys.length > 1 ? checklist : undefined,
    material: tokens,
    answer: answerFor(question, values),
    reason: question.reason,
    concepts: [question.skill || question.title, pack.theme],
    questionId: `${pack.id}-${kind}-${index}`,
    displayAnswer: () => answerFor(question, values),
  };
};

export const generateFindBasic = () => makeQuestion('basic');
export const generateFindAdv = () => makeQuestion('advanced');
export const READ_SPOT_PACKS = PACKS;

// 开发期质量门禁也会调用，确保所有题目引用的字段都真实存在于材料。
export const validateReadSpotPacks = () => {
  const errors = [];
  for (const pack of PACKS) {
    const { tokens, values } = parsePack(pack);
    const raw = tokens.map((token) => token.text).join('');
    const paragraphs = raw.split(/\n+/).filter(Boolean);
    if (paragraphs.length < 4 || paragraphs.length > 5) errors.push(`${pack.id}: 段落数 ${paragraphs.length}`);
    if (raw.replace(/\s/g, '').length < 580) errors.push(`${pack.id}: 材料过短`);
    const numericCount = (raw.match(/\d+(?:\.\d+)?/g) || []).length;
    if (numericCount < 20) errors.push(`${pack.id}: 数字密度不足 ${numericCount}`);
    const toNumber = (key) => Number(String(values[key]).replace(/,/g, '').match(/-?\d+(?:\.\d+)?/)?.[0]);
    for (const sum of pack.sums || []) {
      const total = toNumber(sum.total);
      const parts = sum.parts.reduce((value, key) => value + toNumber(key), 0);
      if (!Number.isFinite(total) || !Number.isFinite(parts) || Math.abs(total - parts) > 0.11) {
        errors.push(`${pack.id}: 加总不一致 ${sum.total} != ${sum.parts.join(' + ')}`);
      }
    }
    for (const kind of ['basic', 'advanced']) {
      for (const question of questionsFor(pack, kind)) {
        for (const key of question.keys) {
          if (!values[key]) errors.push(`${pack.id}/${kind}: 缺少字段 ${key}`);
          if (!pack.labels[key] && !SUPPLEMENT_QUESTIONS[pack.id]?.labels?.[key]) errors.push(`${pack.id}/${kind}: 缺少标签 ${key}`);
        }
      }
    }
  }
  return errors;
};
