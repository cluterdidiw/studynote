## Hive EDA Web 小工具（基于 Streamlit）

### 安装依赖

在你的 Python 环境里安装：

```bash
pip install streamlit pyhive thrift pandas plotly ydata-profiling
```

> 若你们 Hive 需要 LDAP/Kerberos，可能还需要额外依赖（如 `thrift_sasl`、Kerberos 相关包），按你们环境补齐即可。

### 启动

在该目录执行：

```bash
streamlit run hive_eda_app.py
```

### 使用方式

1. 左侧配置 Hive 连接（Host/Port/Database/Username/Auth 等）
2. 输入表名（支持 `db.table` 或仅 `table`）
3. 点击 **执行**
4. 页面会输出：
   - 字段/分区字段（来自 `DESCRIBE`）
   - 非分区表：`count(*)`
   - 分区表：按分区字段 `GROUP BY` 的计数表 + Plotly 趋势图
   - 随机抽样样本（可选生成 profiling 报告，默认最多 5 万行）

