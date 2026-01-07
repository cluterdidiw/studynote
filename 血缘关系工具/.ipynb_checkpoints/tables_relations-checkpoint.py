import pandas as pd
import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import chardet
import re
import json
import pymysql
import warnings
from io import BytesIO
import os

# 忽略告警
warnings.filterwarnings("ignore")

# =================================================================
# 1. 核心解析逻辑
# =================================================================

def is_temp_table(table_name):
    """判断是否为临时表"""
    temp_prefixes = ['tmp_', 'temp_', 'mid_', 'intermediate_', 'tmp.', 'temp.', 'mid.']
    return any(table_name.startswith(prefix) for prefix in temp_prefixes)

def clean_sql_for_cte(sql_stmt):
    """清理SQL：移除注释、统一换行/空格"""
    sql_clean = re.sub(r'--.*?\n', ' ', sql_stmt, flags=re.I | re.DOTALL)
    sql_clean = re.sub(r'/\*.*?\*/', ' ', sql_clean, flags=re.I | re.DOTALL)
    sql_clean = re.sub(r'\s+', ' ', sql_clean.strip().lower())
    return sql_clean

def extract_all_cte_aliases(sql_stmt):
    """提取所有CTE别名"""
    clean_sql = clean_sql_for_cte(sql_stmt)
    pattern = r'(\w+)\s+as\s*\('
    matches = re.findall(pattern, clean_sql)
    return list(set(matches))

def extract_output_tables(stmt):
    """提取输出表 (保留临时表，后续由穿透算法处理)"""
    pattern = r"""(?i)(?:insert\s+(?:overwrite|into)\s+table|create\s+table)\s*(?:partition\s*\(.*?\)\s*)?[`"]?([\w\.]+)[`"]?"""
    tables = re.findall(pattern, stmt, flags=re.VERBOSE)
    return [t.lower() for t in tables]

def extract_input_tables(stmt):
    """提取输入表 + 过滤CTE别名"""
    cte_aliases = extract_all_cte_aliases(stmt)
    pattern = r"""(?i)(?:from|join)\s+[`"]?([\w\.]+)[`"]?(?:\s+as\s+\w+|\s+\w+)?"""
    tables = re.findall(pattern, stmt, flags=re.VERBOSE)
    filtered_tables = []
    for table in tables:
        table_lower = table.lower()
        if (not table_lower.startswith("(") 
            and table_lower not in cte_aliases):
            filtered_tables.append(table_lower)
    return list(set(filtered_tables))

def extract_sql_from_text(text):
    """从文本中提取SQL"""
    sql_list = []
    pattern = r'sql\s*=\s*"([^"]+)"'
    matches = re.findall(pattern, text, flags=re.S)
    for match in matches:
        sql_list.append(match.strip())
    if not matches and "insert" in text.lower():
        inserts = re.findall(r'(insert\s+(?:overwrite|into)\s+table.*?;)', text, flags=re.S | re.I)
        sql_list += [x.strip("; \n") for x in inserts]
    return sql_list

def find_all_sql_in_json(obj):
    """递归查找JSON中的SQL"""
    found_sqls = []
    if isinstance(obj, dict):
        for v in obj.values(): found_sqls += find_all_sql_in_json(v)
    elif isinstance(obj, list):
        for v in obj: found_sqls += find_all_sql_in_json(v)
    elif isinstance(obj, str):
        found_sqls += extract_sql_from_text(obj)
    return found_sqls

# =================================================================
# 2. 中间穿透逻辑 (路径压缩)
# =================================================================

def compress_graph(df):
    """
    通过路径压缩算法，穿透中间临时表节点。
    A -> TMP -> B  =>  A -> B
    """
    if df is None or df.empty:
        return df

    G = nx.MultiDiGraph()
    for _, row in df.iterrows():
        G.add_edge(row["source"], row["target"], project=row["project"], task_name=row["task_name"])

    all_nodes = list(G.nodes())
    temp_nodes = [n for n in all_nodes if is_temp_table(str(n))]

    for node in temp_nodes:
        predecessors = list(G.predecessors(node))
        successors = list(G.successors(node))
        for p in predecessors:
            for s in successors:
                if p == s: continue
                p_edges = G.get_edge_data(p, node)
                s_edges = G.get_edge_data(node, s)
                proj = p_edges[0]['project'] if p_edges else "unknown"
                task = s_edges[0]['task_name'] if s_edges else "unknown"
                G.add_edge(p, s, project=proj, task_name=task)
        G.remove_node(node)

    new_records = []
    for u, v, data in G.edges(data=True):
        new_records.append({
            "source": u,
            "target": v,
            "project": data.get("project"),
            "task_name": data.get("task_name")
        })
    return pd.DataFrame(new_records).drop_duplicates()

# =================================================================
# 3. 数据提取与导出工具
# =================================================================

def fetch_data_from_db(config):
    try:
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("🔗 正在连接数据库...")
        conn = pymysql.connect(**config)
        cursor = conn.cursor()
        progress_bar.progress(10)

        status_text.text("🔍 正在查询任务定义...")
        sql = """
        select t2.name as project_name, t1.name as task_name, t1.task_params
        from (
            select name, task_params, project_code from (
                select *, row_number() over(partition by name, project_code order by update_time desc) rk
                from t_ds_task_definition where flag = 1 and task_type = 'SHELL' and project_code <> '14173450119264'
            ) tmp where rk = 1
        ) t1 join t_ds_project t2 on t1.project_code = t2.code;
        """
        cursor.execute(sql)
        tasks = cursor.fetchall()
        progress_bar.progress(30)

        records = []
        total = len(tasks)
        for i, (proj_name, task_name, task_json) in enumerate(tasks):
            try:
                task_data = json.loads(task_json)
                sql_texts = find_all_sql_in_json(task_data)
                for sql_text in sql_texts:
                    statements = re.split(r';\s*', sql_text.lower())
                    for stmt in statements:
                        if not stmt.strip(): continue
                        out_t = extract_output_tables(stmt)
                        in_t = extract_input_tables(stmt)
                        for o in out_t:
                            for n in in_t:
                                if n and o and n != o:
                                    records.append({"project": proj_name, "task_name": task_name, "source": n, "target": o})
            except: continue
            if i % 10 == 0:
                percent = 30 + int((i / total) * 60)
                progress_bar.progress(percent)
                status_text.text(f"⏳ 正在解析任务 SQL: {i}/{total}")

        df = pd.DataFrame(records).drop_duplicates()
        status_text.text("⚙️ 正在执行中间表穿透压缩...")
        df = compress_graph(df)
        
        cursor.close()
        conn.close()
        progress_bar.progress(100)
        status_text.text("✅ 数据提取与穿透完成！")
        return df
    except Exception as e:
        st.error(f"❌ 数据库连接或执行失败: {e}")
        return None

def to_excel(df):
    """将数据帧转换为可下载的Excel字节流"""
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Lineage_Data')
    return output.getvalue()

# =================================================================
# 4. 可视化与 UI
# =================================================================

def build_panorama_relation(df, target_nodes):
    G = nx.DiGraph()
    edge_list = []
    for _, row in df.iterrows():
        source, target = str(row["source"]), str(row["target"])
        if source and target and source != target:
            G.add_edge(source, target)
            edge_list.append((source, target))
    
    core_node_set = set(target_nodes)
    all_down_depth, all_up_depth = {}, {}

    def get_down(node, depth, core):
        if node in core_node_set and node != core: return
        all_down_depth[node] = max(depth, all_down_depth.get(node, 0))
        for c in G.successors(node):
            if c.strip() and c not in core_node_set: get_down(c, depth + 1, core)

    def get_up(node, depth, core):
        if node in core_node_set and node != core: return
        all_up_depth[node] = max(depth, all_up_depth.get(node, 0))
        for p in G.predecessors(node):
            if p.strip() and p not in core_node_set: get_up(p, depth + 1, core)

    for core in core_node_set:
        if core in G:
            for c in G.successors(core): get_down(c, 1, core)
            for p in G.predecessors(core): get_up(p, 1, core)

    node_basic_info = {}
    core_colors = {c: ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0"][i % 4] for i, c in enumerate(core_node_set)}
    all_related = list(core_node_set) + list(all_up_depth.keys()) + list(all_down_depth.keys())
    
    for node in set(all_related):
        mask = (df["source"].astype(str) == node) | (df["target"].astype(str) == node)
        tasks = df[mask]["task_name"].unique().tolist()
        projects = df[mask]["project"].unique().tolist()
        if node in core_node_set:
            info = {"final_depth_type": "core", "final_depth": 0, "is_core": True, "node_color": core_colors[node]}
        elif node in all_up_depth:
            d = all_up_depth[node]
            info = {"final_depth_type": "upstream", "final_depth": d, "is_core": False, "node_color": f"#{max(0, 13+d*20):02x}{min(255, 71+d*15):02x}{min(255, 161+d*10):02x}"}
        else:
            d = all_down_depth[node]
            info = {"final_depth_type": "downstream", "final_depth": d, "is_core": False, "node_color": f"#{min(255, 230+d*5):02x}{min(255, 81+d*10):02x}{0:02x}"}
        info.update({"related_task": tasks, "related_project": projects})
        node_basic_info[node] = info

    up_h = {d: [n for n, dep in all_up_depth.items() if dep == d] for d in set(all_up_depth.values())}
    down_h = {d: [n for n, dep in all_down_depth.items() if dep == d] for d in set(all_down_depth.values())}
    up_edges = [(p, c) for p, c in edge_list if (c in core_node_set and p in all_up_depth) or (p in all_up_depth and c in all_up_depth and all_up_depth[p] > all_up_depth[c])]
    down_edges = [(p, c) for p, c in edge_list if (p in core_node_set and c in all_down_depth) or (p in all_down_depth and c in all_down_depth and all_down_depth[p] < all_down_depth[c])]

    return up_h, down_h, node_basic_info, up_edges, down_edges, G, core_node_set

def plot_graph(core_nodes, up_h, down_h, node_info, up_edges, down_edges, G):
    fig = go.Figure()
    x_step, y_spacing = 10, 3.5
    node_coords = {}
    
    sorted_cores = sorted(list(core_nodes))
    for i, n in enumerate(sorted_cores):
        node_coords[n] = (0, (i - (len(sorted_cores)-1)/2) * 8)

    for h_dict, x_dir in [(up_h, -1), (down_h, 1)]:
        for depth in sorted(h_dict.keys()):
            nodes = sorted(h_dict[depth])
            for i, n in enumerate(nodes):
                node_coords[n] = (x_dir * depth * x_step, (i - (len(nodes)-1)/2) * y_spacing)

    edge_x, edge_y = [], []
    for p, c in list(set(up_edges + down_edges)):
        if p in node_coords and c in node_coords:
            edge_x += [node_coords[p][0], node_coords[c][0], None]
            edge_y += [node_coords[p][1], node_coords[c][1], None]
    
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines", line=dict(width=1, color="#999"), hoverinfo="none"))

    nx_list, ny_list, n_color, n_size, n_text, n_label = [], [], [], [], [], []
    for n, coord in node_coords.items():
        nx_list.append(coord[0]); ny_list.append(coord[1])
        info = node_info[n]
        n_color.append(info["node_color"])
        n_size.append(40 if info["is_core"] else 20)
        n_label.append(n.split('.')[-1])
        n_text.append(f"节点: {n}<br>项目: {','.join(info['related_project'])}<br>任务: {','.join(info['related_task'])}")

    fig.add_trace(go.Scatter(
        x=nx_list, y=ny_list, mode="markers+text", text=n_label, textposition="top center",
        marker=dict(color=n_color, size=n_size, line=dict(width=1, color="black")),
        hovertext=n_text, hoverinfo="text"
    ))

    fig.update_layout(
        title=f"<b>数据血缘依赖图 (已自动穿透临时表)</b>",
        showlegend=False, plot_bgcolor="white",
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        height=850, width=1600
    )
    return fig

# =================================================================
# 5. Streamlit 主界面
# =================================================================

st.set_page_config(page_title="数据血缘分析平台", layout="wide")
st.title("📊 数据血缘可视化分析平台")

if "df" not in st.session_state: st.session_state.df = None
if "selected_nodes" not in st.session_state: st.session_state.selected_nodes = []

with st.sidebar:
    st.header("🔌 数据源配置")
    mode = st.radio("选择输入方式", ["数据库实时提取", "上传本地文件"])
    
    if mode == "数据库实时提取":
        with st.expander("数据库连接设置", expanded=True):
            host = st.text_input("Host", "192.168.101.199")
            user = st.text_input("User", "dol")
            pw = st.text_input("Password", "dol*123456", type="password")
            db = st.text_input("Database", "dolphin")
        if st.button("🚀 开始提取并穿透"):
            config = {"host": host, "user": user, "password": pw, "database": db, "charset": "utf8mb4"}
            st.session_state.df = fetch_data_from_db(config)
    else:
        file = st.file_uploader("上传 Excel/CSV", type=["xlsx", "csv"])
        if file:
            raw_df = pd.read_excel(file) if file.name.endswith("xlsx") else pd.read_csv(file)
            st.info("🔄 正在执行中间表穿透处理...")
            st.session_state.df = compress_graph(raw_df)

    # 导出功能区
    if st.session_state.df is not None:
        st.divider()
        st.subheader("💾 结果导出")
        st.write(f"当前解析条数: **{len(st.session_state.df)}**")
        excel_data = to_excel(st.session_state.df)
        st.download_button(
            label="📥 导出穿透后的血缘数据集",
            data=excel_data,
            file_name="lineage_data_compressed.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        st.divider()
        all_nodes = sorted(list(set(st.session_state.df["source"].astype(str)) | set(st.session_state.df["target"].astype(str))))
        st.session_state.selected_nodes = st.multiselect("🎯 选择核心节点进行分析", all_nodes)

# 主展示区
if st.session_state.df is not None and st.session_state.selected_nodes:
    tabs = st.tabs(["🌐 依赖全景视图", "📑 节点血缘列表"])
    
    # 路径与层级计算
    up_h, down_h, node_info, up_e, down_e, G, cores = build_panorama_relation(st.session_state.df, st.session_state.selected_nodes)
    
    with tabs[0]:
        fig = plot_graph(cores, up_h, down_h, node_info, up_e, down_e, G)
        st.plotly_chart(fig, use_container_width=True)
        
    with tabs[1]:
        details = [{"节点名称": k, "关系类型": v["final_depth_type"], "链路深度": v["final_depth"], "所属项目": v["related_project"], "关联任务": v["related_task"]} for k, v in node_info.items()]
        st.dataframe(pd.DataFrame(details), use_container_width=True)
else:
    st.info("💡 操作指南：\n1. 在左侧配置数据源并点击提取。\n2. 提取成功后，可选择导出完整 Excel 或在下方搜索框选择核心节点进行可视化展示。")