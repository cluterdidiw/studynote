import datetime as dt
import io
import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    from pyhive import hive
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "缺少依赖：pyhive。请先安装：pip install pyhive thrift"
    ) from e

try:
    from ydata_profiling import ProfileReport
except Exception:
    ProfileReport = None  # type: ignore


@dataclass
class HiveConfig:
    host: str
    port: int = 10000
    username: str = ""
    password: str = ""
    database: str = "default"
    auth: str = "NONE"  # NONE / LDAP / KERBEROS ...


def normalize_table_name(table_name: str, default_db: str) -> str:
    t = (table_name or "").strip()
    if not t:
        raise ValueError("表名不能为空")
    return t if "." in t else f"{default_db}.{t}"


def strip_table_prefix_and_dedupe_columns(cols: List[str]) -> List[str]:
    base = [str(c).split(".")[-1] for c in cols]
    seen: Dict[str, int] = {}
    out: List[str] = []
    for c in base:
        n = seen.get(c, 0) + 1
        seen[c] = n
        out.append(c if n == 1 else f"{c}__{n}")
    return out


def normalize_df_columns(df: pd.DataFrame) -> pd.DataFrame:
    new_cols = strip_table_prefix_and_dedupe_columns(list(df.columns))
    if list(df.columns) == new_cols:
        return df
    df = df.copy()
    df.columns = new_cols
    return df


def _sql_quote(v) -> str:
    return "'" + str(v).replace("'", "''") + "'"


@st.cache_resource(show_spinner=False)
def get_connection(cfg: HiveConfig):
    kwargs = {
        "host": cfg.host,
        "port": cfg.port,
        "database": cfg.database,
        "auth": cfg.auth,
    }
    if cfg.username:
        kwargs["username"] = cfg.username
    # 部分环境（如 LDAP）需要 password；pyhive 是否支持与版本有关，这里尽量兼容
    if cfg.password:
        kwargs["password"] = cfg.password
    return hive.Connection(**kwargs)


def hive_query(cfg: HiveConfig, sql: str) -> pd.DataFrame:
    conn = get_connection(cfg)
    cur = conn.cursor()
    cur.execute(sql)
    cols = [d[0] for d in cur.description] if cur.description else []
    rows = cur.fetchall()
    cur.close()
    return pd.DataFrame(rows, columns=cols)


def get_table_schema(cfg: HiveConfig, full_table: str) -> Dict[str, pd.DataFrame]:
    df = hive_query(cfg, f"DESCRIBE {full_table}")
    if df.shape[1] == 0:
        return {"data_cols": pd.DataFrame(), "partition_cols": pd.DataFrame()}

    c0 = df.columns[0]
    c1 = df.columns[1] if df.shape[1] > 1 else df.columns[0]
    tmp = df[[c0, c1]].fillna("").astype(str)

    data_rows = []
    part_rows = []
    in_part = False

    for _, r in tmp.iterrows():
        name = str(r.iloc[0]).strip()
        dtype = str(r.iloc[1]).strip()

        if not name:
            continue
        if name.startswith("# Partition Information"):
            in_part = True
            continue
        if name.startswith("#"):
            continue

        if in_part:
            part_rows.append({"col_name": name, "data_type": dtype})
        else:
            data_rows.append({"col_name": name, "data_type": dtype})

    return {
        "data_cols": pd.DataFrame(data_rows),
        "partition_cols": pd.DataFrame(part_rows),
    }


def is_partitioned(schema: Dict[str, pd.DataFrame]) -> bool:
    part_cols = schema.get("partition_cols")
    return bool(part_cols is not None and len(part_cols) > 0)


def build_sampling_sql(
    full_table: str,
    sampling_rate: float,
    seed: int,
    extra_where: str = "",
    columns: str = "*",
    limit: Optional[int] = None,
) -> str:
    if sampling_rate <= 0 or sampling_rate > 1:
        raise ValueError("sampling_rate 需要在 (0,1] 范围")
    conds = []
    if extra_where and extra_where.strip():
        conds.append(f"({extra_where})")
    conds.append(f"rand({int(seed)}) < {float(sampling_rate)}")
    where_sql = " WHERE " + " AND ".join(conds) if conds else ""
    limit_sql = f" LIMIT {int(limit)}" if limit is not None else ""
    return f"SELECT {columns} FROM {full_table}{where_sql}{limit_sql}"


def render_df_info(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.info(buf=buf, show_counts=True)
    return buf.getvalue()


def main():
    st.set_page_config(page_title="Hive 表 EDA", layout="wide")
    st.title("Hive 表 EDA（计数趋势 + 随机抽样 + 可选 Profiling）")

    with st.sidebar:
        st.subheader("Hive 连接配置")
        host = st.text_input("Host", value=os.getenv("HIVE_HOST", ""))
        port = st.number_input("Port", value=int(os.getenv("HIVE_PORT", "10000")), step=1)
        database = st.text_input("Database", value=os.getenv("HIVE_DATABASE", "default"))
        username = st.text_input("Username", value=os.getenv("HIVE_USERNAME", ""))
        password = st.text_input("Password（可选）", value=os.getenv("HIVE_PASSWORD", ""), type="password")
        auth = st.selectbox("Auth", options=["NONE", "LDAP", "KERBEROS"], index=0)

        cfg = HiveConfig(
            host=host.strip(),
            port=int(port),
            username=username.strip(),
            password=password,
            database=database.strip() or "default",
            auth=auth,
        )

        st.divider()
        st.subheader("运行参数")
        table_name = st.text_input("表名", value="")

        partition_count_key = st.text_input("分区计数字段（分区表）", value="dt")
        show_points = st.number_input("趋势展示最近 N 个点", min_value=10, max_value=2000, value=90, step=10)

        st.divider()
        st.subheader("抽样/Profiling")
        sampling_rate = st.slider("抽样比例", min_value=0.001, max_value=1.0, value=0.10, step=0.001)
        seed = st.number_input("随机种子", value=42, step=1)
        extra_where = st.text_area("额外过滤条件（可选）", value="")
        max_candidate_rows = st.number_input("候选样本最大行数（limit）", value=200000, step=10000)
        profile_max_rows = st.number_input("Profiling 最大行数", value=50000, step=5000)
        strip_prefix = st.checkbox("展示时去掉列名前缀（db.table.）", value=True)

        enable_profiling = st.checkbox("生成 ydata_profiling 报告（较慢）", value=False)

        run = st.button("执行", type="primary", use_container_width=True)

    if not run:
        st.info("在左侧填写 Hive 配置与表名后点击“执行”。")
        return

    if not cfg.host:
        st.error("请先填写 Hive Host。")
        return
    if not table_name.strip():
        st.error("请先填写表名。")
        return

    full_table = normalize_table_name(table_name, default_db=cfg.database)

    # 连接性测试（简单查询）
    try:
        hive_query(cfg, "SELECT 1 AS ok")
    except Exception as e:
        st.error(f"Hive 连接失败：{e}")
        return

    st.success(f"连接成功。目标表：{full_table}")

    # 1) Schema
    with st.spinner("读取表结构（DESCRIBE）..."):
        schema = get_table_schema(cfg, full_table)
    data_cols_df = schema["data_cols"]
    part_cols_df = schema["partition_cols"]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("字段（非分区）")
        st.caption(f"共 {len(data_cols_df)} 列")
        st.dataframe(data_cols_df, use_container_width=True, height=420)
    with c2:
        st.subheader("分区字段")
        st.caption(f"共 {len(part_cols_df)} 列")
        st.dataframe(part_cols_df, use_container_width=True, height=420)

    # 2) Count logic
    if not is_partitioned(schema):
        st.subheader("全表记录数")
        with st.spinner("执行 count(*) ..."):
            cnt_df = hive_query(cfg, f"SELECT COUNT(1) AS cnt FROM {full_table}")
        cnt = int(cnt_df.iloc[0, 0]) if not cnt_df.empty else 0
        st.metric("count(*)", f"{cnt:,}")
    else:
        st.subheader("分区计数趋势")
        part_keys = part_cols_df["col_name"].astype(str).tolist() if "col_name" in part_cols_df.columns else []
        x_key = partition_count_key if partition_count_key in part_keys else (part_keys[0] if part_keys else partition_count_key)
        sql = f"SELECT {x_key} AS p, COUNT(1) AS cnt FROM {full_table} GROUP BY {x_key} ORDER BY {x_key}"
        st.code(sql, language="sql")
        with st.spinner("执行分区 group by 计数 ..."):
            part_cnt = hive_query(cfg, sql)

        part_cnt = normalize_df_columns(part_cnt) if strip_prefix else part_cnt
        if part_cnt.empty:
            st.warning("未返回分区计数结果。")
        else:
            # 只展示最近 N 个点
            part_cnt_view = part_cnt.tail(int(show_points)).copy() if len(part_cnt) > int(show_points) else part_cnt.copy()
            st.dataframe(part_cnt_view, use_container_width=True, height=260)
            x_dt = pd.to_datetime(part_cnt_view["p"], errors="coerce")
            part_cnt_view["x_label"] = x_dt.dt.strftime("%Y-%m-%d").where(x_dt.notna(), part_cnt_view["p"].astype(str))
            fig = px.line(part_cnt_view, x="x_label", y="cnt", markers=True, title=f"{full_table} 分区计数趋势（x={x_key}）")
            st.plotly_chart(fig, use_container_width=True)

    # 3) Sampling + (optional) profiling
    st.subheader("随机抽样样本（用于结构分布观察）")
    sample_sql = build_sampling_sql(
        full_table=full_table,
        sampling_rate=float(sampling_rate),
        seed=int(seed),
        extra_where=extra_where,
        columns="*",
        limit=int(max_candidate_rows) if max_candidate_rows else None,
    )
    st.code(sample_sql, language="sql")
    with st.spinner("执行抽样 SQL ..."):
        sample_df = hive_query(cfg, sample_sql)
    sample_df = normalize_df_columns(sample_df) if strip_prefix else sample_df
    st.caption(f"候选样本：{len(sample_df)} 行，{sample_df.shape[1]} 列")
    st.dataframe(sample_df.head(200), use_container_width=True, height=360)

    with st.expander("样本 df.info() / describe（基于样本）", expanded=False):
        st.code(render_df_info(sample_df), language="text")
        try:
            desc = sample_df.describe(include="all").T
            st.dataframe(desc, use_container_width=True, height=420)
        except Exception as e:
            st.warning(f"describe 失败：{e}")

    # profiling：先随机下采样到 5 万行
    if enable_profiling:
        if ProfileReport is None:
            st.error("未安装 ydata_profiling：pip install ydata-profiling")
            return
        with st.spinner("二次随机下采样 + 生成 profiling 报告（可能较慢）..."):
            if len(sample_df) > int(profile_max_rows):
                profile_df = sample_df.sample(n=int(profile_max_rows), random_state=int(seed))
            else:
                profile_df = sample_df.sample(frac=1.0, random_state=int(seed))

            report_title = f"EDA - {full_table} - rate={sampling_rate} - rows={len(profile_df)}"
            profile = ProfileReport(profile_df, title=report_title, explorative=True)

            safe_name = re.sub(r"[^0-9a-zA-Z_\\.\\-]+", "_", full_table)
            now = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = os.path.join(os.getcwd(), f"profile_{safe_name}_{now}.html")
            profile.to_file(out_path)

        st.success(f"报告已生成：{out_path}")
        with open(out_path, "r", encoding="utf-8", errors="ignore") as f:
            html = f.read()
        st.components.v1.html(html, height=900, scrolling=True)


if __name__ == "__main__":
    main()

