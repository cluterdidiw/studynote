# 计量经济学实战项目

在 Jupyter Lab 中手工操作的计量经济学练习与实战项目。本仓库用于配合 Cursor 等 AI 辅助编写和修改 Python 脚本与 notebook。

## 目录结构

```
计量经济学实战/
├── README.md          # 本说明
├── code/              # 所有 .ipynb 与 .py 脚本
└── data/              # 数据文件或数据说明（按需放置）
```

## 使用方式

- **环境**：使用 studynote 根目录的 `environment.yml`（conda 环境 `py311`），已包含 `pandas`、`numpy`、`statsmodels`、`wooldridge` 等。
- **运行**：在 Jupyter Lab 中打开 `code/` 下的 notebook，按单元格手工执行。
- **辅助**：需要写或改某段 Python 代码时，在 Cursor 中描述需求（例如「用 OLS 做工资对教育年限的回归并输出系数和 R²」），由 AI 生成或修改对应代码，你再复制到 notebook 中运行。

## 与 AI 协作写脚本的提示

- 说明**目标**：要做哪类分析（回归、检验、画图等）。
- 说明**数据**：变量名、是否已有 DataFrame、在哪个 notebook 里。
- 说明**输出**：需要表格、图形还是只打印结果。
- 可以贴出当前单元格的代码片段，让 AI 基于现有代码做修改或扩展。

## 可扩展内容

- 横截面：简单/多元 OLS、异方差、内生性初探。
- 时间序列：平稳性、AR/ARIMA、协整。
- 面板数据：固定效应、随机效应（若后续引入相应库）。

按需在 `code/` 下新建 notebook 或 Python 脚本即可。
