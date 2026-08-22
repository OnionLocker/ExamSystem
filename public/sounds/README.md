# 背景音采样素材

> 番茄钟的背景音引擎：**纯采样 + 随机事件层**。
> 每个场景由「底层 loop」+「随机事件音」叠加而成，听感接近 mynoise / Endel。

## 目录结构

```
public/sounds/
├─ rain.mp3            ← 底层 loop（10 个场景）
├─ thunderstorm.mp3
├─ ocean.mp3
├─ ...
└─ events/             ← 随机事件音
   ├─ bird1.mp3 ~ bird4.mp3
   ├─ thunder1.mp3 ~ thunder3.mp3
   └─ cricket.mp3
```

## 底层 loop（10 个场景）

播放时由 `SoundEngine` 做 **0.8s 等功率交叉淡化** 再 `loop`，文件本身不再做首尾淡化（否则每圈会掉一截音量）。

规格：mp3 / **48 kHz / 立体声 / 192 kbps**，多数截到 120s。

| 文件 | 时长 | 大小 | 来源（许可） |
|---|---:|---:|---|
| `rain.mp3`         | 120s | 2.8M | Freesound [549909](https://freesound.org/people/deadrobotmusic/sounds/549909/) deadrobotmusic · CC0 |
| `thunderstorm.mp3` | 120s | 2.8M | Freesound [738091](https://freesound.org/people/soundofsong/sounds/738091/) soundofsong · CC0 |
| `ocean.mp3`        | 120s | 2.8M | Freesound [578524](https://freesound.org/people/SamsterBirdies/sounds/578524/) SamsterBirdies · CC0 |
| `stream.mp3`       | 120s | 2.8M | Freesound [621107](https://freesound.org/people/hargissssound/sounds/621107/) hargissssound · CC0 |
| `forest.mp3`       | 64s  | 1.5M | Freesound [850507](https://freesound.org/people/GammaGool/sounds/850507/) GammaGool · CC0 |
| `fire.mp3`         | 120s | 2.8M | Freesound [729396](https://freesound.org/people/HECKFRICKER/sounds/729396/) HECKFRICKER · CC0 |
| `wind.mp3`         | 62s  | 1.5M | Mixkit 2658（立体声预览） |
| `night.mp3`        | 51s  | 1.2M | Freesound [436528](https://freesound.org/people/KikeVilaplana/sounds/436528/) KikeVilaplana · CC0 |
| `cafe.mp3`         | 120s | 2.8M | Freesound [746428](https://freesound.org/people/douglasbruce@look.ca/sounds/746428/) · CC0 |
| `keyboard.mp3`     | 120s | 2.8M | Freesound [661435](https://freesound.org/people/Brazilio123/sounds/661435/) Brazilio123 · CC0 |

## 随机事件音

事件音叠在底层 loop 之上，按配置好的随机间隔触发，破除"loop 感"。

| 场景 | 事件 | 间隔 | 音量 |
|---|---|---|---|
| forest | 4 种鸟鸣（bird1~4） | 6~22 秒 | 55% |
| thunderstorm | 3 种雷声（thunder1~3） | 18~60 秒 | 85% |
| rain | 2 种远雷（复用 thunder1~2） | 90~240 秒 | 35% |
| night | 1 种蟋蟀（cricket） | 12~35 秒 | 45% |

事件音规格：mp3 / 44.1 kHz / 单声道 / 96 kbps，1~5 秒，应用 dynaudnorm 归一。

> 其他场景（ocean / stream / fire / wind / cafe / keyboard）当前**没有事件层**——
> 它们的底层 loop 已经包含足够的"颗粒变化"（浪声起伏、火焰噼啪、键盘敲击都是离散事件本身），
> 不需要再叠加。

## 想加新事件 / 改间隔？

打开 `src/pomodoro/PomodoroContext.jsx`，找到 `SCENE_EVENTS`：

```js
const SCENE_EVENTS = {
  forest: {
    sounds: ['/sounds/events/bird1.mp3', /* ... */],
    minMs: 6000,    // 最短间隔
    maxMs: 22000,   // 最长间隔
    volume: 0.55,   // 相对底层的音量倍率
  },
  // ...
};
```

加新场景的事件层：在 `SCENE_EVENTS` 加一条，然后把对应 mp3 放到 `events/` 即可。

## 来源 & 许可证

底层 loop 以 **Freesound CC0** 实采为主（公有领域，无需署名）；`wind.mp3` 仍用 Mixkit 立体声预览。事件音仍来自 Mixkit。

Freesound CC0：https://creativecommons.org/publicdomain/zero/1.0/
Mixkit 音效许可：https://mixkit.co/license/

Mixkit License 要点：
- ✅ 商用 / 非商用免费
- ✅ 无需署名
- ❌ 不能把素材本身打包二次销售（嵌入应用使用是允许的）

## 想替换某个素材？

任意素材听着不喜欢，去 Mixkit 对应分类挑：

```
https://mixkit.co/free-sound-effects/<category>/
分类 slug：rain / thunder / ocean / water / forest / fire / wind / night / restaurant / keyboard / bird / lightning
```

直链格式：`https://assets.mixkit.co/active_storage/sfx/<ID>/<ID>-preview.mp3`

底层 loop 处理（立体声 192k，不要首尾淡化）：
```bash
ffmpeg -y -t 120 -i raw.mp3 -ac 2 -ar 48000 -b:a 192k \
  -af "highpass=f=50" \
  public/sounds/<scene>.mp3
```

事件音处理（短促单次音）：
```bash
ffmpeg -y -i raw.mp3 -ac 1 -ar 44100 -b:a 96k \
  -af "afade=t=in:st=0:d=0.05,afade=t=out:st=<dur-0.1>:d=0.1,dynaudnorm=p=0.7:s=10" \
  public/sounds/events/<event>.mp3
```

## 故障

控制台看到：
```
[SoundEngine] 采样加载失败：/sounds/<scene>.mp3
```
→ 文件路径不对，按错误信息检查。底层 loop 缺失会**整个场景静音**；事件音缺失会**静默跳过该事件**，不影响底层 loop。

控制台看到 `bgmType` 是 `white` / `pink` / `brown` 的旧值？这三个场景已下线，引擎会自动回退到 `rain`。

---

## 数资模块 BGM(`bgm/`)

数资模块独立的「沉浸式 BGM」，由 `src/practice/bgm.js` 引擎管理（与番茄钟 SoundEngine、Mixer SoundMixer 完全独立）。

| 文件 | 触发时机 | 风格 | 来源 |
|------|---------|------|------|
| `bgm/games.mp3`    | 进入小游戏 modal 时           | 轻快 town/chiptune | OpenGameArt CC0 — [Happy Town](https://opengameart.org/content/happy-town) |
| `bgm/training.mp3` | 数资训练模式 session 开始时   | 平静 ambient       | OpenGameArt CC0 — [josepharaoh99 / Dust](https://opengameart.org/content/cc0-calm-relaxing-music) |
| `bgm/ranked.mp3`   | 数资晋升(排位)模式 session    | 8-bit boss battle  | OpenGameArt CC0 — [8bit Action Boss Battle](https://opengameart.org/content/8bit-action-boss-battle) |

资源协议：CC0 / 公有领域（允许商用，无需署名）。

### 缺失策略

任何一个 mp3 缺失或解码失败 → 该轨道在 `BgmEngine` 内被标记为 `loadFailed`，UI 上会显示「资源缺失」但**不会报错**，其他 BGM/UI 不受影响。想替换风格直接覆盖这三个文件即可，无需改代码。

### 用户偏好持久化

启用状态 + 音量保存在 localStorage `bgm_prefs_v1`，跨页面/刷新保持一致。

