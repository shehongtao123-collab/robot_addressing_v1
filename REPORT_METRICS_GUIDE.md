# 意图识别评测指标说明

本文档说明 Robot Addressing 项目意图识别报告中的指标定义、计算公式和审核口径。指标实现以 [`evaluate.py`](evaluate.py) 中的 `metrics()` 函数为准。

## 1. 评测目标

项目对每条需要评测的人类发言进行二分类：

- `addressing`：这句话是对机器人说的，属于正类（Positive）。
- `ignore`：这句话不是对机器人说的，属于负类（Negative）。

默认使用数据集的 `intent` 字段作为标准标签。使用 `--label-key policy_intent` 时，计算方法不变，只是标准标签改为 `policy_intent`。

在汇总历史批次或多轮测试时，每次实际评测都独立计数。例如同一条用例运行 3 轮，就会贡献 3 个样本，而不是只计算一次。

## 2. 基础计数

| 计数 | 标准标签 | 模型分类 | 项目中的含义 |
| --- | --- | --- | --- |
| TP（True Positive） | `addressing` | `addressing` | 应该响应机器人，模型也正确识别为应该响应 |
| TN（True Negative） | `ignore` | `ignore` | 不应该响应机器人，模型正确保持沉默 |
| FP（False Positive） | `ignore` | `addressing` | 误接话：本不应响应，但模型认为应该响应 |
| FN（False Negative） | `addressing` | `ignore` | 漏识别：本应响应，但模型认为应该忽略 |
| Missing Positive | `addressing` | 无有效分类 | 正类调用失败、格式错误或漏答 |
| Missing Negative | `ignore` | 无有效分类 | 负类调用失败、格式错误或漏答 |

其中：

```text
总样本数 N = TP + TN + FP + FN + Missing Positive + Missing Negative
```

“无有效分类”表示最终没有得到合法的 `addressing` 或 `ignore`，常见原因包括：

- HTTP 请求失败、超时或服务端异常；
- 模型没有返回文本；
- 返回格式无法解析；
- 返回了协议以外的分类；
- 请求被中断或结果缺失。

## 3. 总体准确率（Accuracy）

总体准确率表示全部测试中，被正确分类的比例。

```text
Accuracy = (TP + TN) / N
```

调用失败和漏答包含在 `N` 中，但不计入正确数量，因此会降低总体准确率。

例如总共测试 100 次，其中 TP=18、TN=72、FP=4、FN=3、失败/漏答=3：

```text
Accuracy = (18 + 72) / 100 = 90%
```

### 适合回答的问题

> 在所有评测请求中，模型最终正确处理了多少比例？

### 审核注意事项

当数据集中 `ignore` 占比很高时，只看 Accuracy 可能会掩盖正类识别能力。例如模型始终返回 `ignore`，仍可能获得较高准确率，因此必须结合 Recall、Precision 和 F1 一起审核。

## 4. Precision（精确率）

Precision 表示模型判定为 `addressing` 的样本中，真正属于 `addressing` 的比例。

```text
Precision = TP / (TP + FP)
```

例如模型一共触发响应 22 次，其中 18 次正确、4 次误接话：

```text
Precision = 18 / (18 + 4) ≈ 81.82%
```

### 适合回答的问题

> 机器人决定接话时，有多大概率确实应该接话？

Precision 越低，说明误接话越严重。对于多人交谈场景，Precision 通常非常重要，因为机器人频繁插话会直接影响体验。

### 特殊情况

如果模型一次 `addressing` 都没有预测，即 `TP + FP = 0`，本项目将 Precision 记为 `0`，而不是空值。

## 5. Recall（召回率）

Recall 表示所有真正应该由机器人响应的样本中，模型成功识别出来的比例。

本项目将正类调用失败和正类漏答计入 Recall 分母：

```text
Recall = TP / (TP + FN + Missing Positive)
```

例如标准答案中共有 23 条 `addressing`：18 条识别正确、3 条误判为 `ignore`、2 条没有有效分类：

```text
Recall = 18 / (18 + 3 + 2) ≈ 78.26%
```

### 适合回答的问题

> 用户确实在对机器人说话时，机器人有多大概率成功识别？

Recall 越低，说明机器人越容易漏掉用户请求。

### 特殊情况

如果当前统计分组中没有任何正类样本，本项目将 Recall 记为 `0`。

## 6. F1

F1 是 Precision 和 Recall 的调和平均，用于同时衡量误接话与漏识别。

```text
F1 = 2 × Precision × Recall / (Precision + Recall)
```

使用前面的示例：

```text
Precision ≈ 81.82%
Recall    ≈ 78.26%

F1 ≈ 2 × 0.8182 × 0.7826 / (0.8182 + 0.7826)
   ≈ 80.00%
```

F1 只有在 Precision 和 Recall 都较高时才会较高。它不会把 TN 纳入公式，因此比 Accuracy 更能反映 `addressing` 正类的识别质量。

如果 Precision 和 Recall 都为 0，本项目将 F1 记为 0。

## 7. 调用失败 / 漏答

网页上的“调用失败 / 漏答”对应：

```text
Missing = Missing Positive + Missing Negative
```

它统计没有产生合法最终分类的请求数量，不是百分比，也不等于 FN。

区别如下：

- FN：模型成功返回了合法分类，但把 `addressing` 错判为 `ignore`。
- Missing Positive：标准答案是 `addressing`，但调用失败或没有解析出合法分类。
- Missing Negative：标准答案是 `ignore`，但调用失败或没有解析出合法分类。

失败/漏答的影响：

- 计入总样本数；
- 不计入正确样本；
- Missing Positive 进入 Recall 分母；
- 不进入 `TP + FP`，因此不会直接进入 Precision 分母；
- 会通过 Recall 间接降低 F1。

## 8. 完整计算示例

假设一轮共测试 100 条：

| 计数 | 数量 |
| --- | ---: |
| TP | 18 |
| TN | 72 |
| FP | 4 |
| FN | 3 |
| Missing Positive | 2 |
| Missing Negative | 1 |
| 合计 | 100 |

计算结果：

```text
Accuracy  = (18 + 72) / 100
          = 90.00%

Precision = 18 / (18 + 4)
          ≈ 81.82%

Recall    = 18 / (18 + 3 + 2)
          ≈ 78.26%

F1        = 2 × 0.8182 × 0.7826 / (0.8182 + 0.7826)
          ≈ 80.00%

调用失败 / 漏答 = 2 + 1
                  = 3 次
```

## 9. 分组指标

报告中的 H1、H2、H3 和场景类型采用完全相同的公式，只是先筛选样本再计算：

- H1/H2/H3：按 `speaker_id` 分组，观察不同说话人的识别效果；
- 场景类型：按数据集 `tag` 分组，观察直接呼叫、上下文记忆、闲聊干扰等场景的效果；
- 各轮统计：只使用该轮数据；
- 总体统计：使用当前模型、数据集和筛选范围内的全部轮次数据。

小分组样本量较少时，百分比波动会很大。审核时应同时查看“样本数”和指标值，避免只比较百分比。

## 10. 推荐审核顺序

1. 检查“调用失败 / 漏答”是否为 0；如果不为 0，先查看接口与格式问题。
2. 查看 Accuracy，确认整体正确率。
3. 查看 Recall，确认用户直接呼叫机器人时是否容易漏识别。
4. 查看 Precision，确认机器人是否容易误接话。
5. 使用 F1 比较 Precision 与 Recall 的综合平衡。
6. 展开混淆计数，确认指标变化来自 FP、FN 还是失败/漏答。
7. 检查 H1/H2/H3 和各场景分组，排查整体指标掩盖的局部问题。
8. 对比各轮结果，判断错误是否稳定复现。

## 11. 审核口径说明

- `addressing` 固定为正类，`ignore` 固定为负类。
- 每轮、每条实际请求均独立计入分母。
- 调用失败和格式解析失败按错误处理，不从 Accuracy 分母排除。
- Precision、Recall、F1 均采用项目代码中的直接计算结果，不使用宏平均或加权平均。
- 分组指标是各组独立重新计算，不是总体指标按样本数简单拆分。
- 历史汇总按照模型 ID 和数据集 SHA-256 分组，不同数据集不会混在同一指标组中。
- 本项目数据是酒店多人对话场景的回归测试数据，指标只代表当前数据集与测试配置，不应直接解释为开放环境中的真实准确率。

## 12. 代码依据

核心实现位于：

- [`evaluate.py`](evaluate.py)：`metrics()` 负责计算混淆计数、Accuracy、Precision、Recall、F1 和失败/漏答。
- [`reporting/intent_reports.py`](reporting/intent_reports.py)：负责按模型、轮次、说话人和场景类型进行聚合。
- [`reporting/page_generator.py`](reporting/page_generator.py)：负责在网页中展示指标。

