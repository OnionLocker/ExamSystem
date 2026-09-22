from __future__ import annotations
import json, subprocess, time
from pathlib import Path
from ziliao_parallel_runner import call

ROOT = Path(__file__).resolve().parents[1]
BATCH = "20260920_hermes_ziliao_chart_stable_01"
OUT = ROOT / "data" / "chart-trial" / "2026-09-20" / BATCH
TAGS = "资料分析-ABRX类-基期量计算与比较；资料分析-ABRX类-增长量计算与现期推算；资料分析-ABRX类-增长率计算模型；资料分析-比重类-现期、基期与隔级比重；资料分析-比重类-比重趋势、比重差与比值差；资料分析-平均类-一般平均值与年均增速/增量；资料分析-比较类-双线法与增量比较"

def main():
    start=time.monotonic(); OUT.mkdir(parents=True, exist_ok=True); (OUT/'images').mkdir(exist_ok=True)
    frozen=call('''只生成一份广东省考资料分析柱状图材料数据，不出题。输出JSON {"content":"...","figure":{"kind":"bars","title":"不超过16字","unit":"亿元","categories":["甲","乙","丙","丁"],"series":[{"name":"收入","values":[120,240,360,480]}]}}。使用G省/H省/全国；正文必须完整包含全部图表分类和数值；标签不超过4字；数据足够支撑5题。只输出JSON。''',5000)
    f=frozen['figure']; img=OUT/'images/material-bars.png'
    subprocess.run(['python3','scripts/render_ziliao_figure.py','bars','--title',f['title'],'--ylabel',f['unit'],'--categories',','.join(f['categories']),'--series',f"{f['series'][0]['name']}:{','.join(map(str,f['series'][0]['values']))}",'--out',str(img)],cwd=ROOT,check=True)
    qs=[]; calcs=[]; mid=BATCH+'-M01'
    target_letters = ['A', 'C', 'B', 'D', 'A']
    for i in range(1,6):
        kind='综合判断' if i==5 else '常规计算'
        prompt=f'''只根据冻结材料出第{i}题（{kind}），不要修改任何材料或图表数字。材料：{frozen["content"]}\n图表：{json.dumps(f,ensure_ascii=False)}\n输出一个JSON对象，字段question和calculation。question必须含category=资料分析、question_type=single、stem、options=[{{"key":"A","text":"..."}},{{"key":"B","text":"..."}},{{"key":"C","text":"..."}},{{"key":"D","text":"..."}}]、answer、explanation、tags（必须从以下白名单复制：{TAGS}）、difficulty。第5题题干必须是“根据资料，以下说法可以判断属实的是”或“能够从上述资料中推出的是”。calculation必须含correct（只用数字和+-*/括号）、options字典A-D数值、tolerance；计算必须唯一匹配answer。解析最后必须明确选择answer对应项。只输出JSON。'''
        r=call(prompt,5000); q=r['question']; q.update(external_id=f'{BATCH}-Q{i}',material_id=mid)
        correct = str(q['answer']).upper(); opts = q['options'] if isinstance(q['options'], list) else [{'key': k, 'text': v} for k, v in q['options'].items()]
        by_key = {str(o['key']).upper(): o for o in opts}; desired = target_letters[i - 1]
        if correct not in by_key: raise ValueError(f'worker answer missing option: {correct}')
        ordered = [by_key[correct]] + [by_key[k] for k in 'ABCD' if k != correct]
        pos = 'ABCD'.index(desired); ordered[0], ordered[pos] = ordered[pos], ordered[0]
        q['options'] = [dict(o, key='ABCD'[j]) for j, o in enumerate(ordered)]; q['answer'] = desired; qs.append(q)
        c=r['calculation'];
        # Keep the calculation option values aligned with the reordered visible options.
        original_order = [by_key[k] for k in 'ABCD']
        original_values = dict(c.get('options') or {})
        c['options'] = {new_key: original_values.get(str(original_order[j].get('key'))) for j, new_key in enumerate('ABCD')}
        c['question_id']=q['external_id']; calcs.append(c)
    material={'external_id':mid,'content':frozen['content'],'images':['images/material-bars.png']}
    manifest={'batch_id':BATCH,'source':'广东省考行测-资料分析-20260920','region':'广东-模拟','year':2026,'license':'仅用于学习与题库内部评测','created_at':'2026-09-20','kind':'ai-generated','difficulty_tier':'hard','generation':{'style_marker':'GONGKAO-STYLE-v1','batch_constraints':{'all_original':True,'question_count':5,'answer_min_letters':2},'evaluation_contexts':[]}}
    for n,d in [('manifest.json',manifest),('materials.json',[material]),('questions.json',qs),('calculations.json',{'questions':calcs}),('frozen-data.json',frozen)]: (OUT/n).write_text(json.dumps(d,ensure_ascii=False,indent=2))
    gate=subprocess.run(['python3','scripts/generation_gate.py','issue',str(OUT)],cwd=ROOT,text=True,capture_output=True); print(gate.stdout or gate.stderr)
    if gate.returncode: return gate.returncode
    imp=subprocess.run(['node','scripts/import-batch.mjs',str(OUT)],cwd=ROOT,text=True,capture_output=True); print(imp.stdout or imp.stderr); print(json.dumps({'total_seconds':round(time.monotonic()-start,2)})); return imp.returncode
if __name__=='__main__': raise SystemExit(main())
