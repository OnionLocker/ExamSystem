# grokbot → 申论收件箱

grokbot 负责到外面找申论材料和广东真题；系统负责核验原文、建要点表、批改。grokbot 不直接写题库，只往收件箱放 JSON 文件，然后运行一次：

```bash
python3 /home/ubuntu/ExamSystem/scripts/shenlun_quiz.py ingest
```

处理成功的文件移到 `data/shenlun-inbox/done/`，失败的移到 `data/shenlun-inbox/failed/`，命令输出里有逐个文件的错误原因。

## 1. 材料：`data/shenlun-inbox/sources/<id>.json`

一篇原文一个文件。系统会自己抓链接正文、按段存档、算哈希；出题时材料只能逐字摘自这些正文，所以必须给能直接打开的原文页，不要给搜索结果、摘要或转述。

```json
{
  "id": "nfnews-2026-10-baiqianwan-qingyuan",
  "title": "原文准确标题",
  "url": "https://原文地址",
  "published_at": "2026-10-12",
  "publisher": "南方日报",
  "tags": ["百千万工程", "乡村振兴"],
  "focus": ["可选：只保留含这些词的段落"]
}
```

- `id`：小写字母、数字、连字符，2–80 位，全库唯一。
- 链接只收 HTTPS。目前认的站点：各级政府网（gov.cn）、人民网、新华网、求是、光明网、央视网、央广网、中新网、中国经济网、中国日报、南方网 / 南方+、羊城晚报、广州日报、深圳新闻网、读特。别的站点抓取会被拒，需要先让用户加白名单。
- 最好的材料是**案例和报道**：某镇某村怎么做的、遇到什么问题、群众怎么说、干部怎么说、成效数字。纯政策条文只适合归纳概括，不适合对策题和综合分析。
- 主题优先：百千万工程、乡村振兴、基层治理与减负、民生实事、产业转移与县域经济、绿美广东、营商环境、数字政府、应急管理、文化传承。

## 2. 真题：`data/shenlun-inbox/papers/<id>.json`

```json
{
  "id": "gd-2025-xianji",
  "title": "2025年广东省考申论（县级卷）",
  "kind": "zhenti",
  "level": "县级",
  "year": 2025,
  "time_limit_min": 150,
  "source_note": "回忆版，来源：……",
  "materials": [
    {"title": "材料1", "paragraphs": ["第一段原文", "第二段原文"]}
  ],
  "questions": [
    {
      "qtype": "归纳概括",
      "prompt": "根据“给定资料1”，概括……（10分）要求：……不超过200字。",
      "score": 10,
      "words_max": 200,
      "material_ids": ["M1"],
      "reference_answers": [
        {"source": "粉笔", "text": "机构参考答案原文"},
        {"source": "华图", "text": "机构参考答案原文"}
      ]
    }
  ]
}
```

- `qtype` 只能是：归纳概括、综合分析、提出对策、贯彻执行、文章写作。
- `material_ids` 用 M1、M2……，按 `materials` 的顺序编号。
- `reference_answers` 尽量给 **2 家以上**机构答案：系统建要点表时只收几家都提到、并且材料里有原文依据的点；机构答案本身不当标准。
- 文章写作题写 `words_min` 和 `words_max`（如 1000、1200）。
- 材料段落要逐字照录试卷，不要改写或删节；回忆版要在 `source_note` 写明。
