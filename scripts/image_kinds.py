"""公考带图题清单：谁程序画、谁仍走 Gemini。"""

from __future__ import annotations

PROGRAM = "program"
GEMINI = "gemini"
NONE = "none"

# 广东日练会碰到的带图来源。国考-only 也收进来，空间类广东近年会考。
IMAGE_KINDS = (
    # 资料分析：图在材料，不在题干
    ("资料分析", "table", "统计表", PROGRAM, "已有 render_ziliao_figure"),
    ("资料分析", "bars", "柱状图", PROGRAM, "已有 render_ziliao_figure"),
    ("资料分析", "pie", "饼图", PROGRAM, "已有 render_ziliao_figure"),
    # 判断推理 · 平面
    ("判断推理", "faces", "数量-封闭面", PROGRAM, "多边形剖分，面数可数"),
    ("判断推理", "arrows", "位置-平移旋转", PROGRAM, "箭头走格+转向"),
    ("判断推理", "xor", "样式-去同存异", PROGRAM, "线段集合对称差"),
    ("判断推理", "symmetry", "属性-对称分类", PROGRAM, "轴对称/中心对称"),
    ("判断推理", "open_close", "特殊-开闭分类", PROGRAM, "开口是否闭合"),
    # 判断推理 · 空间（广东会考；截面/拼合国考更多，但可练）
    ("判断推理", "cube_net", "空间-六面体展开", PROGRAM, "11 种展开+贴纸，相对面可算"),
    ("判断推理", "cube_section", "空间-立方体/堆叠截面", PROGRAM, "体素+切面，截面多边形可算"),
    ("判断推理", "cube_views", "空间-小方块三视图", PROGRAM, "体素正交投影"),
    ("判断推理", "cube_stack", "空间-方块计数", PROGRAM, "体素可见块可数"),
    # 科学推理：有固定几何内核的程序画，其余生图
    ("科学推理", "lever", "杠杆/滑轮", PROGRAM, "program_figure"),
    ("科学推理", "circuit", "串并联电路", PROGRAM, "program_figure"),
    ("科学推理", "tank", "容器液面/压强", PROGRAM, "program_figure"),
    ("科学推理", "motion_graph", "v-t / s-t 图像", PROGRAM, "program_figure"),
    ("科学推理", "contour", "等高线", PROGRAM, "program_figure"),
    ("科学推理", "food_web", "食物网/系谱", PROGRAM, "program_figure"),
    ("科学推理", "front", "锋面剖面", PROGRAM, "program_figure"),
    ("科学推理", "reflex", "反射弧", PROGRAM, "program_figure"),
    # 数量：广东卷面多为纯文字
    ("数量关系", "geometry", "平面/立体几何附图", PROGRAM, "日练暂少出，有图也按尺规画"),
)

GRAPHIC_KIND_BY_MOVE = {
    "封闭面递增": "faces",
    "箭头平移旋转": "arrows",
    "去同存异": "xor",
    "对称性分类": "symmetry",
    "开闭性分类": "open_close",
    "六面体展开还原": "cube_net",
    "立方体截面": "cube_section",
    "小方块三视图": "cube_views",
}


def draw_mode(kind: str) -> str:
    for _module, key, _label, mode, _note in IMAGE_KINDS:
        if key == kind:
            return mode
    return GEMINI
