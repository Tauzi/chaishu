# 拆书细纲生成器桌面版

一个轻量 Python 桌面程序：导入小说 TXT，自动按章节分割，调用兼容 OpenAI Chat Completions 的 API 生成拆书细纲，并在 GUI 中逐章查看结果。

## 运行

```powershell
cd chaishu_desktop
python chaishu_gui.py
```

界面中填写：

- `API Key`：你的 API Key，也可以提前设置环境变量 `OPENAI_API_KEY`；点击 `保存配置` 后下次自动填充。
- `接口地址`：默认 `https://api.openai.com/v1/chat/completions`，兼容中转或其它兼容接口。
- `模型`：默认 `gpt-4o-mini`，可手动输入，也可点击 `获取模型` 从接口读取模型列表。

## 使用流程

1. 点击 `导入TXT`。
2. 程序自动识别 `第1章`、`第一章`、`第十回` 等章节标题。
3. 程序会自动把 TXT 复制到 `data\books\书名`，无需手动选择保存位置。
4. 顶部 `书库` 下拉框可以切换已导入的书籍。
5. 点击 `开始拆书`。
6. 拆书过程中可点击 `暂停`，当前 API 请求完成后会暂停下一章；点击 `继续` 可恢复。
7. 左侧章节列表显示进度，中间逐章查看原文或生成后的拆书细纲，右侧用角色列表 + 详情卡片查看人物信息。

## 细纲编辑器

中间区域是可编辑的富文本式 Markdown 编辑器：

- `A-` / `A+`：调整细纲字体大小。
- `保存当前细纲`：把当前编辑器内容保存回对应章节 Markdown。
- `重新高亮`：按 Markdown 标题、列表、关键词重新高亮显示。
- 支持直接修改 AI 生成的细纲，未保存时右上角会显示 `未保存`。

## 窗口布局

- 首次打开默认使用更大的居中窗口。
- 关闭程序时会记录窗口大小、位置和三栏分割比例。
- 下次打开会恢复上次调整后的窗口布局。

配置会保存到项目本地数据目录：

```text
chaishu_desktop\data\config.json
```

默认保存目录规则：导入 `书名.txt` 后，程序会把原 TXT 复制到项目本地数据目录，并创建同名项目文件夹。关闭后再次打开，会自动恢复上次导入的小说、章节列表、已生成细纲和上次选中的章节。

数据目录结构：

```text
chaishu_desktop\data\
  config.json
  state.json
  books\
    书名\
      书名.txt
      characters.json
      书名拆书细纲\
        0001_第1章 xxx_拆书细纲.md
        0002_第2章 xxx_拆书细纲.md
```

## 角色记录

每章拆书完成后，程序会再调用一次 AI 更新 `characters.json`：

- `main_character`：主角详细档案，包括身份、性格、能力资源、目标、状态、出场章节。
- `main_character.relationships`：主角和其他角色的人物关系。
- `characters`：其他角色列表，包括身份、剧情功能、与主角关系、最新状态、备注。

右侧角色栏会把 `characters.json` 渲染成侧边栏：上方是可搜索角色列表，下方是自动换行的详情卡片，重启程序后会自动恢复。

## 连续上下文

为了保持前后章节一致，程序每次拆当前章节时都会带上：

- 主角档案：身份、金手指、能力资源、目标、最新状态。
- 最近章节细纲：默认带最近 2 章已生成细纲。

这样第二章以后会继承第一章已经确认的主角设定，例如“穿越者”“怪物收容监狱金手指”“已获得能力”等，不会把章节当成孤立文本。

## 文件结构

```text
chaishu_desktop\
  chaishu_gui.py   # GUI 主程序
  api.py           # API 请求、模型列表、拆书和角色更新调用
  storage.py       # 数据目录、书库、章节拆分、配置和状态保存
  prompts.py       # 拆书提示词和角色提示词
```

输出文件命名示例：

```text
书名拆书细纲\0001_第1章 xxx_拆书细纲.md
书名拆书细纲\0002_第2章 xxx_拆书细纲.md
```

## 打包 EXE

首次打包需要安装 PyInstaller：

```powershell
pip install pyinstaller
```

然后运行：

```
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

生成文件：

```text
dist\拆书细纲生成器.exe
```

## 设计取舍

- GUI 使用 Python 标准库 `tkinter`，无需 Electron，体积更小。
- API 请求使用标准库 `urllib`，不依赖 `requests`。
- 拆分为 GUI、API、存储、提示词四个轻量模块。
- 默认按章节输出三个栏目：`剧情主要内容`、`细节剧情点`、`读者看点`。
- 暂停不会中断正在进行的 API 请求，只会在当前章节完成后暂停下一章，避免丢失结果。
- 导入 TXT 和生成的细纲都保存在 `chaishu_desktop\data`，方便程序下次自动读取。
- 角色库单独保存为 `characters.json`，便于后续做人物关系图、搜索或导出。
