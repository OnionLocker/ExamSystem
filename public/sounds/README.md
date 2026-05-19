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

| 文件 | 时长 | 大小 | 来源 |
|---|---:|---:|---:|
| `rain.mp3`         | 60s | 938K | Mixkit 2392 |
| `thunderstorm.mp3` | 46s | 720K | Mixkit 2415 |
| `ocean.mp3`        | 60s | 938K | Mixkit 1208 |
| `stream.mp3`       | 60s | 938K | Mixkit 2456 |
| `forest.mp3`       | 60s | 938K | Mixkit 1210 |
| `fire.mp3`         | 21s | 330K | Mixkit 1330 |
| `wind.mp3`         | 59s | 921K | Mixkit 2658 |
| `night.mp3`        | 60s | 938K | Mixkit 2482 |
| `cafe.mp3`         | 60s | 938K | Mixkit  444 |
| `keyboard.mp3`     | 23s | 366K | Mixkit 1386 |

规格：mp3 / 44.1 kHz / 单声道 / 128 kbps，首尾 0.4s 淡化。

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

全部来自 **[Mixkit](https://mixkit.co/free-sound-effects/)**，使用 **[Mixkit License](https://mixkit.co/license/)**：
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

底层 loop 处理（60s 单声道 mp3）：
```bash
ffmpeg -y -ss 2 -i raw.mp3 -t 60 -ac 1 -ar 44100 -b:a 128k \
  -af "afade=t=in:st=0:d=0.4,afade=t=out:st=59.6:d=0.4" \
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
