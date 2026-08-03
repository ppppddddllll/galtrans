# 「大图书馆」 一键汉化工具

> 面向 Windows 的 galgame 汉化工具，支持 **离线脚本汉化** 与 **实时翻译** 两种模式。

<p align="center">
  <img src="assets/logo.png" alt="大图书馆 汉化工具" width="220">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-GPLv3-blue.svg" alt="License: GPLv3">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python: 3.10+">
  <img src="https://img.shields.io/badge/platform-Windows-lightgrey.svg" alt="Platform: Windows">
  <img src="https://img.shields.io/badge/GUI-PySide6-green.svg" alt="GUI: PySide6">
</p>

支持两种核心翻译方式：

1. **离线脚本汉化**：解析游戏脚本（Ren'Py / Kirikiri），批量翻译后生成汉化补丁与对照表。
2. **实时翻译**：框选屏幕区域，用 Windows 内置 OCR 识别日文文本，实时翻译并显示在悬浮窗中。

## 功能特性

| 功能 | 说明 |
| --- | --- |
| Ren'Py 支持 | 解析 `.rpy` 对话，支持 `.rpa` 归档解包 |
| Kirikiri 支持 | 解析 `.ks/.txt/.kst/.ksc`，自动检测编码（SJIS/UTF-16/UTF-8），剥离颜色码与控制标签 |
| OCR 兜底 | Windows 内置 OCR，兼容任何游戏（需安装日语语言包效果最佳） |
| 多翻译引擎 | DeepSeek / DeepL / Google / Bing 可选，主引擎失败自动降级 + 冷却恢复 |
| 术语表 | 维护日译中对照表，翻译时优先套用（人名、专名） |
| 汉化补丁 | 输出镜像原目录结构的 `patch/` 目录，保留原始脚本标签与结构 |
| 翻译对照表 | 导出 CSV（文件/行号/原文/译文），便于人工校对 |
| 悬浮窗 | 网易云歌词风格置顶翻译条，支持拖拽、大小/透明度/字体/文字颜色调节 |
| API Key 加密 | 密钥经 Windows DPAPI 加密存储，配置文件不落明文 |

## 安装

需要 Python 3.10+（开发环境为 3.14）。

```powershell
# 在项目根目录执行
pip install -e .
```

如需要打包成单文件 exe：

```powershell
pip install pyinstaller
pyinstaller build.spec --noconfirm --distpath dist --workpath build
```

产物为独立的 `dist\大图书馆汉化工具.exe`，双击即可运行，无需安装 Python。

> **打包说明**
> - onefile 模式：全部依赖内嵌进单个 exe，首次启动需解压到临时目录（约 5–15 秒），属正常现象。
> - 已做瘦身：排除 Qt 无用模块（Quick/Qml/Pdf/Network 等）与 numpy，体积从 ~156MB 降至约 55MB。
> - 单文件 exe 可能被 Windows Defender / 360 等**误报**，属 PyInstaller 常见情况，请添加白名单后运行。

## 运行

```powershell
python -m galtrans
```

## 使用流程

### 离线汉化

1. 打开「离线汉化」页，选择游戏根目录（含 `.rpy`/`.ks` 的目录），或直接选中游戏 `exe`（自动定位到所在目录）。
2. 选择输出目录。
3. 在「设置」页配置主翻译引擎（DeepSeek 需要 API Key，DeepL 需注册免费 Key，Google/Bing 免 Key）。
4. 点击「开始汉化」，完成后在输出目录得到 `patch/` 与 `translation_table.csv`。

### 汉化后如何使用补丁

输出目录结构：

```
输出目录/
├── patch/                  ← 汉化补丁（镜像原游戏目录结构）
│   └── ...
└── translation_table.csv   ← 翻译对照表（文件/行号/原文/译文）
```

| 步骤 | 操作 |
| --- | --- |
| ① 应用补丁 | 将 `patch/` 内的文件**覆盖到游戏根目录**，保持相对路径一致，启动游戏即为中文 |
| ② 校对（可选） | 用 Excel/WPS 打开 `translation_table.csv`，逐条核对翻译质量 |
| ③ 还原原版 | 用备份的脚本文件覆盖回去即可（游戏本体未被修改） |

> **注意事项**
> - 覆盖前建议先**备份原脚本文件**，避免汉化问题后无法还原。
> - Ren'Py 的旧存档可能因对话文本变化产生 mismatch，建议汉化后开新档测试。
> - 补丁会按原文件编码回写（SJIS/UTF-16/UTF-8），一般无需手动处理。
> - `patch/` 目录不能单独移动，必须保持内部相对结构与游戏目录一致。
> - 若汉化后进游戏仍是日文，说明补丁覆盖位置不对，检查相对路径是否一致。

### 实时翻译（不稳定，网络连接差时延迟非常大；悬浮窗功能正在测试，因此不建议使用实时翻译）

1. 打开「实时翻译」页。
2. 点击「框选区域」，在屏幕上框住游戏对话文本区域。
3. 在「引擎」下拉框选择实时翻译引擎（默认 **Bing**，最快且免 Key）。
4. 勾选「显示悬浮窗」后点击「开始」。
5. 游戏内出现新文本时，悬浮窗实时显示译文。

> **独立引擎配置**：实时翻译的引擎与离线汉化分离，实时页只使用自己选的引擎（不参与离线配置的降级链），
> 默认 Bing 响应最快；追求翻译质量可切 DeepSeek（需 Key）。
>
> 提示：OCR 需要日语识别。在 Windows「设置 → 时间和语言 → 语言」中添加日语语言包后效果最佳。

## 翻译消耗（Token）

只有 **DeepSeek** 按 Token 计费；**Google / Bing / DeepL** 免费接口不消耗 Token。（DeepL的官方免费API计划已经不再对新用户开放了）

### 单次请求估算（默认 batch_size=16 行）

| 组成 | Token 估算 |
| --- | --- |
| 系统提示词（固定） | ~200 |
| 指令 + 术语表（固定） | ~100–150 |
| 16 行日文输入（每行约 20 字） | ~400–500 |
| 16 行中文输出 | ~400–500 |
| **单批合计** | **约 1100–1300 Token** |

### 整部游戏估算

| 剧本规模 | 输入 + 输出总量 |
| --- | --- |
| 小短篇（约 5 千行） | ~25 万 Token |
| 中等 galgame（约 3 万行） | ~150 万 Token |
| 大型 galgame（约 10 万行） | ~500 万 Token |

### 节省 Token 的技巧

- **内置翻译缓存**：相同句子只翻译一次，重复台词不重复计费。
- **调大 `batch_size`**（设置页 1–64）：单次请求放入更多文本，摊薄固定的提示词成本。
- **优先用免费引擎**：Google / Bing / DeepL 免费接口不消耗 Token，适合大批量但质量要求不高的场景。

## 术语表使用

术语表是「日文 → 中文」对照表，用于统一人名、地名、招式等专有名词的翻译。

### 操作入口

打开「术语表」页：

| 操作 | 说明 |
| --- | --- |
| 添加词条 | 上方输入日文原名与中文译名，点「添加」（如 `綾瀬` → `绫濑`） |
| 启用开关 | 勾选「启用术语表」后词条才生效 |
| 删除 / 清空 | 选中表格行点「删除选中」，或「清空」全部 |
| 导入 / 导出 | 支持 JSON 文件批量导入 / 导出备份 |

### 生效机制

1. **翻译前预处理**：源文本中匹配到的日文词条会被直接替换为中文，保证绝对一致。
2. **提示词注入**：词条同时作为参考译名发送给 DeepSeek，覆盖未直接命中的场景。

> 匹配采用**最长匹配**原则，`綾瀬` 与 `綾瀬学園` 同时存在时优先匹配更长的 `綾瀬学園`。

### 导入 JSON 格式

```json
[["綾瀬", "绫濑"], ["さくら", "樱"]]
```

### 建议用法

开始翻译某部作品前，先整理该作的人名 / 专名对照表（可网上搜索汉化对照表），一次性导入，能显著提升专有名词的统一度。DeepL / Google / Bing 等普通接口同样会走「预处理替换」这条路径。

## 配置

配置文件位于 `~/.galtrans/config.json`，也可用环境变量 `GALTRANS_HOME` 指定配置目录。

- `translate.primary` / `translate.fallbacks`：主引擎与降级顺序（`deepseek`/`deepl`/`google`/`bing`）。
- `realtime.engine`：实时翻译页独立引擎（默认 `bing`）。
- `translate.concurrency` / `batch_size` / `rate_limit_per_min`：并发与限流参数。
- `ocr.interval`：实时翻译轮询间隔（秒）。
- `overlay`：悬浮窗样式（透明度、字号、历史行数、位置）。

> API Key 使用 Windows DPAPI 加密存储在 `~/.galtrans/secrets.json`，`config.json` 不落明文。

## 测试

```powershell
python -m pytest tests -v
```

测试覆盖：配置读写、术语表、两种解析器、离线流水线（含取消）、翻译降级调度、缓存、实时会话去重与错误恢复、GUI 构建、悬浮窗。

## 项目结构

```
galtrans/
├── config.py            # 配置读写
├── glossary.py          # 术语表
├── secrets_store.py     # API Key 加密存储（Windows DPAPI）
├── ocr.py               # Windows 内置 OCR 封装
├── realtime.py          # 实时翻译会话（截屏→OCR→翻译）
├── pipeline.py          # 离线汉化流水线
├── main.py              # 程序入口
├── parsers/             # 脚本解析器
│   ├── base.py          #   解析器基类与数据结构
│   ├── kirikiri.py      #   Kirikiri/KAG
│   └── renpy.py         #   Ren'Py + RPA 解包
├── translate/           # 翻译引擎
│   ├── base.py          #   引擎基类
│   ├── deepseek.py      #   DeepSeek（OpenAI 兼容）
│   ├── deepl.py         #   DeepL 免费 API
│   ├── google.py        #   Google 免费接口
│   ├── bing.py          #   Bing 免费接口
│   └── manager.py       #   多引擎调度与降级
└── ui/                  # PySide6 图形界面
    ├── main_window.py   #   主窗口导航
    ├── offline_page.py  #   离线汉化页
    ├── realtime_page.py #   实时翻译页
    ├── glossary_page.py #   术语表页
    ├── settings_page.py #   设置页
    ├── overlay.py       #   悬浮翻译窗
    ├── style.py         #   全局样式表
    └── language_guide.py #  OCR 语言包引导
```

## 已知限制

- OCR 需系统安装日语语言包才能准确识别日文。
- 离线汉化对 Kirikiri 支持常见 KAG 语法；极端自定义脚本可能解析不完全。
- 免费翻译接口（Google/Bing）稳定性有限，量大时建议用 DeepSeek 或 DeepL。
- 单文件 exe 首次启动需解压（5–15 秒），且可能被部分杀毒软件误报，请添加白名单。

## 常见问题（FAQ）

**Q1：翻译结果一直是日文 / 和原文相同？**

大概率是翻译引擎没生效。免费接口（Bing/Google）在国内网络环境稳定性差，DeepL 免费计划已不对新用户开放。请到「设置」页配置有效的 **DeepSeek API Key**（或 DeepL Key），并点击「测试所有引擎连接」确认可用后再汉化。

**Q2：实时翻译卡顿、延迟很大？**

实时翻译是「截屏 → OCR → 联网翻译」循环（默认 0.8 秒一次），延迟由网络与 OCR 耗时决定。追求速度在实时页选 Bing 或 Google；网络差时建议直接用离线汉化。

**Q3：OCR 识别不准 / 识别不了日文？**

Windows 内置 OCR 需要日语语言包。按「实时翻译」页顶部的「日语 OCR 引导」操作：`设置 → 时间和语言 → 语言 → 添加语言 → 日本語`，安装后点「重新检测」。

**Q4：exe 被杀毒软件拦截 / 删除？**

单文件 PyInstaller 打包常被误报，请将 exe 加入 Windows Defender 或第三方杀软的白名单。

**Q5：汉化补丁怎么用？**

把输出目录的 `patch/` 下所有文件按相对路径覆盖到游戏根目录（先备份原文件），启动游戏即为中文。对照表 `translation_table.csv` 用 Excel 打开校对。

**Q6：Ren'Py 游戏汉化后旧存档报错？**

对话文本变化会导致旧存档 mismatch，建议汉化后开新档测试。

**Q7：换了游戏目录，之前的设置还在吗？**

配置存于 `~/.galtrans/config.json`，跨游戏通用。不同游戏建议分别导出/导入术语表。

## 其他

- 强烈建议使用离线汉化（DeepSeek 足够便宜了，且效果最好）。
- DeepSeek 模型可能需与时俱进（截止 2026-8-3 ，最新模型为 deepseek-v4-flash & deepseek-v4-pro ）。

## 许可证

本项目基于 [GPL-3.0](LICENSE) 开源协议发布。请遵守协议要求，如需商用请咨询作者。

## 贡献

欢迎提交 Issue 与 Pull Request：

1. Fork 本仓库并创建你的分支。
2. 修改代码时遵循以下约定：
   - 代码注释使用中文；
   - 优先函数式编程，避免 `class`；
   - 变量名用驼峰 `getUserInfo`，常量用全大写下划线 `API_KEY`；
   - 函数不超过 50 行，避免嵌套超过 3 层。
3. 提交前运行 `python -m pytest tests -q`，确保全部测试通过（当前 25 个用例）。
4. 提交 Pull Request 并描述改动内容。
