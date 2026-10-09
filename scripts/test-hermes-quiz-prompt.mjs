import assert from 'node:assert/strict';
import { buildQuizPrompt } from '../src/hermes/quizPrompt.js';

const projectRoot = '/home/ubuntu/ExamSystem';
for (const text of [
  '给我出6道最值问题，easy mid hard各两道',
  '工程问题出题，按现在的子知识点分配',
  '针对和定最值与构造练5道',
  '来三道政治理论题',
  '翻译推理和真假推理各出两题',
  '只练标题填入题，给我3道easy题。',
  '常识判断的科技理论与成就，给我3道easy单选题。',
]) {
  const prompt = buildQuizPrompt({ text, projectRoot });
  assert.equal(prompt.wantsQuiz, true, text);
  assert.match(prompt.quizNudge, /knowledge-content\.mjs catalog/);
  assert.match(prompt.quizNudge, /--plan-only/);
  assert.match(prompt.quizNudge, /catalog 返回的稳定 tag/);
  assert.match(prompt.quizNudge, /数量未指定难度时省略/);
  assert.match(prompt.quizNudge, /不要自行补成全mid/);
  assert.match(prompt.quizNudge, /言语同样未指定为auto/);
  assert.match(prompt.quizNudge, /难度只作命题倾向/);
  assert.match(prompt.quizNudge, /政治理论、常识判断也默认auto/);
  assert.match(prompt.quizNudge, /review-updates/);
  assert.match(prompt.quizNudge, /文字逻辑判断同样默认auto/);
  assert.doesNotMatch(prompt.quizNudge, /quiz_generator\.py|First tool call|四个独立考法/);
}
for (const text of ['先不要出题，讨论工程问题拆成三类', '只讨论怎么出题', '今天感觉累了']) {
  assert.equal(buildQuizPrompt({ text, projectRoot }).quizNudge, '', text);
}
assert.equal(buildQuizPrompt({ text: '直接在聊天这里出题', projectRoot }).quizNudge, '');
assert.match(buildQuizPrompt({ audio: true, projectRoot }).quizNudge, /若录音要求出题/);

const bar = buildQuizPrompt({ text: '我只练柱状图资料分析', projectRoot });
assert.equal(bar.wantsQuiz, true);
assert.match(bar.quizNudge, /--track gd --count 5 --materials 1 --difficulty mid --formats chart/);
assert.match(bar.quizNudge, /独立上下文/);

const table = buildQuizPrompt({ text: '只练表格资料分析，出5题', projectRoot });
assert.match(table.quizNudge, /--formats table/);
assert.match(table.quizNudge, /--track gd/);

for (const text of [
  '给我出一整套资料分析，均衡一点',
  '出一套广东省考资料分析',
  '来20道资料分析题',
  '资料分析出四篇题',
  '给我出广东省考资料分析题',
  '资料分析来一套经典计算加练',
]) {
  const { wantsQuiz, quizNudge } = buildQuizPrompt({ text, projectRoot });
  assert.equal(wantsQuiz, true, text);
  assert.match(quizNudge, /scripts\/ziliao_agent_paper\.py --output-dir \/home\/ubuntu\/ExamSystem\/data\/manual-ziliao-agent-paper/, text);
  assert.match(quizNudge, /--workers 2 --import/, text);
  assert.match(quizNudge, /资料分析整套必须走 agent-paper 高质量通道/, text);
  assert.match(quizNudge, /禁止用 parallel runner/, text);
  assert.doesNotMatch(quizNudge, /python3 \S*ziliao_parallel_runner\.py/, text);
}

const voice = buildQuizPrompt({ audio: true, projectRoot }).quizNudge;
assert.match(voice, /资料分析整套（20题、4篇、“一套\/整套”、广东省考\/默认难度，不论语音还是文字）必须走 agent-paper 高质量通道，禁止用 parallel runner 出整套/);
assert.match(voice, /scripts\/ziliao_agent_paper\.py/);
assert.doesNotMatch(voice, /资料分析共享材料和确定性图表走 ziliao_parallel_runner\.py/);

const defaultZiliao = buildQuizPrompt({ text: '资料分析出5题', projectRoot });
assert.match(defaultZiliao.quizNudge, /--track gd --count 5 --materials 1 --difficulty mid --formats chart/);
console.log('Hermes quiz prompt: ok');
