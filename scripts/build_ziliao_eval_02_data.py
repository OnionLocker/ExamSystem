import json
import subprocess
from pathlib import Path

BATCH_ID = "20260920_hermes_ziliao_eval_02"
BATCH_DIR = Path("/home/ubuntu/ExamSystem/data/manual-ziliao/2026-09-20/20260920_hermes_ziliao_eval_02")
SOURCE = "广东省考行测-资料分析-20260920"

m1_content = """2025年，G省新能源与新型储能产业实现营业收入8856.4亿元，同比增长18.2%；实现工业总产值9120.8亿元，同比增长19.5%。全省新型储能装机规模达到420.5万千瓦，同比增长68.2%，较2023年末增加275.3万千瓦。
按细分领域看，2025年，全省锂电池产业营业收入5420.8亿元，同比增长15.6%；氢能产业营业收入315.6亿元，同比增长32.4%；储能系统集成及配套产业营业收入2240.0亿元，同比增长24.5%；太阳能光伏及其他领域营业收入880.0亿元，同比增长12.8%。
2025年，全省新型储能产业研发经费投入354.2亿元，同比增长22.5%；研发投入强度达到4.00%。全省拥有规模以上新型储能企业1160家，全年实现利润总额696.0亿元，同比增长16.0%。
2025年，珠三角地区新型储能产业营业收入占全省比重为82.5%，比上年提高1.5个百分点；粤东、粤西、粤北地区合计占比为17.5%。全省新型储能电站平均利用小时数为1350小时，较上年增加120小时。"""

m2_content = """2025年，H省海洋生产总值达到19580.4亿元，同比增长7.8%，占全省地区生产总值的比重为14.2%，对全省经济增长的贡献率达到16.5%。全省主要海洋产业实现增加值5307.0亿元，同比增长10.5%（具体构成见附表）。
2025年，全省涉海规模以上工业企业达到2450家，实现营业收入8620.5亿元，同比增长9.6%；实现利润总额568.4亿元，同比增长11.2%。涉海工业企业每百元营业收入中的成本为82.4元，较上年减少0.8元。
海洋交通与港口方面，2025年全省沿海港口完成货物吞吐量20.4亿吨，同比增长5.8%，其中外贸货物吞吐量7.6亿吨，同比增长8.2%，内贸货物吞吐量12.8亿吨。全省港口集装箱吞吐量完成7280万标准箱，同比增长6.5%。
海洋科创方面，2025年全省涉海研究机构与高校研发经费内部支出185.6亿元，同比增长14.2%；拥有省级及以上海洋重点实验室48个，涉海有效发明专利达到2.85万件，较上年末增加0.42万件。"""

m3_content = """2025年，G省农林牧渔业总产值达到9280.6亿元，同比增长4.5%。农村居民人均可支配收入达到28912元，同比增长7.5%（历年收入见附图）。城乡居民人均可支配收入比为2.32:1，较上年缩小0.04。全省农村生活污水治理率达到72.4%，较上年提高6.8个百分点。
农业数字化方面，2025年全省农产品网络零售额实现945.8亿元，同比增长15.2%，占全省农产品销售总额的比重为22.5%，比上年提高1.8个百分点。全省累计建成数字农业示范基地280个，其中当年新建45个；物联网农业应用面积达到385万亩，同比增长28.3%。
优势特色产业方面，2025年全省岭南水果全产业链总产值2150.0亿元，同比增长8.2%；现代茶产业总产值420.5亿元，同比增长12.6%；优质蔬菜产值1680.2亿元，同比增长5.4%；水产养殖总产值1860.5亿元，同比增长6.8%。
农业经营主体方面，2025年末全省拥有国家级农业龙头企业112家，较上年增加14家；省级农业龙头企业1420家，较上年增加160家。全省农民专业合作社达到5.42万个，家庭农场达到18.6万家，辐射带动农户超480万户。"""

m4_content = """2025年，H省软件与信息技术服务业完成业务收入11540.0亿元，同比增长16.2%；实现利润总额1485.6亿元，同比增长12.8%。全省软件业务出口额达到265.4亿美元，同比增长8.5%，其中外包服务出口162.8亿美元，同比增长10.2%，其他软件出口102.6亿美元，同比增长5.9%。
按细分领域看，全省信息技术服务收入6280.0亿元，占全行业比重超过五成；软件产品收入3450.0亿元，信息安全和嵌入式系统软件分别实现收入385.0亿元和1425.0亿元（各领域增速见附表）。
2025年，全省软件业从业人员平均人数达到112.5万人，同比增长7.2%；人均创造业务收入102.58万元，较上年增加7.92万元。全省软件企业研发投入总额达到1186.0亿元，同比增长17.5%，研发经费占业务收入的比重达到10.28%。
产业集聚方面，2025年省会核心园区实现软件业务收入7850.0亿元，占全省比重达到68.02%；核心园区新认定专精特新软件企业185家，累计达到820家；拥有年收入超百亿元的软件骨干企业22家，较上年增加3家。"""

materials = [
    {
        "external_id": f"{BATCH_ID}-M01",
        "content": m1_content,
        "images": []
    },
    {
        "external_id": f"{BATCH_ID}-M02",
        "content": m2_content,
        "images": ["images/m-02-table.png"]
    },
    {
        "external_id": f"{BATCH_ID}-M03",
        "content": m3_content,
        "images": ["images/m-03-bars.png"]
    },
    {
        "external_id": f"{BATCH_ID}-M04",
        "content": m4_content,
        "images": ["images/m-04-table.png"]
    }
]

(BATCH_DIR / "materials.json").write_text(json.dumps(materials, ensure_ascii=False, indent=2), encoding="utf-8")

questions = [
    # M01: Q1-Q5, Answers: C, A, B, A, D
    {
        "external_id": f"{BATCH_ID}-Q01",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M01",
        "stem": "2024年（上年），珠三角地区新型储能产业营业收入约为（    ）亿元。",
        "options": [
            {"key": "A", "text": "5450亿元"},
            {"key": "B", "text": "5820亿元"},
            {"key": "C", "text": "6069亿元"},
            {"key": "D", "text": "6310亿元"}
        ],
        "answer": "C",
        "explanation": "由材料第一、四段可知，2025年全省新能源与新型储能产业营业收入为8856.4亿元，同比增长18.2%；珠三角地区营业收入占比为82.5%，比上年提高1.5个百分点。2024年全省总营业收入 = 8856.4 / (1 + 18.2%) ≈ 7492.72亿元；2024年珠三角地区比重 = 82.5% - 1.5% = 81.0%。2024年珠三角地区营业收入 = 7492.72 × 81.0% ≈ 6069.11亿元，与C项最接近。因此选择C选项。A项为按现期比重乘少除以基期；B项为直接用8856.4除以1.182后再减去部分增量估算偏差；D项为基期乘积计算偏差项。",
        "difficulty": 4,
        "tags": ["资料分析-基础知识-统计术语与常考概念", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q02",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M01",
        "stem": "2025年G省氢能产业营业收入同比增量约为（    ）。",
        "options": [
            {"key": "A", "text": "77.2亿元"},
            {"key": "B", "text": "64.5亿元"},
            {"key": "C", "text": "92.8亿元"},
            {"key": "D", "text": "102.3亿元"}
        ],
        "answer": "A",
        "explanation": "由材料第二段可知，2025年氢能产业营业收入为315.6亿元，同比增长32.4%。增长量 = 315.6 × 32.4% / (1 + 32.4%) = 315.6 × 0.324 / 1.324 ≈ 77.23亿元，与A项最接近。因此选择A选项。B项误用24.5%增速；C项误直接用现期乘32.4%未除以(1+r)；D项多算基期增量。",
        "difficulty": 4,
        "tags": ["资料分析-ABRX类-增长量计算与现期推算", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q03",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M01",
        "stem": "2025年G省规模以上新型储能企业户均实现利润总额约为（    ）。",
        "options": [
            {"key": "A", "text": "4800万元"},
            {"key": "B", "text": "6000万元"},
            {"key": "C", "text": "7200万元"},
            {"key": "D", "text": "8500万元"}
        ],
        "answer": "B",
        "explanation": "由材料第三段可知，2025年规模以上新型储能企业1160家，全年实现利润总额696.0亿元。户均利润 = 696.0亿元 / 1160家 = 0.60亿元/家 = 6000万元/家。因此选择B选项。A项为少除基数；C项为错取720家估算；D项为单位换算与估算偏差项。",
        "difficulty": 4,
        "tags": ["资料分析-平均类-一般平均值与年均增速/增量", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q04",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M01",
        "stem": "2024年（上年），G省锂电池产业营业收入占全省新能源与新型储能产业营业收入的比重约为（    ）。",
        "options": [
            {"key": "A", "text": "62.6%"},
            {"key": "B", "text": "61.2%"},
            {"key": "C", "text": "58.4%"},
            {"key": "D", "text": "55.6%"}
        ],
        "answer": "A",
        "explanation": "由材料第一、二段可知，2025年锂电池产业营业收入A=5420.8亿元，增速a=15.6%；全省总营业收入B=8856.4亿元，增速b=18.2%。基期比重 = (A/B) × [(1+b)/(1+a)] = (5420.8 / 8856.4) × (1.182 / 1.156) ≈ 61.21% × 1.0225 ≈ 62.58%，与A项最接近。因此选择A选项。B项为2025年现期比重(61.2%)；C项误将(1+a)/(1+b)反向缩放；D项为基期乘积计算偏差项。",
        "difficulty": 4,
        "tags": ["资料分析-比重类-现期、基期与隔级比重", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q05",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M01",
        "stem": "根据资料，以下说法可以判断属实的是（    ）。",
        "options": [
            {"key": "A", "text": "2025年G省新型储能产业研发经费投入同比增量低于60亿元"},
            {"key": "B", "text": "2023年末G省新型储能装机规模超过160万千瓦"},
            {"key": "C", "text": "2025年G省太阳能光伏及其他领域营业收入占全省比重高于上年同期"},
            {"key": "D", "text": "2025年G省储能系统集成及配套产业营业收入占全省比重较上年提高"}
        ],
        "answer": "D",
        "explanation": "由材料第二段可知，储能系统集成及配套产业营业收入增速a=24.5%，高于全省总营业收入增速b=18.2%，两期比重比较中分子增速大于分母增速，比重上升，D项属实。A项，研发经费投入增量=354.2×22.5%/1.225≈65.05亿元>60亿元，错误；B项，2023年末装机规模=420.5-275.3=145.2万千瓦<160万千瓦，错误；C项，太阳能光伏增速12.8%<全省增速18.2%，比重应低于上年，错误。因此选择D选项。",
        "difficulty": 4,
        "tags": ["资料分析-比重类-比重趋势、比重差与比值差", "paper_style:gd"],
        "source": SOURCE
    },

    # M02: Q6-Q10, Answers: D, B, C, C, D
    {
        "external_id": f"{BATCH_ID}-Q06",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M02",
        "stem": "2024年（上年），H省海洋船舶及工程装备制造增加值约为（    ）。",
        "options": [
            {"key": "A", "text": "465.0亿元"},
            {"key": "B", "text": "488.2亿元"},
            {"key": "C", "text": "508.4亿元"},
            {"key": "D", "text": "528.6亿元"}
        ],
        "answer": "D",
        "explanation": "由附表可知，2025年海洋船舶及工程装备制造增加值为624.8亿元，同比增长18.2%。基期量 = 624.8 / (1 + 18.2%) = 624.8 / 1.182 ≈ 528.6亿元。因此选择D选项。A项为465.2亿元（误看成海洋油气及矿业）；B项为除以1.28估算；C项为基期估算偏差值。",
        "difficulty": 4,
        "tags": ["资料分析-ABRX类-基期量计算与比较", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q07",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M02",
        "stem": "2025年H省沿海港口完成内贸货物吞吐量同比增速约为（    ）。",
        "options": [
            {"key": "A", "text": "3.2%"},
            {"key": "B", "text": "4.4%"},
            {"key": "C", "text": "5.8%"},
            {"key": "D", "text": "6.9%"}
        ],
        "answer": "B",
        "explanation": "由材料第三段可知，2025年沿海港口货物吞吐量20.4亿吨，同比增长5.8%；其中外贸货物吞吐量7.6亿吨，同比增长8.2%；内贸货物吞吐量12.8亿吨。全部港口货物基期量 = 20.4 / (1 + 5.8%) ≈ 19.282亿吨；外贸货物基期量 = 7.6 / (1 + 8.2%) ≈ 7.024亿吨。内贸货物基期量 = 19.282 - 7.024 = 12.258亿吨。内贸货物同比增速 = (12.8 - 12.258) / 12.258 ≈ 0.542 / 12.258 ≈ 4.42%，与B项最接近。十字交叉法验证：外贸增速8.2%、总体增速5.8%、内贸增速必低于5.8%，排除C、D；结合内外贸基期权数比例约7:12.3，(8.2%-5.8%)/(5.8%-r)=12.258/7.024≈1.745，解得5.8%-r≈1.38%，r≈4.42%。因此选择B选项。",
        "difficulty": 4,
        "tags": ["资料分析-盐水类-十字交叉法与混合增长率", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q08",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M02",
        "stem": "2024年H省港口集装箱吞吐量约为多少万标准箱？",
        "options": [
            {"key": "A", "text": "6420万标准箱"},
            {"key": "B", "text": "6650万标准箱"},
            {"key": "C", "text": "6836万标准箱"},
            {"key": "D", "text": "7015万标准箱"}
        ],
        "answer": "C",
        "explanation": "由材料第三段可知，2025年港口集装箱吞吐量为7280万标准箱，同比增长6.5%。基期量 = 7280 / (1 + 6.5%) = 7280 / 1.065 ≈ 6835.68万标准箱，与C项最接近。因此选择C选项。A项为除以1.134估算；B项为直接减去增量偏差项；D项为除以1.037估算项。",
        "difficulty": 4,
        "tags": ["资料分析-ABRX类-增长率计算模型", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q09",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M02",
        "stem": "2025年H省主要海洋产业的6个门类中，增加值同比增量最大的是（    ）。",
        "options": [
            {"key": "A", "text": "海洋渔业"},
            {"key": "B", "text": "海洋船舶及工程装备制造"},
            {"key": "C", "text": "海洋旅游业"},
            {"key": "D", "text": "海洋交通运输业"}
        ],
        "answer": "C",
        "explanation": "由附表可知各门类增量为：海洋渔业 1280.5×0.048/1.048≈58.6亿元；海洋船舶及装备制造 624.8×0.182/1.182≈96.2亿元；海洋旅游业 1568.0×0.125/1.125≈174.2亿元；海洋交通运输业 986.0×0.064/1.064≈59.3亿元。对比可知，海洋旅游业现期量最大(1568.0)且增速较高(12.5%)，增量174.2亿元位列第一。因此选择C选项。",
        "difficulty": 4,
        "tags": ["资料分析-比较类-双线法与增量比较", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q10",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M02",
        "stem": "能够从上述资料中推出的是（    ）。",
        "options": [
            {"key": "A", "text": "2024年H省海洋生产总值超过18500亿元"},
            {"key": "B", "text": "2025年H省外贸货物吞吐量占沿海港口货物吞吐量的比重低于上年同期"},
            {"key": "C", "text": "2025年H省主要海洋产业增加值中，海洋渔业增加值占比超过25.0%"},
            {"key": "D", "text": "2025年H省涉海规模以上工业企业户均营业收入超过3.5亿元"}
        ],
        "answer": "D",
        "explanation": "由材料第二段可知，2025年涉海规模以上工业企业2450家，实现营业收入8620.5亿元。户均营业收入 = 8620.5 / 2450 ≈ 3.5186亿元 > 3.5亿元，D项能够推出。A项，2024年海洋生产总值=19580.4/1.078≈18163.6亿元<18500亿元，错误；B项，外贸吞吐量增速8.2%>全部港口增速5.8%，比重高于上年同期，错误；C项，海洋渔业占比=1280.5/5307.0≈24.13%<25.0%，错误。因此选择D选项。",
        "difficulty": 4,
        "tags": ["资料分析-特殊考点-拉动增长、贡献率与容斥", "paper_style:gd"],
        "source": SOURCE
    },

    # M03: Q11-Q15, Answers: D, A, A, C, B
    {
        "external_id": f"{BATCH_ID}-Q11",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M03",
        "stem": "若2025年G省城镇居民人均可支配收入是农村居民人均可支配收入的2.32倍（即收入比为2.32:1），则2025年G省城镇居民人均可支配收入比农村居民约高出（    ）元。",
        "options": [
            {"key": "A", "text": "28912元"},
            {"key": "B", "text": "32450元"},
            {"key": "C", "text": "35680元"},
            {"key": "D", "text": "38164元"}
        ],
        "answer": "D",
        "explanation": "由材料第一段及附图可知，2025年农村居民人均可支配收入为28912元，城乡居民人均可支配收入比为2.32:1。城镇居民人均收入 = 28912 × 2.32，高出农村居民的金额 = 28912 × (2.32 - 1) = 28912 × 1.32 = 38163.84元 ≈ 38164元。因此选择D选项。A项直接取农村居民收入；B项用1.12倍估算偏差；C项少算部分乘积尾数偏差项。",
        "difficulty": 4,
        "tags": ["资料分析-基础知识-统计术语与常考概念", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q12",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M03",
        "stem": "2025年G省农产品网络零售额同比增量约为（    ）。",
        "options": [
            {"key": "A", "text": "124.8亿元"},
            {"key": "B", "text": "110.5亿元"},
            {"key": "C", "text": "138.2亿元"},
            {"key": "D", "text": "152.0亿元"}
        ],
        "answer": "A",
        "explanation": "由材料第二段可知，2025年农产品网络零售额945.8亿元，同比增长15.2%。增长量 = 945.8 × 15.2% / (1 + 15.2%) = 945.8 × 0.152 / 1.152 ≈ 124.79亿元，与A项最接近。因此选择A选项。B项用12.6%增速估算；C项未除以(1+r)直接用现期相乘(945.8×15.2%≈143.8)附近的偏差项；D项为基期增量错误计算项。",
        "difficulty": 4,
        "tags": ["资料分析-ABRX类-增长量计算与现期推算", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q13",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M03",
        "stem": "2021—2025年，G省农村居民人均可支配收入年均增加量约为（    ）。",
        "options": [
            {"key": "A", "text": "1652元"},
            {"key": "B", "text": "1321元"},
            {"key": "C", "text": "1845元"},
            {"key": "D", "text": "2202元"}
        ],
        "answer": "A",
        "explanation": "由附图可知，2021年农村居民人均可支配收入为22306元，2025年为28912元。2021—2025年经历4个年份间隔，年均增量 = (28912 - 22306) / 4 = 6606 / 4 = 1651.5元 ≈ 1652元。因此选择A选项。B项误除以5个年份(6606/5=1321.2)；C项为基期与现期取错年份估算项；D项误按3年计算。",
        "difficulty": 4,
        "tags": ["资料分析-平均类-一般平均值与年均增速/增量", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q14",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M03",
        "stem": "2024年（上年），G省农产品销售总额约为（    ）亿元。",
        "options": [
            {"key": "A", "text": "3450亿元"},
            {"key": "B", "text": "3720亿元"},
            {"key": "C", "text": "3966亿元"},
            {"key": "D", "text": "4204亿元"}
        ],
        "answer": "C",
        "explanation": "由材料第二段可知，2025年全省农产品网络零售额为945.8亿元，同比增长15.2%，占全省农产品销售总额的比重为22.5%，比上年提高1.8个百分点。2024年网络零售额 = 945.8 / (1 + 15.2%) ≈ 821.01亿元；2024年占比 = 22.5% - 1.8% = 20.7%。2024年全省农产品销售总额 = 821.01 / 20.7% ≈ 3966.22亿元，与C项最接近。因此选择C选项。A项为除以23.8%估算；B项为计算偏差项；D项为2025年现期销售总额(945.8/22.5%≈4203.6亿元)。",
        "difficulty": 4,
        "tags": ["资料分析-比重类-现期、基期与隔级比重", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q15",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M03",
        "stem": "根据资料，不能从上述资料中推出的是（    ）。",
        "options": [
            {"key": "A", "text": "2022—2025年各年，G省农村居民人均可支配收入同比增加量均超过1000元"},
            {"key": "B", "text": "2025年G省省级农业龙头企业数量同比增长超过15.0%"},
            {"key": "C", "text": "2024年G省农村生活污水治理率为65.6%"},
            {"key": "D", "text": "2025年G省岭南水果全产业链总产值占全省农林牧渔业总产值的比重超过20%"}
        ],
        "answer": "B",
        "explanation": "由材料第四段可知，2025年末省级龙头企业1420家，较上年增加160家，上年为1420-160=1260家，增速=160/1260≈12.7%<15.0%，故B项不能推出。A项，2022年增量23598-22306=1292元，2023年增量25142-23598=1544元，2024年增量26895-25142=1753元，2025年增量28912-26895=2017元，均超过1000元，能推出；C项，2024年污水治理率=72.4%-6.8%=65.6%，能推出；D项，岭南水果产值占比=2150.0/9280.6≈23.17%>20%，能推出。因此选择B选项。",
        "difficulty": 4,
        "tags": ["资料分析-比重类-比重趋势、比重差与比值差", "paper_style:gd"],
        "source": SOURCE
    },

    # M04: Q16-Q20, Answers: B, B, C, A, D
    {
        "external_id": f"{BATCH_ID}-Q16",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M04",
        "stem": "2024年（上年），H省软件产品实现业务收入约为（    ）。",
        "options": [
            {"key": "A", "text": "2850亿元"},
            {"key": "B", "text": "3013亿元"},
            {"key": "C", "text": "3220亿元"},
            {"key": "D", "text": "3380亿元"}
        ],
        "answer": "B",
        "explanation": "由附表可知，2025年软件产品实现业务收入3450.0亿元，同比增长14.5%。基期量 = 3450.0 / (1 + 14.5%) = 3450.0 / 1.145 ≈ 3013.10亿元 ≈ 3013亿元。因此选择B选项。A项为除以1.21估算；C项为除以1.071估算；D项直接减去部分增量估算偏差项。",
        "difficulty": 4,
        "tags": ["资料分析-ABRX类-基期量计算与比较", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q17",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M04",
        "stem": "2025年H省软件产品（14.5%）与嵌入式系统软件（10.0%）两类合计实现业务收入4875.0亿元，这两类业务收入的合并同比增速约为（    ）。",
        "options": [
            {"key": "A", "text": "11.5%"},
            {"key": "B", "text": "13.1%"},
            {"key": "C", "text": "14.0%"},
            {"key": "D", "text": "15.2%"}
        ],
        "answer": "B",
        "explanation": "由附表可知，软件产品现期量3450.0亿元、增速14.5%，基期量=3450/1.145≈3013.10亿元；嵌入式系统软件现期量1425.0亿元、增速10.0%，基期量=1425/1.10≈1295.45亿元。合并基期量=3013.10+1295.45=4308.55亿元，合并现期量=4875.0亿元。合并增速=(4875.0-4308.55)/4308.55=566.45/4308.55≈13.15%≈13.1%。结合十字交叉原理，增速必在10.0%与14.5%之间，且软件产品基期权重大于嵌入式，增速偏向14.5%，锁定13.1%。因此选择B选项。A项过于偏向10.0%；C项过于贴近14.5%；D项超过上限。",
        "difficulty": 4,
        "tags": ["资料分析-盐水类-十字交叉法与混合增长率", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q18",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M04",
        "stem": "2024年H省软件企业研发投入总额约为（    ）。",
        "options": [
            {"key": "A", "text": "925亿元"},
            {"key": "B", "text": "968亿元"},
            {"key": "C", "text": "1009亿元"},
            {"key": "D", "text": "1052亿元"}
        ],
        "answer": "C",
        "explanation": "由材料第三段可知，2025年软件企业研发投入总额为1186.0亿元，同比增长17.5%。基期量 = 1186.0 / (1 + 17.5%) = 1186.0 / 1.175 ≈ 1009.36亿元 ≈ 1009亿元。因此选择C选项。A项为除以1.282估算；B项为除以1.225估算；D项为除以1.127估算项。",
        "difficulty": 4,
        "tags": ["资料分析-ABRX类-增长率计算模型", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q19",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M04",
        "stem": "下列柱状图能够准确反映2025年H省软件产品、信息技术服务、信息安全、嵌入式系统软件四个细分领域业务收入同比增量大小关系的是（    ）。",
        "options": [
            {"key": "A", "text": "信息技术(967.0亿元) > 软件产品(436.9亿元) > 嵌入式(129.5亿元) > 信息安全(77.0亿元)", "images": ["images/q-19-opt-A.png"]},
            {"key": "B", "text": "信息技术(967.0亿元) > 嵌入式(436.9亿元) > 软件产品(129.5亿元) > 信息安全(77.0亿元)", "images": ["images/q-19-opt-B.png"]},
            {"key": "C", "text": "信息技术(967.0亿元) > 软件产品(436.9亿元) > 信息安全(77.0亿元) > 嵌入式(129.5亿元)", "images": ["images/q-19-opt-C.png"]},
            {"key": "D", "text": "软件产品(967.0亿元) > 信息技术(436.9亿元) > 嵌入式(129.5亿元) > 信息安全(77.0亿元)", "images": ["images/q-19-opt-D.png"]}
        ],
        "answer": "A",
        "explanation": "由附表可知各细分领域现期收入及增速，增量计算公式为 现期量×r/(1+r)：信息技术服务增量 = 6280.0×0.182/1.182 ≈ 967.0亿元；软件产品增量 = 3450.0×0.145/1.145 ≈ 436.9亿元；嵌入式系统软件增量 = 1425.0×0.10/1.10 ≈ 129.5亿元；信息安全增量 = 385.0×0.25/1.25 = 77.0亿元。增量从大到小排列依次为：信息技术服务(967.0) > 软件产品(436.9) > 嵌入式系统(129.5) > 信息安全(77.0)。选项A柱状图数值与排序完全匹配。B图倒置软件产品与嵌入式；C图倒置信息安全与嵌入式；D图倒置信息技术与软件产品。因此选择A选项。",
        "difficulty": 4,
        "tags": ["资料分析-比较类-双线法与增量比较", "paper_style:gd"],
        "source": SOURCE
    },
    {
        "external_id": f"{BATCH_ID}-Q20",
        "category": "资料分析",
        "question_type": "single",
        "material_id": f"{BATCH_ID}-M04",
        "stem": "根据资料，以下说法可以判断属实的是（    ）。",
        "options": [
            {"key": "A", "text": "2025年H省信息技术服务收入同比增量占全行业软件业务收入增量的比重低于50%"},
            {"key": "B", "text": "2024年H省软件业从业人员平均人数超过110万人"},
            {"key": "C", "text": "2025年H省外包服务出口额占软件业务出口总额的比重低于60.0%"},
            {"key": "D", "text": "2025年H省省会核心园区软件业务收入占全行业比重超过三分之二"}
        ],
        "answer": "D",
        "explanation": "由材料第四段可知，省会核心园区实现软件业务收入7850.0亿元，占全行业比重为68.02%，超过三分之二（约66.67%），D项属实。A项，信息技术服务增量约967.0亿元，全行业增量=11540×0.162/1.162≈1608.8亿元，占比=967.0/1608.8≈60.1%>50%，错误；B项，2024年从业人员=112.5/1.072≈104.9万人<110万人，错误；C项，外包服务出口占比=162.8/265.4≈61.34%>60.0%，错误。因此选择D选项。",
        "difficulty": 4,
        "tags": ["资料分析-特殊考点-拉动增长、贡献率与容斥", "paper_style:gd"],
        "source": SOURCE
    }
]

(BATCH_DIR / "questions.json").write_text(json.dumps(questions, ensure_ascii=False, indent=2), encoding="utf-8")

calculations = {
    "questions": [
        {"question_id": f"{BATCH_ID}-Q01", "correct": "(8856.4 / 1.182) * (82.5 - 1.5) / 100", "options": {"A": "5450", "B": "5820", "C": "6069", "D": "6310"}, "tolerance": 5.0},
        {"question_id": f"{BATCH_ID}-Q02", "correct": "315.6 * 0.324 / 1.324", "options": {"A": "77.2", "B": "64.5", "C": "92.8", "D": "102.3"}, "tolerance": 0.1},
        {"question_id": f"{BATCH_ID}-Q03", "correct": "696.0 / 1160 * 10000", "options": {"A": "4800", "B": "6000", "C": "7200", "D": "8500"}, "tolerance": 1.0},
        {"question_id": f"{BATCH_ID}-Q04", "correct": "(5420.8 / 8856.4) * (1 + 0.182) / (1 + 0.156) * 100", "options": {"A": "62.6", "B": "61.2", "C": "58.4", "D": "55.6"}, "tolerance": 0.1},
        {"question_id": f"{BATCH_ID}-Q05", "correct": "4", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "tolerance": 0.01},
        {"question_id": f"{BATCH_ID}-Q06", "correct": "624.8 / 1.182", "options": {"A": "465.0", "B": "488.2", "C": "508.4", "D": "528.6"}, "tolerance": 0.1},
        {"question_id": f"{BATCH_ID}-Q07", "correct": "(12.8 - (20.4 / 1.058 - 7.6 / 1.082)) / (20.4 / 1.058 - 7.6 / 1.082) * 100", "options": {"A": "3.2", "B": "4.4", "C": "5.8", "D": "6.9"}, "tolerance": 0.1},
        {"question_id": f"{BATCH_ID}-Q08", "correct": "7280 / 1.065", "options": {"A": "6420", "B": "6650", "C": "6836", "D": "7015"}, "tolerance": 1.0},
        {"question_id": f"{BATCH_ID}-Q09", "correct": "3", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "tolerance": 0.01},
        {"question_id": f"{BATCH_ID}-Q10", "correct": "4", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "tolerance": 0.01},
        {"question_id": f"{BATCH_ID}-Q11", "correct": "28912 * (2.32 - 1)", "options": {"A": "28912", "B": "32450", "C": "35680", "D": "38164"}, "tolerance": 1.0},
        {"question_id": f"{BATCH_ID}-Q12", "correct": "945.8 * 0.152 / 1.152", "options": {"A": "124.8", "B": "110.5", "C": "138.2", "D": "152.0"}, "tolerance": 0.1},
        {"question_id": f"{BATCH_ID}-Q13", "correct": "(28912 - 22306) / 4", "options": {"A": "1652", "B": "1321", "C": "1845", "D": "2202"}, "tolerance": 1.0},
        {"question_id": f"{BATCH_ID}-Q14", "correct": "(945.8 / 1.152) / ((22.5 - 1.8) / 100)", "options": {"A": "3450", "B": "3720", "C": "3966", "D": "4204"}, "tolerance": 2.0},
        {"question_id": f"{BATCH_ID}-Q15", "correct": "2", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "tolerance": 0.01},
        {"question_id": f"{BATCH_ID}-Q16", "correct": "3450.0 / 1.145", "options": {"A": "2850", "B": "3013", "C": "3220", "D": "3380"}, "tolerance": 1.0},
        {"question_id": f"{BATCH_ID}-Q17", "correct": "(4875.0 - (3450.0 / 1.145 + 1425.0 / 1.10)) / (3450.0 / 1.145 + 1425.0 / 1.10) * 100", "options": {"A": "11.5", "B": "13.1", "C": "14.0", "D": "15.2"}, "tolerance": 0.1},
        {"question_id": f"{BATCH_ID}-Q18", "correct": "1186.0 / 1.175", "options": {"A": "925", "B": "968", "C": "1009", "D": "1052"}, "tolerance": 1.0},
        {"question_id": f"{BATCH_ID}-Q19", "correct": "1", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "tolerance": 0.01},
        {"question_id": f"{BATCH_ID}-Q20", "correct": "4", "options": {"A": "1", "B": "2", "C": "3", "D": "4"}, "tolerance": 0.01}
    ]
}

(BATCH_DIR / "calculations.json").write_text(json.dumps(calculations, ensure_ascii=False, indent=2), encoding="utf-8")

tag_to_qids = {
    "资料分析-基础知识-统计术语与常考概念": [f"{BATCH_ID}-Q01", f"{BATCH_ID}-Q11"],
    "资料分析-ABRX类-增长量计算与现期推算": [f"{BATCH_ID}-Q02", f"{BATCH_ID}-Q12"],
    "资料分析-平均类-一般平均值与年均增速/增量": [f"{BATCH_ID}-Q03", f"{BATCH_ID}-Q13"],
    "资料分析-比重类-现期、基期与隔级比重": [f"{BATCH_ID}-Q04", f"{BATCH_ID}-Q14"],
    "资料分析-比重类-比重趋势、比重差与比值差": [f"{BATCH_ID}-Q05", f"{BATCH_ID}-Q15"],
    "资料分析-ABRX类-基期量计算与比较": [f"{BATCH_ID}-Q06", f"{BATCH_ID}-Q16"],
    "资料分析-盐水类-十字交叉法与混合增长率": [f"{BATCH_ID}-Q07", f"{BATCH_ID}-Q17"],
    "资料分析-ABRX类-增长率计算模型": [f"{BATCH_ID}-Q08", f"{BATCH_ID}-Q18"],
    "资料分析-比较类-双线法与增量比较": [f"{BATCH_ID}-Q09", f"{BATCH_ID}-Q19"],
    "资料分析-特殊考点-拉动增长、贡献率与容斥": [f"{BATCH_ID}-Q10", f"{BATCH_ID}-Q20"]
}

eval_contexts = []
for tag, qids in tag_to_qids.items():
    res = subprocess.run(["python3", "scripts/reference_style.py", "context", "--role", "evaluate", "--count", "1", "--tag", tag], capture_output=True, text=True, check=True)
    out = json.loads(res.stdout[res.stdout.find('{'):])
    eval_contexts.append({
        "context_id": out["context_id"],
        "reference_ids": out["reference_ids"],
        "question_ids": qids
    })

manifest = {
    "batch_id": BATCH_ID,
    "source": SOURCE,
    "region": "广东",
    "year": 2026,
    "license": "仅用于学习与题库内部评测",
    "created_at": "2026-09-20",
    "kind": "ai-generated",
    "difficulty_tier": "hard",
    "generation": {
        "style_marker": "GONGKAO-STYLE-v1",
        "batch_constraints": {
            "all_original": True,
            "question_count": 20,
            "answer_max_per_letter": 5,
            "answer_min_letters": 4,
            "difficulty_tier": "hard"
        },
        "evaluation_contexts": eval_contexts
    }
}

(BATCH_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Revised data files written successfully to {BATCH_DIR}.")
