// ExamSystem ↔ Hermes 防腐层：集中处理上游 transcript 与流式事件的不稳定细节。

const METRICS_KEY = 'hermes.protocolMetrics.v1';
const EMBEDDED_IMAGE_RE = /data:image\/[A-Za-z0-9.+-]+;base64,[A-Za-z0-9+/=]+/g;
const SYSTEM_NOTICE_RE = /^\s*(?:\[CONTEXT COMPACTION\b|\[(?:ASYNC DELEGATION[^\]]*|SYSTEM NOTIFICATION[^\]]*|BACKGROUND TASK[^\]]*)\]|\[System:\s*You edited code in this turn\b|\[Coding\]\s*Before you run tests\/linters\b)/i;
const REVIEW_FILE_RE = /\/data\/(exam-reviews|practice-reviews)\/(\d+)-([^\n]+\.md)/;
const UPLOAD_FILE_RE = /((?:\/[^\n]*)?\/data\/uploads\/(\d{4}\.\d{2}\.\d{2})\/([^\n/]+)\/([^\n]+))/;
// 后台脚本跑完，Hermes 运行时会把整段 stdout 当成一条用户消息塞回对话。
// 原文长得像一坨日志，直接上屏很难看，解析出来交给 BackgroundNotice 折叠显示。
// 动词按退出方式变：成功是 completed normally，失败是 exited，所以只认头，
// 退出码另外抓——抓不到就当未知，宁可显示得保守一点也别漏成一坨日志。
const BACKGROUND_NOTICE_RE = /^\s*\[(?:[A-Z]+:\s*)?Background process\b/i;
const EXIT_CODE_RE = /\(exit code\s*(-?\d+)\)/i;
const USER_MESSAGE_RE = /\[USER_MESSAGE\]\n?([\s\S]*?)\n?\[\/USER_MESSAGE\]/;
const USER_NOTE_RE = /\[USER_NOTE\]\n?([\s\S]*?)\n?\[\/USER_NOTE\]/;
const KNOWLEDGE_DEBT_RE = /\[KNOWLEDGE_DEBT\]\n?([\s\S]*?)\n?\[\/KNOWLEDGE_DEBT\]/;
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

export const parseBackgroundNotice = (text) => {
  const raw = String(text || '');
  if (!BACKGROUND_NOTICE_RE.test(raw)) return null;
  const code = raw.match(EXIT_CODE_RE)?.[1];
  const outputAt = raw.search(/Output:/i);
  const output = outputAt < 0 ? '' : raw.slice(outputAt + 7).replace(/\]\s*$/, '').trim();
  return {
    exitCode: code == null ? null : Number(code),
    command: raw.match(/Command:\s*([^\n]+)/)?.[1]?.trim() || '',
    output,
    // 脚本自己回的那句人话，比任何我这边拼的摘要都准。
    message: output.match(/"message"\s*:\s*"((?:[^"\\]|\\.)*)"/)?.[1]
      ?.replace(/\\(["\\/])/g, '$1')
      .replace(/\\[nrt]/g, ' ')
      .trim() || '',
  };
};

const extractEmbeddedImages = (text) => text.match(EMBEDDED_IMAGE_RE) || [];
const stripEmbeddedImages = (text) =>
  text.replace(new RegExp(`\\n*${EMBEDDED_IMAGE_RE.source}`, 'g'), '').trim();

const visibleUserText = (text) => {
  const raw = String(text || '');
  const marked = raw.match(USER_MESSAGE_RE)?.[1] ?? raw.match(USER_NOTE_RE)?.[1];
  return marked != null ? marked.trim() : raw.replace(INTERNAL_NUDGE_RE, '').trim();
};

export const debtReviewOf = (instruction) => {
  const title = instruction.match(/^考点:\s*(.+)$/m)?.[1]?.trim() || '知识债出题';
  return { id: `debt:${title}`, kind: 'debt', title, label: `知识债 · ${title}`, instruction };
};

export const extractReview = (text) => {
  const raw = String(text || '');
  const debt = raw.match(KNOWLEDGE_DEBT_RE);
  if (debt) return { content: visibleUserText(raw), review: debtReviewOf(debt[1]) };
  const marked = raw.match(USER_MESSAGE_RE)?.[1] ?? raw.match(USER_NOTE_RE)?.[1];
  const match = raw.match(REVIEW_FILE_RE);
  const upload = raw.match(UPLOAD_FILE_RE);
  let review = null;
  if (match) {
    const kind = match[1] === 'practice-reviews' ? 'practice' : 'exam';
    const name = match[3];
    const cleanTitle = name.replace(/^\d+-/, '').replace(/\.md$/i, '');
    const audit = kind === 'practice' && /复盘审核/.test(raw);
    review = {
      id: Number(match[2]),
      kind,
      name,
      title: kind === 'practice' ? `AI 练题复盘：${cleanTitle}` : cleanTitle,
      label: kind === 'practice'
        ? `${audit ? '复盘审核 · ' : ''}AI练题复盘 #${match[2]} · ${cleanTitle}`
        : name,
      audit,
    };
  } else if (upload) {
    const name = String(upload[4] || '').trim();
    const cleanTitle = name.replace(/\.pdf$/i, '');
    review = {
      id: `${upload[2]}/${upload[3]}/${name}`,
      kind: 'upload',
      name,
      path: String(upload[1] || '').trim(),
      title: cleanTitle,
      label: `资料上传 · ${upload[2]} · ${cleanTitle}`,
    };
  }
  if (!review) return { content: visibleUserText(raw), review: null };
  // 复盘附件只留芯片。用户附带的那句原话仍送给模型，但不上屏，
  // 否则复盘审核会把「感觉还是不会」这类对话画在题卡旁边。
  if (marked != null) return { content: '', review };
  const cleaned = raw.replace(INTERNAL_NUDGE_RE, '').trim();
  const chunks = cleaned.split(/\n{2,}/);
  const last = (chunks[chunks.length - 1] || '').trim();
  const lastIsLead = REVIEW_FILE_RE.test(last) || UPLOAD_FILE_RE.test(last) || /record\(\)/.test(last) || /^\d+\.\s/.test(last);
  return { content: lastIsLead ? '' : last, review };
};

// 复盘正文必须从「### 01 · 题型名」起笔。模型有时会先把任务说明和用户原话
// 复述出来，这段不能上屏，和练题复盘只展示题卡保持一致。
const REVIEW_HEADING_LINE_RE = /^###\s+\d+\s*[·．.]/m;
const REVIEW_LEAK_RE = /第一件工具必须是|The user wants me to do a review|Let's carefully check the instructions|回复的第一行必须是|The user's voice message/;

export const visibleAssistantReply = (content) => {
  const raw = String(content || '');
  const heading = REVIEW_HEADING_LINE_RE.exec(raw);
  if (heading) {
    if (heading.index > 0 && REVIEW_LEAK_RE.test(raw.slice(0, heading.index))) {
      return raw.slice(heading.index).trim();
    }
    return raw;
  }
  return REVIEW_LEAK_RE.test(raw) ? '' : raw;
};

const assistantSig = (message) => String(message?.content || '').replace(/\s+/g, ' ').trim();

const sameAssistantText = (left, right) => {
  const a = assistantSig(left);
  const b = assistantSig(right);
  if (!a || !b || a.length < 40 || b.length < 40) return false;
  return a === b || a.startsWith(b) || b.startsWith(a);
};

const dedupeHistory = (messages) => {
  const out = [];
  for (const message of messages) {
    const prev = out[out.length - 1];
    if (message.role === 'assistant' && prev?.role === 'assistant' && sameAssistantText(prev, message)) {
      bump('hydrate_duplicate_assistant');
      if (assistantSig(message).length > assistantSig(prev).length) out[out.length - 1] = message;
      continue;
    }
    if (message.role === 'assistant') {
      const signature = assistantSig(message);
      if (
        signature.length >= 40
        && out.some((item) => item.role === 'assistant' && assistantSig(item) === signature)
      ) {
        bump('hydrate_duplicate_assistant');
        continue;
      }
    }
    out.push(message);
  }
  return out;
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
      const notice = message.role === 'user' ? parseBackgroundNotice(rawText) : null;
      if (notice) {
        // 单独一个 role，这样「最后一条用户消息」的判定不会被它顶掉。
        return { id: nextId(), role: 'notice', content: '', notice, tools: [], thinking: '', sentAt: sentAtMs(message.timestamp) };
      }
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
        sentAt: sentAtMs(message.timestamp),
      };
    })
    .filter((message) => (
      message.content
      || (message.images?.length ?? 0) > 0
      || message.review
      || message.audioSec
      || message.hadAudio
      || message.notice
    )),
);

export const appendAssistantDelta = (messages, text, nextId) => {
  const last = messages[messages.length - 1];
  if (last?.role === 'assistant' && last.streaming) {
    const copy = messages.slice(0, -1);
    copy.push({ ...last, content: last.content + text });
    return copy;
  }
  if (last?.role === 'assistant' && !last.streaming) {
    bump('duplicate_delta_on_complete');
    return messages;
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
  if (last?.role === 'assistant') {
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

// 官方 TUI 同款：gateway WS 广播所有会话的流式事件，必须按 session_id 丢掉别人的。
export const eventMatchesSession = (event, liveId, storedId) => {
  const sid = event?.session_id;
  if (!sid) return true;
  const type = String(event?.type || '');
  if (type.startsWith('gateway.')) return true;
  return sid === liveId || sid === storedId;
};

export const resumeMatchesSession = (payload, liveId, storedId) => {
  const incoming = [
    payload?.session_id,
    payload?.session_key,
    payload?.resumed,
    payload?.stored_session_id,
  ].filter(Boolean);
  if (incoming.length === 0) return true;
  const mine = new Set([liveId, storedId].filter(Boolean));
  if (mine.size === 0) return true;
  return incoming.some((id) => mine.has(id));
};

export const coerceResumePayload = (result) => {
  if (Array.isArray(result)) return { messages: result, running: false };
  if (!result || typeof result !== 'object') return { messages: [], running: false };
  const messages = Array.isArray(result.messages) ? result.messages : [];
  return { ...result, messages };
};

const sentAtMs = (ts) => {
  const n = Number(ts);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return n < 1e12 ? Math.round(n * 1000) : Math.round(n);
};

const userKey = (message, parseAudioLen, isAudioLabel) => {
  const raw = String(message?.content || '').trim();
  const audio = Boolean(message?.hadAudio || message?.audio || isAudioLabel?.(raw));
  const body = audio
    ? `[audio]:${message.audioSec || parseAudioLen?.(raw) || 0}`
    : raw;
  return `${body}\0${message?.review?.id || ''}`;
};

// 把 session.resume / session.history 的 transcript 合并进当前气泡。
// 另一台设备后发的用户消息会出现在 resume.messages 或 inflight.user 里。
export const mergeResumedMessages = (prev, resume, {
  nextId, parseAudioLen, isAudioLabel, sameSession = true, storedId,
} = {}) => {
  if (!sameSession) prev = [];
  const hydrated = normalizeHermesHistory(resume?.messages, {
    nextId,
    parseAudioLen,
    isAudioLabel,
  });
  const lastHydratedUser = [...hydrated].reverse().find((message) => message.role === 'user');
  const inflightCandidate = String(resume?.inflight?.user || '').trim();
  const inflightRaw = isSystemInjectedNotice(inflightCandidate) || parseBackgroundNotice(inflightCandidate)
    ? ''
    : inflightCandidate;
  const inflightUser = inflightRaw ? extractReview(inflightRaw) : null;

  const resumeSessionIds = new Set([
    storedId,
    resume?.stored_session_id,
    resume?.session_key,
    resume?.resumed,
    resume?.session_id,
  ].filter(Boolean));
  const localBelongs = (message) => {
    const owned = message?.storedSessionId;
    if (!owned || resumeSessionIds.size === 0) return true;
    return resumeSessionIds.has(owned);
  };

  const lastLocalUser = [...prev].reverse().find((message) => message.role === 'user' && localBelongs(message));
  const keyOf = (message) => userKey(message, parseAudioLen, isAudioLabel);
  const hydratedUserKeys = new Set(
    hydrated.filter((message) => message.role === 'user').map(keyOf),
  );
  const localStillPending = Boolean(
    lastLocalUser
    && localBelongs(lastLocalUser)
    && !hydratedUserKeys.has(keyOf(lastLocalUser))
    && (!inflightUser || keyOf({
      content: inflightUser.content,
      review: inflightUser.review,
      hadAudio: lastLocalUser.hadAudio,
      audioSec: lastLocalUser.audioSec,
    }) === keyOf(lastLocalUser)),
  );
  const pendingContent = inflightUser?.content ?? (localStillPending ? lastLocalUser.content : '');
  const pendingReview = inflightUser?.review ?? (localStillPending ? lastLocalUser.review : null);
  const alreadyHydrated = pendingContent === lastHydratedUser?.content
    && pendingReview?.id === lastHydratedUser?.review?.id;

  // 只把同一条用户消息上的本地录音/图贴回去，禁止按下标串到别的会话。
  const unusedUsers = prev.filter((message) => message.role === 'user');
  const next = hydrated.map((message) => {
    if (message.role !== 'user') return message;
    const at = unusedUsers.findIndex((old) => keyOf(old) === keyOf(message));
    if (at < 0) return message;
    const old = unusedUsers.splice(at, 1)[0];
    return {
      ...message,
      id: old.id,
      images: message.images?.length ? message.images : old.images,
      audio: message.audio || old.audio,
      audioSec: message.audioSec ?? old.audioSec,
      hadAudio: message.hadAudio || old.hadAudio,
      sentAt: old.sentAt ?? message.sentAt,
      storedSessionId: old.storedSessionId || message.storedSessionId,
    };
  });
  if ((pendingContent || pendingReview) && !alreadyHydrated) {
    next.push({
      id: lastLocalUser?.id || nextId(),
      role: 'user',
      content: pendingContent,
      streaming: false,
      tools: [],
      thinking: '',
      images: lastLocalUser?.images || [],
      audio: lastLocalUser?.audio || null,
      audioSec: lastLocalUser?.audioSec ?? parseAudioLen(pendingContent),
      hadAudio: lastLocalUser?.hadAudio || isAudioLabel(pendingContent),
      review: pendingReview,
      sentAt: lastLocalUser?.sentAt,
      storedSessionId: lastLocalUser?.storedSessionId,
    });
  }
  if (resume?.running) {
    const last = next[next.length - 1];
    const inflight = String(resume.inflight?.assistant || '');
    const lastText = String(last?.content || '');
    const localStream = [...prev].reverse().find((message) => message.role === 'assistant' && message.streaming);
    const alreadyOnScreen = last?.role === 'assistant' && (
      last.streaming
      || sameAssistantText(last, { content: inflight })
    );
    if (alreadyOnScreen) {
      if (last.streaming) {
        next[next.length - 1] = {
          ...last,
          content: inflight.length > lastText.length ? inflight : last.content,
          tools: last.tools?.length ? last.tools : (localStream?.tools || last.tools),
          thinking: last.thinking || localStream?.thinking || '',
        };
      }
    } else if (localStream) {
      next.push({
        ...localStream,
        content: inflight.length > String(localStream.content || '').length ? inflight : localStream.content,
        streaming: true,
      });
    } else {
      next.push({
        id: nextId(),
        role: 'assistant',
        content: inflight,
        streaming: true,
        tools: [],
        thinking: '',
      });
    }
  }
  return next;
};

export const shouldAcceptRemoteResume = (prev, next, resume, force = false) => {
  if (force) return true;
  if (resume?.running) return true;
  const prevUsers = prev.filter((message) => message.role === 'user').map((message) => message.content);
  if (next.some((message) => message.role === 'user' && !prevUsers.includes(message.content))) {
    return true;
  }
  const prevAsst = prev.filter((message) => message.role === 'assistant').map((message) => message.content).join('\n');
  const nextAsst = next.filter((message) => message.role === 'assistant').map((message) => message.content).join('\n');
  return nextAsst.length > prevAsst.length;
};

// 粘贴/旧消息/复盘草稿可能没有 mime；data URL 仍保留实际媒体类型。
export const imageMimeOf = (file) => {
  if (file?.mime?.startsWith('image/')) return file.mime;
  return /^data:(image\/[^;,]+)/i.exec(file?.dataUrl || '')?.[1] || '';
};
