# 四人连续对话意图识别评测

这是一个可以单独复制运行的 OpenAI SDK 评测工具，不依赖 ROS、工作区环境或项目应用代码。

## 项目结构

项目自带 `datasets/conversation.jsonl`、`datasets/intent_300.jsonl` 和 `datasets/intent_600.jsonl`。每个文件都是一段连续对话；人类发言用于意图识别，紧邻 addressing case 的机器人发言作为回复标准答案。参与者、机器人名称、样本数量和标签分布均在运行时从所选数据集读取。

| 目录或文件 | 用途 |
| --- | --- |
| `evaluate.py` | 唯一命令行入口：校验、运行、计分、报告服务 |
| `config/` | 被测模型配置；旧裁判配置仅用于读取历史批次 |
| `prompts/` | 意图识别和回复生成提示词 |
| `evaluation/` | 意图流水线、输出解析、回复生成与结果比较 |
| `reporting/` | 意图报告、回复报告、静态页面生成和 HTTP 服务 |
| `hotel_tools/` | function calling schema 与无副作用酒店伪工具 |
| `tests/` | 单元测试和离线集成测试 |
| `datasets/` | 对话数据集与标准答案 |
| `results/` | 每次运行生成的原始报告批次 |
| `templates/` | 六个静态报告页面 |
| `requirements.txt` | 运行依赖 |

## 安装与运行

Python 3.10+，在本目录运行，不需要激活开发容器：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

# 默认流水线模式：每条 case 先识别意图，addressing 时再生成并判断回复
python evaluate.py run --rounds 3

# --model 可重复，也可以填写服务端模型 ID
python evaluate.py run --model qwen38_27b --rounds 3

# 单独执行意图识别
python evaluate.py run --task intent --model qwen38_27b --rounds 3

# 意图识别使用自己的模型列表或提示词
python evaluate.py run --task intent --config my_models.json --prompt prompts/intent_classification.md --rounds 5

# 流水线冒烟测试：只跑前 3 条人类 case
python evaluate.py run --limit 3 --rounds 2

# 切换到其他数据集
python evaluate.py validate --dataset datasets/intent_300.jsonl
python evaluate.py run --dataset datasets/intent_300.jsonl --limit 3
python evaluate.py run --task intent --dataset datasets/intent_600.jsonl --rounds 1

# 流水线模式：使用前 3 条人类 case 做冒烟测试
python evaluate.py run --dataset datasets/intent_300.jsonl --limit 3

# 完整运行流水线
python evaluate.py run --dataset datasets/intent_300.jsonl --rounds 1
```

`--dataset` 接受与 `datasets/conversation.jsonl` 相同字段结构的 JSONL 文件。参与者、机器人名称、会话 ID、发言数量和标签分布均从所选数据集动态读取；每次结果按数据集 SHA-256 分组，不会与其他数据集混合统计。`validate`、`run` 和 `score` 都支持该参数。

`run` 不带 `--task` 时使用逐 case 流水线：每条人类发言先进行意图识别；预测为 `ignore` 时记录意图结果并直接进入下一条；预测为 `addressing` 且数据集为该 case 提供了紧邻的机器人标准回复时，再调用被测模型生成正式回复并判断正确性。两阶段原始数据保存在同一条 case 记录和同一个 `results/<批次>/details.json` 中，意图页面与结果页面分别读取各自指标。漏判为 `ignore` 的 addressing case 不生成回复，并在结果指标中记为未覆盖/失败；误判为 addressing 但没有标准回复的 case 记录为无参考答案，不计入回复准确率。明确增加 `--task intent` 时只执行意图识别，不生成回复。结果判断完全使用本地确定性规则：方法调用必须来自原生 `tool_calls`，参数按 schema、枚举、类型和标准答案校验；自然语言参数与普通文本按关键词包含情况校验，不调用裁判模型。

结果判断使用独立文件：

| 文件 | 用途 |
| --- | --- |
| `prompts/response_generation.md` | 待测模型生成回复的 system 提示词 |
| `evaluation/local_result_validator.py` | 原生工具调用、JSON 参数和文本关键词本地校验 |
| `evaluation/response_runner.py` | 回复模型调用与原生 tool call 解析 |
| `reporting/response_reports.py` | 结果判断汇总、单次运行与明细报告 |
| `hotel_tools/mock_functions.py` | function calling schema 与本地无副作用伪工具 |
| `scripts/reevaluate_results.py` | 不调用模型，对已有批次执行离线本地重评 |

### 本地 function calling 伪工具

`hotel_tools/mock_functions.py` 覆盖数据集标准答案中的全部 12 个 `methed`。`TOOL_DEFINITIONS` 可直接作为 OpenAI 兼容 Chat Completions 请求的 `tools` 参数；模型返回函数名和参数后，使用 `dispatch_methed` 进行本地校验与模拟执行，不会操作真实酒店系统：

```python
from hotel_tools.mock_functions import TOOL_DEFINITIONS, dataset_result, dispatch_methed

response = client.chat.completions.create(
    model="your-model",
    messages=messages,
    tools=TOOL_DEFINITIONS,
    tool_choice="auto",
)

call = response.choices[0].message.tool_calls[0]
arguments = json.loads(call.function.arguments)
simulated = dispatch_methed(call.function.name, arguments)

# 转成当前数据集真值使用的 {"methed": ..., "parameters": ...} 格式
candidate = dataset_result(call.function.name, arguments)
```

默认评测流水线已经接入这些定义：回复标准答案为 `methed` JSON 时，模型必须返回一个原生 `tool_calls` 函数调用。函数名不存在、参数不是合法 JSON、字段缺失/多余、类型错误或返回多个调用都会直接判为模型调用失败；普通文本标准答案仍允许直接返回文本。

默认每轮包含相同的 150 条人类发言，每个模型独立运行，不使用上次模型的输出作为下次的历史，也不把前一轮对话重复累加到下一轮。默认 `--rounds 1`。每次执行创建新的结果目录，历史结果保留；只保存 `results/<批次>/details.json` 原始记录，不提前生成统计报告。页面每次刷新时读取当前原始记录并在内存中统计。同一个服务端模型 ID 与同一个数据集 SHA-256 的结果合并在一张表中，测试次数跨命令累计；原始运行批次、配置名称和局部轮次保留在明细数据中。

首次使用时复制安全模板：

```bash
cp config/model_profiles.example.json config/model_profiles.json
```

真实的 `config/model_profiles.json` 已被 `.gitignore` 排除，不会提交 API Key；`config/model_profiles.example.json` 不含密钥，用于共享配置结构。有鉴权的接口请设置模型配置中 `api_key_env` 指定的环境变量，例如 `OPENAI_API_KEY`。该环境变量优先于配置中的 `api_key`。无鉴权的本地或兼容服务可以将 `api_key` 留空；需要真实密钥的服务应通过环境变量提供。

## 配置不同模型

在 `config/model_profiles.json` 的 `models` 数组中添加配置，例如：

```json
{
  "models": [
    {
      "name": "model_a",
      "model": "server-model-id-a",
      "base_url": "http://localhost:8000/v1",
      "api_key_env": "MODEL_A_API_KEY",
      "timeout_seconds": 60,
      "request_options": {"max_completion_tokens": 128}
    },
    {
      "name": "model_b",
      "model": "server-model-id-b",
      "base_url": "https://your-endpoint.example/v1",
      "api_key_env": "MODEL_B_API_KEY",
      "request_options": {"temperature": 0.2}
    }
  ]
}
```

- `name` 是不能重复的配置名称；`model` 是服务端实际使用的模型 ID。
- `request_options` 直接使用 SDK 的 Chat Completions 参数，例如 `temperature`、`top_p`、`seed`、`max_completion_tokens`。参数是否适用由目标模型接口决定。运行工具管理 `model / messages / stream`。
- 非标准的兼容接口扩展放在 `extra_body`，不支持扩展的服务可省略该项。默认 Qwen 示例用此项关闭 thinking。
- 默认示例限制 `max_completion_tokens=128`，每次只输出当前句的一个分类。完整参数会保留在报告中；需要 reasoning token 的模型应相应调整。旧批次的参数保留在原始 request 中，不追溯改写。
- 每条测试只请求一次，评测器和 SDK 均不重试。网络失败、超时、返回格式错误直接计错；有效分类与参考标签不同也直接计错。`max_retries` 配置只兼容省略或 0，非零值会报配置错误。历史报告仍保留当时发生的重试及实际消耗。

## 两类评测与六个静态页面

意图识别页面为 `summary.html`、`runs.html`、`details.html`；结果判断页面为 `result_summary.html`、`result_runs.html`、`result_details.html`。六个页面固定保存在 `robot_addressing_v1/templates/`，并在同一顶部导航中同级展示。HTML 不内嵌测试数据，打开或刷新时通过 HTTP 接口实时计算当前结果目录中的报告。

在本目录启动查看服务：

```bash
python3 evaluate.py serve
# 打开 http://127.0.0.1:8786/templates/summary.html
# 单次运行对比 http://127.0.0.1:8786/templates/runs.html
# 明细 http://127.0.0.1:8786/templates/details.html
# 结果判断汇总 http://127.0.0.1:8786/templates/result_summary.html
# 结果判断单次运行 http://127.0.0.1:8786/templates/result_runs.html
# 结果判断明细 http://127.0.0.1:8786/templates/result_details.html
# 可用 --port 修改端口，Ctrl+C 停止服务
```

该服务提供两个静态页面，并在每次页面读取时扫描当前测试目录、在内存中计算汇总和明细 JSON，不需要安装 Web 框架、前端依赖或构建工具。浏览器的 `file://` 限制会阻止 fetch 读取本地 JSON，因此请使用上面的 HTTP 地址。服务默认只监听本机。增加或删除测试目录后，刷新页面即可按当前目录重新计算次数和准确率。删除全部测试后显示 0 次及空表，不沿用旧合并文件。请使用 `python evaluate.py serve`；通用静态文件服务不提供实时统计接口。


每次运行在 `results/<北京时间>/` 下只保存一份 `details.json` 原始记录，例如 `20261105T130944297509`。其中 `details.json` 包含模型配置、提示词摘要、每轮/每次调用的时间、目标标签、预测结果、完整 request、response、usage 和错误。每条完成后立即保存，中断时保留已经产生的记录。不会提前生成 `summary.json`、合并明细或 HTML 报告。

页面刷新时重新读取这些记录、计算测试总次数和准确率，响应数据仅存在于内存，不写回 `results/`。

具体测试的默认序号按开始时间从早到晚排列，最早为第 1 轮。新记录使用每轮的开始时间，因此两个命令交错执行时也能按实际时间排序；旧记录缺少每轮时间时，按批次开始时间和原轮次排序。汇总表的“轮次”仍表示测试总次数，明细页的第 1/2/3 轮用于定位单次测试。

汇总页面按“服务端模型 ID + 数据集 SHA-256”分组，每组只有一张按目标话语合并的结果表。同一句不论测了多少次都只显示一行，“轮次”表示这句话总共测试了多少次。例如：

```bash
python evaluate.py run --task intent --model qwen38_27b --rounds 3
python evaluate.py run --task intent --model qwen38_27b --rounds 3
```

两次命令各运行 3 轮后，每句话累计测试 6 次。汇总表仍为 150 行，各行“轮次”为 6 次，“意图识别准确率”为该句话 6 次中正确的次数除以 6（例如 4/6 = 66.67%）。900 条原始测试结果保存在各批次的 `details.json`，不会在汇总表中重复列成 900 行。

汇总表列为：

| 对话 ID | 轮次 | 目标话语 | 输入 token | 输出 token | 总 token | 累计输入（含重试） | 意图识别准确率 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| u001 | 6 次 | 小露小露，你好…… | 6 次输入之和 | 6 次输出之和 | 6 次总量之和 | 所有调用累计 | 66.67% · 4/6 |

输入、输出、总 token 为这句话所有次测试的已记录单次 usage 累加；存在缺失 usage 时保持未知，不以 0 代替。“累计输入（含重试）”额外包含旧批次的重试消耗，重试不增加测试次数。

可以按模型、数据集、正确/错误/失败和发言内容筛选。点击对话 ID 查看这句话的历次结果，再选择某次查看完整 request、响应和 usage。错误、失败和带历史评测问题标记的报告均按已保存的原始结果纳入分母，标记和原始记录保留；汇总不再自动隐藏目录中的某一份报告。

测试次数只计实际产生的逐句记录，尚未执行的目标不增加分母。`source_run_id / source_round / source_profile` 保留每一次测试的来源；原始批次文件不改写。

明细页的逐句表格包括：

| 对话 ID | 目标话语 | 参考标签 | 模型预测 | 输入/输出/总 token | 识别结果 | 本次调用详情 |
| --- | --- | --- | --- | --- | --- | --- |
| u001 | 小露小露，你好…… | addressing | addressing | 接口实际 usage | 正确 | 查看 request |

这里的“对话 ID”是每句发言的编号（u001–u200），完整会话 ID 是 `hotel_day_001`。汇总页的“轮次”是这句话累计测试的总次数；明细页的测试序号用于定位具体哪一次。总体准确率、各次测试统计和 F1 仍可展开查看。

request 捕获的是 OpenAI SDK 实际构造并提交给 HTTP 客户端的 JSON 参数，包含合并后的 `extra_body`，不是事后推测的请求。记录 POST 地址和完整 JSON body，不写入鉴权 HTTP 头。

明细报告中每次测试的 `input_tokens / output_tokens / total_tokens` 分别对应最后一次调用的 `CompletionUsage.prompt_tokens / completion_tokens / total_tokens`。汇总报告中的同名字段为该句话所有次测试的上述用量之和。明细页切换 HTTP 尝试时，这三个值随当前选中的原始 usage 一起切换。`known_input_tokens / known_output_tokens / known_total_tokens` 才是所有尝试的累计消耗，单独展示。无 usage 的单次调用标为“未知”；累计量显示已知下限及缺失次数，不按文本长度估算。

可用 `--results-directory /path/to/results` 修改结果父目录。如果报告目录位于静态服务目录下，例如 `my_results/`，页面用 `summary.html?results=my_results` 或 `details.html?results=my_results` 读取对应的汇总 JSON；服务根目录外的报告需要在能够访问该目录的静态服务下查看。

## 历史报告与完整指标

意图识别指标的审核口径、公式、混淆计数和完整示例见 [REPORT_METRICS_GUIDE.md](REPORT_METRICS_GUIDE.md)。

日常查看入口包括意图识别的 `templates/summary.html`、`templates/runs.html`、`templates/details.html`，以及结果判断的 `templates/result_summary.html`、`templates/result_runs.html`、`templates/result_details.html`。每次打开或刷新页面时重新计算，没有预先生成的汇总文件。以下命令只显示页面入口，不写统计报告：

```bash
python evaluate.py report

# 离线复核旧脚本误判的完整批量输出，并从已保存 usage 修正 token 显示
python evaluate.py report --audit-saved
```

`--audit-saved` 保留原始 request、response、usage 和修正前的计分，只有在捕获的 unclassified 文本和全部有序输出可以逐条对应时才修正误判。原先只有 index 0 的成功输出沿用旧版目标句协议；缺少完整 request 的旧报告保留原有分数。复核并不重新调用模型，也不把旧批次标成新版协议的新测试。

历史汇总默认读取 `results/` 中全部批次，再按模型、数据集和目标话语合并，累计测试次数与正确次数，支持定位每轮、每句的 request。`python evaluate.py report --complete-only` 则仅将完成批次加入汇总。不同计分标准通过页面参数选择，例如 `summary.html?label_key=policy_intent`，或使用 `python evaluate.py report --label-key policy_intent` 查看对应入口。

旧版目录含 `run.json`、`predictions.jsonl`、`intent_report.json` / `policy_intent_report.json` 时，可导入：

```bash
python evaluate.py report --import-legacy /path/to/old-run
```

导入会在 `results/legacy_<旧批次>_<计分标准>/` 建立新格式的报告副本，保存转换后的原始记录，原目录保持不变。会校验数据集 SHA-256，并逐项核对旧报告的准确率、precision、recall、F1、覆盖率、误接话率和混淆计数。原有报告内容也保留在 `source_statistics` 中。

**旧报告没有采集的完整 request、完整 SDK response 或 token usage 会明确标记为“未记录”，不会从当前配置反推或用 0 token 代替。** 原有输出文本仍可在明细页查看。导入和汇总功能只使用 Python 标准库，不需要 API 密钥或 OpenAI SDK。

## 提示词与计分标准

`prompts/intent_classification.md` 是独立提示词快照，包含身份、对话格式、意图判断、静默/重新呼叫和输出格式规则。运行时只替换 `{{robot_name}}` 和 `{{robot_name_aliases}}` 两个占位符，不读取外部提示词。每次提交当前句之前的完整对话作为上下文，历史人类发言附上数据集已有的标签（如 `……（addressing）` 或 `……（ignore）`），但不提交“谁谁谁说”之类的说话者前缀；机器人回复作为 assistant 上下文。只把当前句标记为 `unclassified`，附上 `utterance_index: 0`，只要求返回 `0:addressing` 或 `0:ignore`。当前句的参考答案和未来发言不进入请求。

例如测试第 10 条人类发言时，前 9 条人类发言带数据集标签作为历史，本次只验证第 10 条。每轮 150 次请求，总共请求 150 个分类，不重复分类历史。历史标签使用 `--label-key` 所选字段，与本轮计分字段一致；前一句预测错误也不会污染后一句的上下文，更不会触发重试。

- `is_to_robot / intent`：是否对机器人说；默认使用 `intent` 计分。
- `policy_intent`：按项目原有静默规则应输出的分类。提示词快照保留此规则，可使用 `--label-key policy_intent` 计分。
- 两种标签仅在 `u146` 不同：这句确实对机器人说，但当时未通过名字解除静默。
- `addressees / tag / reason / section`：仅供复核，不提交给模型。
- 模型调用失败、解析失败均直接计错，不重试；报告同时保留原始错误与 usage 缺失状态。

```bash
python evaluate.py validate
python evaluate.py run --task intent --rounds 3 --label-key policy_intent

# 仍支持给已有预测文件单独计分
python evaluate.py score /path/to/predictions.jsonl

# 离线验证：实际 SDK + 本地 HTTP fixture，不调用外部模型
python -m unittest discover -s tests -p 'test_*.py' -v
```

每次报告都记录数据集与渲染后提示词的 SHA-256、模型 ID、各次请求参数、计分标准和测试轮数。中断时保留已完成部分并标记为未完整结束。修改数据可直接编辑 `datasets/conversation.jsonl` 后校验。本数据是单一酒店场景的人工合成文本回归测试，不代表真实开放场景的总体准确率。
