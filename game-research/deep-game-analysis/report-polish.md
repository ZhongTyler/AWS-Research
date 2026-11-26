# 可选报告编辑适配

[report-polish.py](report-polish.py)为深拆与专题提供离线取文、版本绑定和写回计划。它不联网、不调用模型、不自动采用报告。基础研究、Markdown 与 HTML 表达均可独立使用；本包不携带 copy-polish 执行器或在线服务。

## 配置与调用

只有宿主已安装并审阅兼容的 copy-polish 本地执行器时，才设置环境变量 AWS_RESEARCH_COPY_POLISH_DIR 指向其目录；目录应含 run.py 及其原生依赖。所选文件会作为本地 Python 代码加载，使用可信配置。适配器检查 report_payload、prepare_edit_request、report_revision 接口；实际协议仍须用当前执行器验证。联网请求另按宿主执行器合同及当前数据、次数和费用授权执行。

配置 brief 必须说明 audience、reader_outcome、report_question、覆盖全部节 ID 的 chapter_roles、comprehension_problems、factual_boundaries、allowed_moves、presentation。先理解当前完整稿及章节、图文关系，再编辑；长稿按原序连续自然章节分批，携带同一全稿身份与完整章节职责，共享文字安排明确批次。固定字段逐项校对不能证明全文理解。原生 context 上限1000字符、payload上限64 KiB由已配置执行器实际预检。

components 使用唯一 xpath 和用途 context，取可见文字及 title、aria-label、placeholder、alt；json_scripts 指定中文文案脚本；anchors 包含 id、section、before、kind 及必要的 replaces_table。renderer 明示原生成器及消费约束。导航优先读 reader/navigation.json，否则从原 HTML 的 rn-routes 取文；short_title 一同导出。在用 SVG 按同源引用筛选；unit_context、explanation_bindings、expression_plan 及各节 explanation_targets 保留在独立元数据中，不交文案编辑覆盖。

从模块根执行，输出必须是新的包外目录：

~~~text
python -X utf8 -B game-research/deep-game-analysis/report-polish.py prepare --report <报告目录> --config <业务配置.json> --output <新运行目录>
python -X utf8 -B game-research/deep-game-analysis/report-polish.py verify --run <运行目录>
python -X utf8 -B game-research/deep-game-analysis/report-polish.py plan --run <运行目录> --receipt <原生check结果.json> --output <新写回计划.json>
~~~

prepare 保存请求、payload、位置映射、保留元数据和输入身份；verify 拒绝源、配置、请求或导航形式漂移；plan 只接收同一请求的原生 pass 回执，并返回 revised_source、revised_surfaces、presentation、block_map、prose_map 及原位置。它不统一各种特殊 renderer。原适配者须消费真实拆合段落映射和图表替代关系，再重建并验收。新出图或新解释先回同源正文，已有纯文案修订保留原组件位置和交互。

## 实际调用与审订依据

宿主已配置且授权采用工具编辑流程时，完成依据包括当前稿范围的真实请求、返回、保真审核和采用回执；仅技能编辑、离线夹具或机械 PASS 不算实际 copy-polish 调用。无工具配置或授权时继续人工路径并如实说明；已选工具流程失败或 partial 保留停点，是否降级按当前宿主决定。整页审订核完整主线、章节职责、图文关系与全部自写可见文案，逐项审订核具体变更及保真，两者各自记录。

既有报告返修提供旧版、新版、逐项修改对照、旧新全文图文对照四个入口，绑定同一版本与变化清单。全文保留未改上下文及图表；标色定位实际增删字词，移位、拆合段另标结构变化。宽屏并列、窄屏顺排，核读顺序、标色与控件。逐篇确认的批次按当前用户决定等待；普通新报告沿原交付要求。

网络与原生保护错误归执行器维护；取文、组件替代和写回归 Research 适配者；机制、来源及理解问题归作者与审计。失败、离线恢复、宿主修订与正式采用保留各自身份，不把离线通过回写为在线成功。
