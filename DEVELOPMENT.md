# 省鑰冪粌习系统 - 寮€鍙戣鑼�

## 一銆佸瓧绗︾紪鐮侊紙鏈€楂樹紭鍏堢骇锛屽繀椤讳弗鏍奸伒瀹堬級

**鏈」目浠庣鐩樺埌娴忚鍣ㄈ摼路使鐢� UTF-8锛屼笉鍏佽浠讳綍鐜妭使鐢� GBK / GB18030 / GB2312 / CP936銆�**

### 1.1 鏂囦欢淇濆瓨缂栫爜

| 鏂囦欢绫诲瀷 | 缂栫爜 | BOM | 鎹㈣ |
|---|---|---|---|
| `.js` / `.jsx` / `.ts` / `.tsx` | **UTF-8** | **鏃� BOM** | `LF` |
| `.html` | **UTF-8** | **鏃� BOM** | `LF` |
| `.css` / `.scss` | **UTF-8** | **鏃� BOM** | `LF` |
| `.json` | **UTF-8** | **鏃� BOM** | `LF` |
| `.md` | **UTF-8** | **鏃� BOM** | `LF` |
| `.env` / `.env.example` | **UTF-8** | **鏃� BOM** | `LF` |
| `.sql` | **UTF-8** | **鏃� BOM** | `LF` |

> 为什么涓嶈兘鏈� BOM锛氶儴鍒� Node 瑙ｆ瀽鍣紙灏ゅ叾鑰佺増鏈級浼氭妸 BOM 褰撴櫘通瀛楃锛屽鑷� JSON 瑙ｆ瀽失璐ャ€丼hebang 失效绛夈€�

### 1.2 缂栬緫鍣ㄩ厤缃紙蹇呴』锛�

椤鼓挎牴宸叉彁渚� `.editorconfig`锛屾墍鏈夌紪杈戝櫒闇€要瀹壸�/鍚敤璇ヨ鑼冦€�

- **VS Code / Cursor**锛氬畨装鎻掍欢 `EditorConfig for VS Code`
- **JetBrains 系**锛氬唴缃ф寔锛屓疯宸插惎鐢�
- **Vim/Neovim**锛氬畨装 `editorconfig-vim`

**绂佒�**鍦ㄧ紪杈戝櫒閲屾墜鍔ㄥ垏鎹㈡垚 GBK 鎵撳紑/淇濆瓨椤鼓块噷鐨勪换浣曟枃浠躲€�

### 1.3 缁堢/Shell 缂栫爜

寮€鍙戞満闇€要使鐢� UTF-8 locale锛�

```bash
# Linux / macOS - 鏀惧埌 ~/.bashrc / ~/.zshrc
export LANG=en_US.UTF-8
export LC_ALL=en_US.UTF-8

# 楠屩�
locale            # 应鏄臼� *.UTF-8
echo $LANG        # 应为 en_US.UTF-8 鎴� zh_CN.UTF-8
```

- **Windows**锛毷圭敤 Windows Terminal + PowerShell 7+锛屽苟璁剧疆系统璇█鍖呏ф寔 UTF-8锛堟帶鍒堕潰鏉� 鈫� 鍖哄煙 鈫� 绠＄悊 鈫� Beta: 使鐢� UTF-8 鎻愪緵全鐞冭瑷€支鎸侊級銆�**绂佒�**使鐢ㄨ嚜甯� `cmd.exe`锛埬 CP936锛夈€�
- **鏈嶅姟鍣�**锛氶儴缃叉満蹇呴』鏄� `en_US.UTF-8`銆俙/etc/locale.gen` 鍚敤鍚� `locale-gen`銆�

### 1.4 Git 閰嶇疆

```bash
# 全灞€锛堟帹鑽愶級
git config --global core.autocrlf input        # Linux/macOS
git config --global core.autocrlf false        # Windows 也寤鸿 false锛岃尾鐢� .editorconfig 鎺у埗
git config --global core.quotepath false       # 路寰勯噷鐨勪腑鏂囦笉转涔�
git config --global i18n.commitEncoding utf-8
git config --global i18n.logOutputEncoding utf-8
```

### 1.5 HTTP / 娴忚鍣ㄧ紪鐮�

**前绔紙Vite锛�**

- `index.html` 鐨� `<head>` **绗昏**蹇呴』鏄� `<meta charset="UTF-8" />`
- `vite.config.js` 鐨� `forceUtf8Plugin` 鎻掍欢强鍒舵墍鏈� text 鍝嵱ν峰甫 `; charset=utf-8`
- 绂佒瑰湪 `index.html` 鐨� meta 之前鎻掑叆浠讳綍 `<script>` 鎴栧惈闈� ASCII 鐨勫唴瀹�

**鍚庣锛圗xpress锛�**

- `res.json(...)` 默璁や細甯� `Content-Type: application/json; charset=utf-8`锛屾棤闇€棰濆澶勭悊
- 鑷畾涔� `res.send(text)` 蹇呴』鏄臼借缃細`res.setHeader('Content-Type', 'text/plain; charset=utf-8')`
- 鏁版嵁搴擄紙SQLite锛夋枃鏈垪默璁ゆ寜 UTF-8 瀛樺偍锛宐etter-sqlite3 鏃犻渶棰濆閰嶇疆

### 1.6 鏁版嵁搴撶紪鐮�

- **SQLite**锛氭湰椤鼓渴圭敤 better-sqlite3銆傛枃鏈垪默璁� UTF-8 瀛樺偍銆傜止使鐢� BLOB 瀛樺瓧绗︿覆銆�
- 濡偽存潵鍒� **MySQL**锛氬繀椤� `utf8mb4` + `utf8mb4_unicode_ci`锛屼笉鍏佽 `utf8`锛圡ySQL 鐨� `utf8` 只鏄� 3 瀛楄妭锛屽瓨涓嶄笅 emoji锛夈€�
- 濡偽存潵鍒� **PostgreSQL**锛歚CREATE DATABASE ... ENCODING 'UTF8' LC_COLLATE='en_US.UTF-8' LC_CTYPE='en_US.UTF-8'`

### 1.7 甯歌涔辩爜妗堜緥閫熸煡

| 鐜拌薄 | 原鍥� | 淇硶 |
|---|---|---|
| 娴忚鍣ㄦ樉示 `浣犲ソ` / `閹兼粎閸岋拷` 绫讳贡鐮� | UTF-8 鏂囦欢琚祻瑙堝櫒鎸� GBK 瑙ｆ瀽 | 妫€鏌ュ搷应头鏄惁甯� `charset=utf-8`锛涙鏌� `<meta charset>` 位缃槸鍚﹀湪 `<head>` 寮€头 |
| 缁堢/鏃ブ鹃噷涓枃鏄� `??` | Locale 涓嶆槸 UTF-8 | `export LANG=en_US.UTF-8` |
| `git log` 涓枃鍙� `\346\200` 鍏繘鍒� | 未寮€鍚� `core.quotepath` | `git config --global core.quotepath false` |
| 粘璐翠唬鐮佸悗鍑虹幇涓嶅彲瑙佸瓧绗� `\ufeff` | 鏂囦欢鏈� UTF-8 BOM | 鐢� `dos2unix` 鎴栫紪杈戝櫒"鏃� BOM 淇濆瓨" |
| SSH 杩炰笂鏈嶅姟鍣ㄤ腑鏂囦贡鐮� | 瀹㈡埛绔� locale 没浼犺繃去 | SSH 瀹㈡埛绔缃� `SendEnv LANG LC_*`锛屾湇鍔＄ `AcceptEnv LANG LC_*` |

### 1.8 双閲嶇紪鐮侊紙Mojibake锛夌殑识鍒笌淇

**鍏稿瀷症状**锛氭枃浠� `file --mime-encoding` 鏄臼炬槸 `utf-8`銆佸搷应头也甯� `charset=utf-8`锛屼絾娴忚鍣ㄩ噷涓枃全鏄贡鐮侊紝涓斾贡鐮佸瓧绗︽湰韬兘鏄敓僻绻佷綋/寮備綋瀛楋紙濡� `鑰冪敓`銆乣閸楀洨楠囬弬瑙勵攳`銆乣浣犲ソ`锛夈€�

**原鍥�**锛氭枃浠赌骋绘琚� "鎸� UTF-8 璇诲瓧鑺� 鈫� 鎸� GBK 瑙ｇ爜鎴愭枃鏈� 鈫� 鍐嶆寜 UTF-8 淇濆瓨" 澶勭悊杩囷紝閫犳垚双閲嶇紪鐮併€�

**蹇€熷垽鏂�**锛堃昏鍛戒护锛夛細

```bash
python3 -c "
t = open('src/App.jsx','rb').read().decode('utf-8')
try:
    print('鍙兘鐨勗枃:', t.encode('gbk').decode('utf-8')[:200])
except Exception:
    print('鏂囦欢鏄共鍑€鐨� UTF-8锛屼笉鏄� mojibake')
"
```

濡傛灉"鍙兘鐨勗枃"璇昏捣鏉ユ槸通顺鐨勪腑鏂囷紝灏比疯琚噸缂栫爜浜嗐€�

**淇**锛氶」目鍐呰嚜甯﹁剼鏈� `scripts/fix-mojibake.py`锛屾寜娈垫櫤鑳藉弽瑙ｏ紝涓嶈浼ゆ确娈点€�

```bash
# 淇鍗曚釜鏂囦欢锛堜細鑷姩澶囦唤为 .bak锛�
python3 scripts/fix-mojibake.py src/App.jsx

# 浠呍よ涓嵭村叆
python3 scripts/fix-mojibake.py --dry-run src/App.jsx

# 扫鎻忔暣涓」目
python3 scripts/fix-mojibake.py --all
```

**预闃叉帾施**锛�

1. 浠讳綍缂栬緫鍣ㄥ湪鎵撳紑鏈」目鏂囦欢时蹇呴』鐢� UTF-8 鎵撳紑锛屼笉要璁╃紪杈戝櫒"鑷姩鐚�"缂栫爜銆�
2. 绂佒瑰湪 VS Code / Cursor 涓磋 "Reopen with Encoding 鈫� GBK/GB18030" 鍚庝繚瀛樸€�
3. 浼犺緭鐢� `scp` / `rsync` / `git`锛屼笉要鐢ㄤ細"鏅鸿兘转鎹㈢紪鐮�"鐨勫伐鍏凤紙濡偰承� Windows SFTP 瀹㈡埛绔殑"鏂囨湰模式"锛夈€�
4. SSH 涓ょ locale 閮藉繀椤绘槸 UTF-8锛堣 1.3锛夈€�

### 1.9 鎻愪氦前鑷鍛戒护

```bash
# 扫鎻忔暣涓」目锛屓疯鎵€鏈夋枃鏈存枃浠堕兘鏄� UTF-8锛堟垨绾� ASCII锛�
find . -type f \
  \( -name "*.js" -o -name "*.jsx" -o -name "*.ts" -o -name "*.tsx" \
     -o -name "*.html" -o -name "*.css" -o -name "*.md" -o -name "*.json" -o -name "*.sql" \) \
  -not -path "./node_modules/*" -not -path "./.git/*" -not -path "./dist/*" \
  -exec sh -c 'enc=$(file -b --mime-encoding "$1"); case "$enc" in utf-8|us-ascii) ;; *) echo "NON-UTF8: $1 ($enc)";; esac' _ {} \;

# 扫鎻忔槸鍚︽湁 UTF-8 BOM
grep -rlI $'^\xEF\xBB\xBF' --include="*.{js,jsx,ts,tsx,html,css,md,json}" . 2>/dev/null
```

---

## 浜屻€侀」目缁撴瀯

```
ExamSystem/
鈹溾攢鈹€ index.html              # 鍏ュ彛 HTML锛坈harset 蹇呴』鏈€鍏堝０鏄庯級
鈹溾攢鈹€ vite.config.js          # Vite 閰嶇疆锛堝惈 forceUtf8Plugin锛�
鈹溾攢鈹€ src/                    # 前绔� React 源鐮�
鈹�   鈹溾攢鈹€ main.jsx            # 鍏ュ彛
鈹�   鈹溾攢鈹€ App.jsx             # 鏍圭粍浠�
鈹�   鈹溾攢鈹€ Login.jsx           # 鐧宦家�
鈹�   鈹溾攢鈹€ api.js              # 前绔� API 灏佔�
鈹�   鈹斺攢鈹€ index.css           # 全灞€鏍肥斤紙Tailwind锛�
鈹溾攢鈹€ server/                 # 鍚庣 Express 源鐮�
鈹�   鈹溾攢鈹€ index.js            # 鍏ュ彛
鈹�   鈹溾攢鈹€ db.js               # better-sqlite3 灏佔�
鈹�   鈹溾攢鈹€ auth.js             # 鐧宦奸壌权
鈹�   鈹斺攢鈹€ routes/             # 业鍔÷风敱
鈹�       鈹溾攢鈹€ questions.js
鈹�       鈹溾攢鈹€ practice.js
鈹�       鈹溾攢鈹€ mistakes.js
鈹�       鈹溾攢鈹€ reviews.js
鈹�       鈹斺攢鈹€ stats.js
鈹溾攢鈹€ data/                   # SQLite 鏁版嵁搴撴枃浠讹紙涓嶈繘 git锛�
鈹溾攢鈹€ public/                 # 闈櫶祫源锛坒avicon 绛夛級
鈹溾攢鈹€ .env                    # 鏈湴鐜鍙橀噺锛堜笉杩� git锛�
鈹溾攢鈹€ .env.example            # 鐜鍙橀噺示渚�
鈹斺攢鈹€ DEVELOPMENT.md          # 鏈枃浠�
```

---

## 涓夈€佹湰鍦板紑鍙�

```bash
# 1. 瀹壸颁緷璧栵紙只闇€棣栨锛�
npm install

# 2. 閰嶇疆鐜鍙橀噺
cp .env.example .env
# 缂栬緫 .env锛岃嚦灏戣缃� EXAM_PASSWORD=鑷畾涔夊瘑鐮�

# 3. 同时鍚姩前鍚庣
npm run dev
# 前绔� http://localhost:5173/
# 鍚庣 http://localhost:3001/api/health
```

## 鍥涖€佺鍙Ｔ煎畾

| 绔彛 | 鐢ㄍ� |
|---|---|
| `5173` | Vite 前绔紑鍙戞湇 |
| `3001` | Express 鍚庣 API |

前绔ㄨ繃 Vite 浠ｇ悊 `/api/*` 鈫� `http://localhost:3001`锛屾墍浠ユ祻瑙堝櫒只闇€璁块棶 `5173`銆�

## 浜斻€佸父鐢ㄥ懡浠�

```bash
npm run dev          # 鍚姩前鍚庣锛堝甫 HMR锛�
npm run dev:web      # 浠呭惎鍔ㄇ扮
npm run dev:server   # 浠呭惎鍔ㄥ悗绔紙nodemon 鐑噸鍚級
npm run build        # 鐢熶骇鏋勫缓
npm run preview      # 预瑙� build 浜х墿
npm run lint         # ESLint 妫€鏌�
```

## 鍏€佷唬鐮侀鏍�

- **缁勪欢**锛氬嚱鏁扮粍浠� + Hooks锛屼笉使鐢� Class
- **鍛藉悕**锛歊eact 缁勪欢 PascalCase锛涙櫘通鍑芥暟 camelCase锛涘父閲� UPPER_SNAKE_CASE
- **注閲�**锛氈诲湪瑙ｉ噴"为什么"时写锛屼笉写"杩欎釜循鐜槸鍋毷裁�"杩欑搴熻瘽
- **涓枃**锛歎I 鏂囨鐢ㄤ腑鏂囷紱浠ｇ爜閲岀殑鍙橀噺鍚�/鍑芥暟鍚�/鏃ブ臼圭敤英鏂�
- **绂佒�**锛氫换浣曞舰式鐨勅眬鍙橀噺姹∪俱€乣var` 澹版槑

## 涓冦€丟it 鎻愪氦瑙勮寖

```
<type>: <subject>

<body>
```

type 取值锛歚feat` / `fix` / `style` / `refactor` / `perf` / `test` / `docs` / `chore`

---

**鏈€鍚幥胯皟一娆★細鎵€鏈夋枃浠躲€佹墍鏈夌粓绔€佹墍鏈夌綉缁滀紶杈撱€佹墍鏈夋暟鎹簱瀛樺偍锛屢诲緥使鐢� UTF-8锛屾棤 BOM銆�**
