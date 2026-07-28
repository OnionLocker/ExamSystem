// Hermes JSON-RPC over WebSocket 客户端（浏览器侧）
//
// 协议与 hermes 官方 dashboard 完全一致：换行分隔的 JSON-RPC 2.0，双向。
// 请求走 request()，返回 Promise；agent 的流式事件走 on(type, cb)。
//
//   const gw = new HermesGateway();
//   gw.on('message.delta', (ev) => append(ev.payload.text));
//   await gw.connect();
//   const { session_id } = await gw.request('session.create', { cwd: '/home/ubuntu' });
//   await gw.request('prompt.submit', { session_id, text: '你好' });

import { getToken } from '../api.js';

const REQUEST_TIMEOUT_MS = 180000; // 一轮对话可能跑很久（工具调用），给足时间
const CONNECT_TIMEOUT_MS = 15000;
const MAX_BACKOFF_MS = 15000;

const ANY = '*';

export class HermesGateway {
  constructor() {
    this.socket = null;
    this.state = 'idle'; // idle | connecting | open | closed | error
    this.nextId = 0;
    this.pending = new Map();
    this.handlers = new Map();
    this.stateHandlers = new Set();
    this.attempt = 0;
    this.wantOpen = false;
    this.reconnectTimer = null;
  }

  get connectionState() {
    return this.state;
  }

  // ---------- 事件订阅 ----------
  on(type, cb) {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type).add(cb);
    return () => this.handlers.get(type)?.delete(cb);
  }

  onState(cb) {
    this.stateHandlers.add(cb);
    return () => this.stateHandlers.delete(cb);
  }

  setState(next) {
    if (this.state === next) return;
    this.state = next;
    for (const cb of this.stateHandlers) {
      try { cb(next); } catch { /* 订阅者自己的错误不影响连接 */ }
    }
  }

  emit(event) {
    for (const type of [event.type, ANY]) {
      const set = this.handlers.get(type);
      if (!set) continue;
      for (const cb of set) {
        try { cb(event); } catch (err) { console.error('[hermes] 事件处理出错', err); }
      }
    }
  }

  // ---------- 连接 ----------
  url() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const token = encodeURIComponent(getToken());
    return `${proto}//${window.location.host}/api/hermes/ws?token=${token}`;
  }

  connect() {
    this.wantOpen = true;
    if (this.state === 'open' || this.state === 'connecting') return Promise.resolve();

    this.setState('connecting');

    return new Promise((resolve, reject) => {
      let socket;
      try {
        socket = new WebSocket(this.url());
      } catch (err) {
        this.setState('error');
        reject(err);
        return;
      }
      this.socket = socket;

      const timer = setTimeout(() => {
        if (this.socket === socket && this.state === 'connecting') {
          try { socket.close(); } catch { /* 已经没了 */ }
          this.setState('error');
          reject(new Error('连接 Hermes 超时'));
        }
      }, CONNECT_TIMEOUT_MS);

      socket.addEventListener('open', () => {
        if (this.socket !== socket) return;
        clearTimeout(timer);
        this.attempt = 0;
        this.setState('open');
        resolve();
      });

      socket.addEventListener('message', (msg) => {
        if (this.socket !== socket) return;
        // 一个 WS 帧里可能有多条换行分隔的 JSON-RPC
        for (const line of String(msg.data).split('\n')) {
          const trimmed = line.trim();
          if (trimmed) this.handleFrame(trimmed);
        }
      });

      socket.addEventListener('error', () => {
        if (this.socket !== socket) return;
        clearTimeout(timer);
        // close 事件紧随其后，重连逻辑统一放在 close 里
      });

      socket.addEventListener('close', () => {
        if (this.socket !== socket) return;
        clearTimeout(timer);
        // 断线时机决定要不要 reject connect() —— 必须在 setState 之前判断
        const wasConnecting = this.state === 'connecting';
        this.socket = null;
        this.setState('closed');
        this.rejectAllPending(new Error('连接已断开'));
        if (wasConnecting) reject(new Error('连接 Hermes 失败'));
        this.scheduleReconnect();
      });
    });
  }

  scheduleReconnect() {
    if (!this.wantOpen || this.reconnectTimer) return;
    const delay = Math.min(MAX_BACKOFF_MS, 800 * 2 ** this.attempt);
    this.attempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.wantOpen && this.state !== 'open') {
        this.connect().catch(() => { /* 失败会再次触发 close → 重排 */ });
      }
    }, delay);
  }

  close() {
    this.wantOpen = false;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    this.rejectAllPending(new Error('已关闭'));
    const socket = this.socket;
    this.socket = null;
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
      try { socket.close(1000, 'client closing'); } catch { /* 忽略 */ }
    }
    this.setState('closed');
  }

  // ---------- 帧处理 ----------
  handleFrame(line) {
    let frame;
    try {
      frame = JSON.parse(line);
    } catch {
      console.warn('[hermes] 收到非 JSON 帧', line.slice(0, 120));
      return;
    }

    // 请求应答
    if (frame.id != null && this.pending.has(frame.id)) {
      const call = this.pending.get(frame.id);
      this.pending.delete(frame.id);
      clearTimeout(call.timer);
      if (frame.error) call.reject(new Error(frame.error.message || 'Hermes 返回错误'));
      else call.resolve(frame.result);
      return;
    }

    // agent 事件
    if (frame.params?.type) this.emit(frame.params);
  }

  request(method, params = {}) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('尚未连接到 Hermes'));
    }
    const id = `e${++this.nextId}`;
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`${method} 超时`));
      }, REQUEST_TIMEOUT_MS);
      this.pending.set(id, { resolve, reject, timer });
      try {
        this.socket.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }) + '\n');
      } catch (err) {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(err);
      }
    });
  }

  rejectAllPending(err) {
    for (const [, call] of this.pending) {
      clearTimeout(call.timer);
      call.reject(err);
    }
    this.pending.clear();
  }
}

export default HermesGateway;
