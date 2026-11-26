# 系统研究报告阅读页

README.md 是文字主本，reader.json 保存已审目录、领域阅读视角和原型入口。`build_reader.py` 只读这两份输入，调用已配置的 PowerShell 7 的 `ConvertFrom-Markdown` 投影正文，再复用深拆的 `reader-navigation/build.py`、`navigation.css` 与 `navigation.js`。HTML 为可重建的阅读入口。系统研究保存于接收方指定的包外案例目录。

## 配置与构建

在案例目录写 `reader.json`，以下为最小示例。`sections` 按原顺序覆盖 README 的全部二级标题，`heading` 与 Markdown 中的标题文字精确对应，`id` 稳定保存。

```json
{
  "schema": 1,
  "report_id": "sr-example",
  "title": "某游戏的完整系统研究",
  "source": "README.md",
  "output": "reader/index.html",
  "sections": [
    {"id": "objects", "heading": "一、管理对象"},
    {"id": "operations", "heading": "二、操作与反馈"}
  ],
  "toc_groups": [
    {"title": "认识与操作", "sections": ["objects", "operations"]}
  ],
  "routes": [],
  "prototype": {"path": "playable/lab.html", "label": "打开可运行原型"}
}
```

`toc_groups` 按内容复杂度选层级，并完整、依次覆盖各节一次。可省略分组配置，生成单层目录。领域有实际阅读增量时才添加 `routes`，每条使用以下结构。`intro` 写这个领域从全系统应读懂的内容，`focus` 针对该领域与当前小节具体说明关注点。正文标题作为步骤标题，来源与哈希由构建器生成。

```json
{
  "id": "interaction",
  "name": "交互策划",
  "intro": "从对象选择读到提交结果，观察信息何时出现，以及取消后怎样继续。",
  "steps": [
    {"target": "operations", "focus": "对照选中、确认、取消三个时刻，检查对象、资源与焦点分别怎样变化。"}
  ]
}
```

在模块根目录，使用已有含 lxml 的 Python 运行。

```powershell
python -X utf8 -B game-research/system-research/build_reader.py <包外案例目录>
```

PowerShell 7 未在 PATH 时通过 `--powershell` 指定现有 `pwsh.exe`。构建只写案例的 `reader/index.html` 和 `reader/build-receipt.json`。转换器保留 Markdown 表格、列表、代码和现有图片，将相对资源链接按输出位置换算。报告目录与其引用资源一起交付，原型仍从原 `playable/` 运行。正文、配置或引用缺失时应先修复输入再生成。构建回执绑定源稿、配置、输出、原型入口及生成器版本，图文语义与实际行为沿独立审计核对。

## 原型浮层与消息协议

报告的“打开可运行原型”按钮呼出模态浮层。iframe 首次打开时装载，关闭后保留同一实例、运行状态与 src。再次打开继续原状态。关闭按钮独立可用，关闭后焦点回到触发按钮，保留阅读位置。浮层使用浏览器原生 dialog，报告在浮层背后进入不可操作状态。

iframe 键盘事件在各自窗口处理，原型及中间工作台负责桥接 Esc。游戏优先消费自己的教程、弹层等内部返回动作，随后才请求关闭报告浮层。

| 方向 | 消息 | 处理 |
|---|---|---|
| 原型工作台 → 报告 | `{type:"research-reader:escape-request"}` | 报告启动一次 Esc 握手。 |
| 报告 → 原型工作台 | `{type:"research-reader:escape",token:正整数}` | 工作台询问或关闭游戏内优先弹层。 |
| 原型工作台 → 报告 | `{type:"research-reader:escape-result",token:同值,consumed:true}` | 游戏已消费 Esc，浮层保持。 |
| 原型工作台 → 报告 | `{type:"research-reader:escape-result",token:同值,consumed:false}` | 当前无游戏内优先返回，关闭浮层。 |

双方只接受已绑定对方窗口的消息。HTTP 下同时校验同源，file 下也核对 `event.source`。工作台含游戏 iframe 时，同样核对内层来源，并将响应关联到原请求。报告只在对应 token 且 `consumed` 明确为 false 时关层。无响应时提示使用关闭按钮。游戏输入保留在原型窗口，报告导航在浮层打开时不能响应游戏按键。

## 审订与交付

按[编辑与回执合同](../deep-game-analysis/report-polish.md)处理当前完整稿、目录、领域导读、控件及辅助阅读文案。已配置且有当前数据、次数和费用授权时，实际调用可选 copy-polish 服务并保留请求、响应、用量、保真审查及采用范围。未配置或未授权时继续人工编辑和基础研究，明确没有工具调用回执；失败、部分返回与人工处理分别记录。安装不提供在线模型服务或授权。

作者核对 README 字节、全部章节、表格图片、领域每步与正文关系。实际浏览器按改动范围检查宽窄屏、图片、导航、浮层反复开关、内外 Esc、焦点归还、阅读位置、运行状态和输入隔离。改原型桥接时复验受影响规则和输入。生成器测试验证机械转换与失败保护，不能代替这些实际检查。

~~~text
python -X utf8 -B -m unittest discover -s game-research/system-research -p test_reader.py -v
~~~

构建器需要 Python 3.10+、lxml 和 PowerShell 7 的 ConvertFrom-Markdown；未安装时可直接交付 Markdown 主本和独立原型。新建输出位于案例目录；把报告目录及声明资源一起交付。报告 HTML 与原型入口必须是可信且已审核的本地内容，iframe 不是对不可信游戏的隔离执行环境。
