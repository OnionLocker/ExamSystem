// ExamSystem ↔ Hermes 防腐层：集中处理上游 transcript 与流式事件的不稳定细节。

const METRICS_KEY = 'hermes.protocolMetrics.v1';
const EMBEDDED_IMAGE_RE = /data:image\/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+/g;
const SYSTEM_NOTICE_RE = /^\s*(?:\[CONTEXT COMPACTION\b|\[(?:ASYNC DELEGATION[^\]]*|SYSTEM NOTIFICATION[^\]]*|BACKGROUND TASK[^\]]*)\]|\[System:\s*You edited code in this turn\b|\[Coding\]\s*Before you run tests\/linters\b)/i;
const REVIEW_FILE_RE = /\/data\/(exam-reviews|practice-reviews)\/(\d+)-([^\n]+\.md)/;
const USER_MESSAGE_RE = /\[USER_MESSAGE\]\n?([\s\S]*?)\n?\[\/USER_MESSAGE\]/;
const USER_NOTE_RE = /\[USER_NOTE\]\n?([\s\S]*?)\n?\[\/USER_NOTE\]/;
const INTERNAL_NUDGE_RE = /\n?Keep all mastery\/profile bookkeeping completely silent and internal\.[\s\S]*$/;

const bump = (name) => {
  try {
    const current = JSON.parse(sessionStorage.getItem(METRICS_KEY) || '{}');
    current[name] = Number(current[name] || 0) + 1;
    sessionStorage.setItem(METRICS_KEY, JSON.stringify(current));
  } catch { /* 指标绝不能影响聊天 */ }
};

export const isSystemInjectedNotice = (text) => {
  const raw = String(text || '').trimStart();
  return (raw.charCodeAt(0) === 0 && raw.slice(1).startsWith('json:'))
    || SYSTEM_NOTICE_RE.test(raw);
};

const extractEmbeddedImages = (text) => text.match(EMBEDDED_IMAGE_RE) || [];
const stripEmbeddedImages = (text) =>
  text.replace(new RegExp(`\\n*${EMBEDDED_IMAGE_RE.source}`, 'g'), '').trim();

const visibleUserText = (text) => {
  const raw = String(text || '');
  const marked = raw.match(USER_MESSAGE_RE)?.[1] ?? raw.match(USER_NOTE_RE)?.[1];
  return marked != null ? marked.trim() : raw.replace(INTERNAL_NUDGE_RE, '').trim();
};

export const extractReview = (text) => {
  const raw = String(text || '');
  const marked = raw.match(USER_MESSAGE_RE)?.[1] ?? raw.match(USER_NOTE_RE)?.[1];
  const match = raw.match(REVIEW_FILE_RE);
  if (!match) return { content: visibleUserText(raw), review: null };
  const kind = match[1] === 'practice-reviews' ? 'practice' : 'exam';
  const name = match[3];
  const cleanTitle = name.replace(/^\d+-/, '').replace(/\.md$/i, '');
  const review = {
    id: Number(match[2]),
    kind,
    name,
    title: kind === 'practice' ? `AI 练题复盘：${cleanTitle}` : cleanTitle,
    label: kind === 'practice' ? `AI练题复盘 #${match[2]} · ${cleanTitle}` : name,
  };
  if (marked != null) return { content: marked.trim(), review };
  const cleaned = raw.replace(INTERNAL_NUDGE_RE, '').trim();
  const chunks = cleaned.split(/\n{2,}/);
  const last = (chunks[chunks.length - 1] || '').trim();
  const lastIsLead = REVIEW_FILE_RE.test(last) || /record\(\)/.test(last) || /^\d+\.\s/.test(last);
  return { content: lastIsLead ? '' : last, review };
};

const dedupeHistory = (messages) => {
  const seenAssistant = new Set();
  return messages.filter((message) => {
    if (message.role !== 'assistant') return true;
    const signature = String(message.content || '').replace(/\s+/g, ' ').trim();
    if (signature.length < 40) return true;
    if (seenAssistant.has(signature)) {
      bump('hydrate_duplicate_assistant');
      return false;
    }
    seenAssistant.add(signature);
    return true;
  });
};

export const normalizeHermesHistory = (
  raw,
  { nextId, parseAudioLen, isAudioLabel },
) => dedupeHistory(
  (raw || [])
    .filter((message) => message.role === 'user' || message.role === 'assistant')
    .filter((message) => {
      const keep = !isSystemInjectedNotice(message.text);
      if (!keep) bump('hydrate_internal_filtered');
      return keep;
    })
    .map((message) => {
      const rawText = String(message.text || '');
      const images = extractEmbeddedImages(rawText);
      const stripped = images.length > 0 ? stripEmbeddedImages(rawText) : rawText;
      const pulled = message.role === 'user'
        ? extractReview(stripped)
        : { content: stripped, review: null };
      const cleaned = String(pulled.content || '')
        .replace(/\[audio\]/gi, '')
        .replace(/下面附了我的口述录音[^\n]*/g, '')
        .trim();
      const audioSec = parseAudioLen(cleaned);
      const hadAudio = /\[audio\]/i.test(rawText) || isAudioLabel(cleaned);
      return {
        id: nextId(),
        role: message.role,
        content: cleaned,
        streaming: false,
        tools: [],
        thinking: '',
        images: pulled.review?.kind === 'practice' ? [] : images,
        audioSec,
        review: pulled.review,
        audio: null,
        hadAudio,
      };
    })
    .filter((message) => (
      message.content
      || (message.images?.length ?? 0) > 0
      || message.review
      || message.audioSec
      || message.hadAudio
    )),
);

export const appendAssistantDelta = (messages, text, nextId) => {
  const last = messages[messages.length - 1];
  if (last?.role === 'assistant' && last.streaming) {
    const copy = messages.slice(0, -1);
    copy.push({ ...last, content: last.content + text });
    return copy;
  }
  bump('delta_without_start');
  return [
    ...messages,
    {
      id: nextId(),
      role: 'assistant',
      content: text,
      streaming: true,
      tools: [],
      thinking: '',
    },
  ];
};

export const ensureStreamingAssistant = (messages, nextId) => {
  const last = messages[messages.length - 1];
  if (last?.role === 'assistant' && last.streaming) {
    bump('duplicate_message_start');
    return messages;
  }
  return [
    ...messages,
    {
      id: nextId(),
      role: 'assistant',
      content: '',
      streaming: true,
      tools: [],
      thinking: '',
    },
  ];
};

export const finishAssistantMessage = (messages, finalText, nextId) => {
  const last = messages[messages.length - 1];
  const final = String(finalText || '').trim();
  const sameFinal = (message, text = final) => (
    text
    && message?.role === 'assistant'
    && !message.streaming
    && String(message.content || '').trim() === text
  );
  if (!last || !last.streaming) {
    if (sameFinal(last)) {
      bump('duplicate_message_complete');
      return messages;
    }
    if (!finalText) return messages;
    bump('complete_without_start');
    return [
      ...messages,
      {
        id: nextId(),
        role: 'assistant',
        content: finalText,
        streaming: false,
        tools: [],
        thinking: '',
      },
    ];
  }

  const copy = messages.slice(0, -1);
  const tools = (last.tools || []).map((tool) => (
    tool.done ? tool : { ...tool, done: true }
  ));
  const content = last.content || finalText;
  const previous = copy[copy.length - 1];
  if (sameFinal(previous, String(content || '').trim())) {
    bump('duplicate_start_complete_pair');
    return copy;
  }
  copy.push({ ...last, content, streaming: false, tools });
  return copy;
};

export const eventText = (event) => event?.payload?.text || event?.payload?.rendered || '';
