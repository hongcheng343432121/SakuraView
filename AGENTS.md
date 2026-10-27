# AGENTS.md · workBuild 任务说明（SakuraView CG 工作包）

> 本文件是给 AI 代理（workBuild）的执行说明。任何拿到本文件夹的代理，读完本文件 + 《SakuraView-CG工作流.md》后，就应能独立完成一个 Galgame 项目从提取 CG 到建站的全部工作。

## 前置：改界面之前必读 `DESIGN.md`

**只要你的改动会碰到 UI（配色、字号、间距、圆角、动效、阴影），先读完根目录的 `DESIGN.md` 再动手。**
那份文件是硬约束，不是建议：

- 色板、5 级字号、4 倍数间距、圆角只有 `2px` / `50%`、阴影全禁
- 动效只允许 `color / border-color / opacity / brightness`，禁止位移与缩放
- 末尾有 **10 条「AI 味禁止清单」** 和 **6 条自检**——改完逐条过一遍再交付
- 图库（`gen_site_generic.py` 的 `CSS`）与落地页（根 `index.html`）是两套变量名、**同一套值**；
  改一处必须同步另一处，否则我会把两边的 token 改漂移

要打破其中某条，在 commit message 里写清理由；没写理由的一律视为 bug。

## 你的目标

用户给你一个 Galgame 游戏的安装目录（或压缩包），你负责产出：

1. 一个可直接双击浏览的 **SakuraView 静态图库**（`CG\index.html` + 分组页 + 收藏页）；
2. 一份**执行报告**（提取了多少、分了几个组、验收清单逐项结果）。

## 零、最快的一条路：一键处理

不用记参数，把游戏文件夹**拖到 `一键处理.bat` 上**就行（或命令行 `一键处理.bat "D://game//某游戏"`）。
它会：识别引擎 → 解包 → 整理成 `CG\<分类>\<分组>` → 建站 → 转视频/海报/缩略图 → 登记 Hub → 打开浏览器。

可选参数：`--name "标题"`、`--key mygame`、`--out 目录`、`--no-extract`、`--no-media`、`--no-hub`、`--no-open`、`--dry`。
支持的引擎：QLIE（FilePackVer3.0 / 3.1）、Ren'Py（\*.rpa）、Godot（\*.pck）；
Unity 需要先用 AssetStudioModCLI 导出纹理，脚本会给提示。

想手工控制每一步，再按下面两种方式走。**重建也不必全量**：`rebuild_all.py` 会算 CG 目录指纹，
没变的库直接跳过（17 个库全没变时 0.6 秒返回），改了 `gen_site_generic.py` 会自动全量重建。

## 一、项目指定的两种方式

**方式一：对话指令（单个项目）**

用户会这样告诉你（字段顺序不限，缺 key 时你按规则自动生成）：

```
处理 D:\game\某游戏    名称：某游戏 1.0    key：mygame01
```

- `处理` 后面是**游戏安装目录**（解包工具从那里找打包文件）；
- `key` 规则：仅小写字母和数字、全库唯一、**重建同一游戏必须一致**；用户没给时，用游戏英文名小写+版本号生成（如 `eternum095`），并在报告中说明。

**方式二：批量（projects 目录）**

若本包的 `projects\` 目录下有 `*.json`，按下面格式逐个执行（对话指令优先级更高，用户明确指定时忽略 json）：

```json
{
  "name": "某游戏 1.0",
  "key": "mygame10",
  "gameDir": "D:\\game\\MyGame-1.0-pc",
  "outputDir": "D:\\game\\MyGame-1.0-pc\\CG"
}
```

`outputDir` 缺省时用 `<gameDir>\CG`。`projects\示例-项目配置.json` 是格式样例。

## 二、执行流程（严格按工作流文档走）

**唯一权威流程是《SakuraView-CG工作流.md》。** 按其 ①→⑤ 顺序执行，每完成一个阶段做一次数量核对并向用户简报。要点重申（细节以工作流文档为准）：

1. **环境自检**（首次/新机器必做）：
   - `python --version` ≥ 3.11；
   - 跑 `python selftest_extract_rpa.py` 验证提取链路；
   - ffmpeg 检测：脚本会自动找同目录的 `ffmpeg*.exe`，`gen_posters.py` 能启动即通过。
   - 环境不满足：如实告知用户需要什么（Python 3.11+ 安装包、或只浏览不重建），**不要静默降级**。
2. **识别引擎**：按工作流 §1 的特征表 + 文件头判断；认不出就按 §1 兜底顺序处理，并明确告知用户你正在用兜底方案。
   - **Unity 游戏**（存在 `xxx_Data\data.unity3d` 类结构）：用本包 `AssetStudioModCLI\AssetStudioModCLI_net472_win32_64\AssetStudioModCLI.exe <Data目录> -t texture2d -g container --image-format jpg -o <extracted>` 导出全部纹理；导出后按 §3 整理，并剔除引擎垃圾（CHAPTER/MISSION 纯编号纹理、字体 Atlas、Font Texture）。
   - **Godot 游戏**（存在 `*.pck`，文件头 `GDPC`）：用本包 `extract_pck.py <pck或目录> <输出目录> --images-only`（见工作流 §2.6）。包内 `.stex/.ctex` 由脚本自动雕刻成真实格式的图；`assets/<章>/videos/*` 是动画逐帧序列、`thumbs` 是缩略图副本，整理时按 §3 剔除。
3. **提取**：中间产物统一放 `<gameDir>\extracted\`；RPA 用 `extract_rpa.py`；ImoScripter 用 `filepack31.exe` + `dpng2png.exe`（**DPNG 必须转真 PNG，漏了全库裂图**）；日文路径一律走 Python `subprocess` 传参。
4. **整理命名**：按工作流 §3 的两级目录规范把素材归入 `<outputDir>\CG\`；保留原始文件名；剔除 UI/缩略图/差分表；**`assets\` 和 `_poster\` 是保留字**。分类命名用中文可读名（角色名/章节）。
5. **生成站点**：`python gen_site_generic.py "<outputDir>\CG" "<名称>" "<key>"`，有视频再跑 `python gen_posters.py "<outputDir>\CG"`。**有 ogv 先跑 convert_ogv.py**（webm 不用转）。
6. **验收**：逐项执行工作流 §5 的清单（用无头浏览器或直接读文件核对数量），报告逐项结果，失败项给原因和修复建议。
   - 机器可核对的部分直接跑 `python verify_libs.py <key>`：入口文件、nav 计数 vs 实际文件数、分组页引用是否 404（裂图）、视频海报帧、缩略图覆盖率，一次给结论。
7. **接入总收藏 Hub**：把 `{name, base(相对 Hub 输出目录的路径), key}` 追加到本包 `hub_libs.json` 的 libs 数组，然后重跑 `sync_pack.py`（它会自动重建 Hub）。
   用 `oneclick.py` / `一键处理.bat` 时**这一步是全自动的**：
   - ① 登记 `hub_libs.json` 并立刻重建 Hub（加 `--no-hub` 可跳过）；
   - ② 把新库写进 `libs_extra.json`，`rebuild_all.py` / `verify_libs.py` 会自动读它 —— **不需要手改 `rebuild_all.py` 的 LIBS 字典**（LIBS 只留「人工确认过的正式库」）；
   - ③ 全过程落盘到 `logs\oneclick-YYYYMMDD-HHMMSS.log`（引擎识别、每个包解出多少文件、失败项、自检结果都在里面）。

## 三、硬性约束（红线）

- **不重命名**任何提取出的原始文件（备注/收藏挂在文件名上）。
- **不改动** `assets\`、`_poster\`、`fav.html` 的存储逻辑；重建用脚本，不手改 html。
- **key 一经使用不得更改**；新游戏不得复用已有 key。
- 用户数据（收藏/备注 JSON）是唯一真相：迁移、恢复一律走收藏页的导出导入，不要手写 localStorage。
- 对外承诺前先本地验证；每步的数字（文件数、分组数）要实际统计，不要估。

## 四、汇报格式

完成后输出一份报告，包含：

```
[项目] 名称 / key / 游戏目录
[提取] 引擎识别结果；解包文件数；DPNG 转换数；视频转码数
[整理] 分类列表（分类名=文件数）；剔除项说明
[建站] 生成的分组页数；海报帧数；网页入口路径
[验收] 工作流 §5 清单逐项 ✔/✘
[待办] 未完成项与建议
```

## 五、异常处理

- 解包失败 → 按工作流 §1 兜底顺序（搜现成提取包）并明确告知；
- 压缩包损坏 → 按 §2.4 切片法评估，切片前确认有备份；
- 遇到本文件和工作流文档没覆盖的情况 → 停下来问用户，不要发明流程。
