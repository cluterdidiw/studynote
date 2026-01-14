import pandas as pd
import streamlit as st
import networkx as nx
from streamlit_agraph import agraph, Node, Edge, Config
import re
import json
import pymysql
import warnings
from io import BytesIO

# 1. 基础配置
warnings.filterwarnings("ignore")

# =================================================================
# 2. 数据库默认配置
# =================================================================
DB_CONFIG = {
    "host": "192.168.101.199",
    "user": "dol",
    "password": "dol*123456",
    "database": "dolphin",
    "charset": "utf8mb4"
}

# =================================================================
# 3. 状态初始化
# =================================================================
if "df" not in st.session_state:
    st.session_state.df = None
if "selected_nodes" not in st.session_state:
    st.session_state.selected_nodes = []

# =================================================================
# 4. 核心解析与穿透逻辑 (保持不动)
# =================================================================
def is_temp_table(table_name):
    temp_prefixes = ['tmp_', 'temp_', 'mid_', 'intermediate_', 'tmp.', 'temp.', 'mid.']
    return any(table_name.startswith(prefix) for prefix in temp_prefixes)

def clean_sql_for_cte(sql_stmt):
    sql_clean = re.sub(r'--.*?\n', ' ', sql_stmt, flags=re.I | re.DOTALL)
    sql_clean = re.sub(r'/\*.*?\*/', ' ', sql_clean, flags=re.I | re.DOTALL)
    sql_clean = re.sub(r'\s+', ' ', sql_clean.strip().lower())
    return sql_clean

def extract_all_cte_aliases(sql_stmt):
    clean_sql = clean_sql_for_cte(sql_stmt)
    pattern = r'(\w+)\s+as\s*\('
    matches = re.findall(pattern, clean_sql)
    return list(set(matches))

def extract_output_tables(stmt):
    pattern = r"""(?i)(?:insert\s+(?:overwrite|into)\s+table|create\s+table)\s*(?:partition\s*\(.*?\)\s*)?[`"]?([\w\.]+)[`"]?"""
    return [t.lower() for t in re.findall(pattern, stmt, flags=re.VERBOSE)]

def extract_input_tables(stmt):
    cte_aliases = extract_all_cte_aliases(stmt)
    pattern = r"""(?i)(?:from|join)\s+[`"]?([\w\.]+)[`"]?(?:\s+as\s+\w+|\s+\w+)?"""
    tables = re.findall(pattern, stmt, flags=re.VERBOSE)
    return list(set([t.lower() for t in tables if not t.startswith("(") and t.lower() not in cte_aliases]))

def find_all_sql_in_json(obj):
    found_sqls = []
    if isinstance(obj, dict):
        for v in obj.values(): found_sqls += find_all_sql_in_json(v)
    elif isinstance(obj, list):
        for v in obj: found_sqls += find_all_sql_in_json(v)
    elif isinstance(obj, str):
        if "insert" in obj.lower() or "select" in obj.lower():
            found_sqls.append(obj)
    return found_sqls

def compress_graph(df):
    if df is None or df.empty: return df
    G = nx.MultiDiGraph()
    for _, row in df.iterrows():
        G.add_edge(row["source"], row["target"], project=row["project"], task_name=row["task_name"])
    temp_nodes = [n for n in G.nodes() if is_temp_table(str(n))]
    for node in temp_nodes:
        pre, suc = list(G.predecessors(node)), list(G.successors(node))
        for p in pre:
            for s in suc:
                if p == s: continue
                p_edges = G.get_edge_data(p, node)
                s_edges = G.get_edge_data(node, s)
                G.add_edge(p, s, project=p_edges[0]['project'], task_name=s_edges[0]['task_name'])
        G.remove_node(node)
    res = []
    for u, v, d in G.edges(data=True):
        res.append({"source": u, "target": v, "project": d.get("project"), "task_name": d.get("task_name")})
    return pd.DataFrame(res).drop_duplicates()

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Sheet1')
    return output.getvalue()

def build_panorama_relation(df, target_nodes):
    G = nx.DiGraph()
    edge_meta = {} 
    for _, row in df.iterrows():
        s, t = str(row["source"]), str(row["target"])
        if s and t and s != t:
            G.add_edge(s, t)
            if (s, t) not in edge_meta: edge_meta[(s, t)] = []
            edge_meta[(s, t)].append({"proj": row["project"], "task": row["task_name"]})
    
    core_node_set = set(target_nodes)
    all_down_depth, all_up_depth = {}, {}
    def get_down(node, depth):
        all_down_depth[node] = max(depth, all_down_depth.get(node, 0))
        for c in G.successors(node): get_down(c, depth + 1)
    def get_up(node, depth):
        all_up_depth[node] = max(depth, all_up_depth.get(node, 0))
        for p in G.predecessors(node): get_up(p, depth + 1)

    for core in core_node_set:
        if core in G:
            get_down(core, 0); get_up(core, 0)

    all_related = (set(all_up_depth.keys()) | set(all_down_depth.keys()))
    node_basic_info, detail_records = {}, []
    layer_colors = {"ods":"#1E88E5", "dwd":"#43A047", "dim":"#43A047", "dws":"#FB8C00", "ads":"#E53935"}
    offset = max(all_up_depth.values()) if all_up_depth else 0
    
    for node in all_related:
        color = "#757575"
        for k, v in layer_colors.items():
            if k in node.lower(): color = v; break
        raw_lvl = 0
        if node in core_node_set: raw_lvl = 0
        elif node in all_up_depth and node not in all_down_depth: raw_lvl = -all_up_depth[node]
        else: raw_lvl = all_down_depth[node]
        
        final_lvl = raw_lvl + offset
        projs, tasks = set(), set()
        for (s, t), v_list in edge_meta.items():
            if s == node or t == node:
                for v in v_list: projs.add(v["proj"]); tasks.add(v["task"])
        
        node_basic_info[node] = {
            "color": color, "level": final_lvl, "label": node.split('.')[-1],
            "title": f"表名: {node}\n项目: {' | '.join(projs)}\n任务: {' | '.join(tasks)}",
            "full_info": f"### 📍 节点详情\n**完整表名**: `{node}`\n\n**关联项目**: {' | '.join(projs)}\n\n**关联任务**: {' | '.join(tasks)}"
        }
        detail_records.append({
            "节点名称": node,
            "关系": "核心" if node in core_node_set else ("上游" if raw_lvl < 0 else "下游"),
            "所属项目": " | ".join(projs), "关联任务": " | ".join(tasks)
        })

    relevant_edges = [(u, v) for u, v in G.edges() if u in all_related and v in all_related]
    return node_basic_info, relevant_edges, pd.DataFrame(detail_records)

# =================================================================
# 7. UI 主程序
# =================================================================
st.set_page_config(page_title="数仓血缘自动化分析", layout="wide")

# 初始化渲染变量
display_nodes, display_edges = [], []
node_info, df_details = {}, pd.DataFrame()

with st.sidebar:
    st.markdown("# 🛡️ 血缘分析看板") 
    st.caption("自动化数仓血缘追踪系统 v2.0")
    st.divider()
    
    st.header("🔄 数据获取")
    
    # 核心修复点：使用回调或确保同步点击后强制更新 session_state
    if st.button("🚀 从数仓同步最新血缘", use_container_width=True):
        with st.spinner("正在从数据库提取并解析 SQL..."):
            try:
                conn = pymysql.connect(**DB_CONFIG)
                cursor = conn.cursor()
                sql = """
                select t2.name as project_name, t1.name as task_name, t1.task_params
                from (
                    select name, task_params, project_code from (
                        select *, row_number() over(partition by name, project_code order by update_time desc) rk
                        from t_ds_task_definition where flag = 1 and task_type = 'SHELL'
                    ) tmp where rk = 1
                ) t1 join t_ds_project t2 on t1.project_code = t2.code;
                """
                cursor.execute(sql)
                tasks = cursor.fetchall()
                records = []
                for proj_name, task_name, task_json in tasks:
                    try:
                        task_data = json.loads(task_json)
                        for sql_text in find_all_sql_in_json(task_data):
                            for stmt in re.split(r';\s*', sql_text.lower()):
                                if not stmt.strip(): continue
                                out_t, in_t = extract_output_tables(stmt), extract_input_tables(stmt)
                                for o in out_t:
                                    for n in in_t:
                                        if n and o and n != o:
                                            records.append({"project": proj_name, "task_name": task_name, "source": n, "target": o})
                    except: continue
                # 同步结果保存到状态中
                st.session_state.df = compress_graph(pd.DataFrame(records).drop_duplicates())
                st.success("同步成功！")
                conn.close()
                st.rerun() # 强制刷新页面以确保主界面识别到新数据
            except Exception as e:
                st.error(f"同步失败: {e}")

    file = st.file_uploader("📂 上传血缘文件", type=["xlsx", "csv"])
    if file:
        raw = pd.read_excel(file) if file.name.endswith("xlsx") else pd.read_csv(file)
        st.session_state.df = compress_graph(raw)

    # 视图控制逻辑 (仅在有数据时显示)
    if st.session_state.df is not None:
        st.divider()
        all_nodes = sorted(list(set(st.session_state.df["source"].astype(str)) | set(st.session_state.df["target"].astype(str))))
        st.session_state.selected_nodes = st.multiselect("🎯 选择核心分析节点", all_nodes, default=st.session_state.selected_nodes)

        if st.session_state.selected_nodes:
            st.subheader("🛠️ 视图过滤")
            node_info, final_edges, df_details = build_panorama_relation(st.session_state.df, st.session_state.selected_nodes)
            
            f_mode = st.toggle("中心扩散模式", value=True)
            
            all_projs = set()
            for info in node_info.values():
                proj_match = re.findall(r"项目: (.*)\n", info["title"])
                if proj_match:
                    for p in proj_match[0].split(' | '): all_projs.add(p)
            selected_projects = st.multiselect("项目过滤", options=sorted(list(all_projs)), default=sorted(list(all_projs)))
            
            all_lvls = sorted(list(set(info["level"] for info in node_info.values())))
            if f_mode:
                core_lvls = [node_info[n]["level"] for n in st.session_state.selected_nodes if n in node_info]
                avg_lvl = int(sum(core_lvls) / len(core_lvls)) if core_lvls else 0
                steps = st.slider("步数范围 (±N)", 0, 10, 2)
                min_l, max_l = avg_lvl - steps, avg_lvl + steps
            else:
                min_l, max_l = st.select_slider("层级区间", options=all_lvls, value=(min(all_lvls), max(all_lvls)))

            # 计算待显示的节点
            filtered_ids = []
            for nid, info in node_info.items():
                proj_match = re.findall(r"项目: (.*)\n", info["title"])
                node_projs = set(proj_match[0].split(' | ')) if proj_match else set()
                project_match = any(p in selected_projects for p in node_projs) if selected_projects else True
                if (min_l <= info["level"] <= max_l) and project_match:
                    filtered_ids.append(nid)

            display_nodes = [Node(id=nid, label=node_info[nid]["label"], title=node_info[nid]["title"], size=18, 
                                  shape="dot" if nid not in st.session_state.selected_nodes else "diamond", 
                                  color=node_info[nid]["color"], level=node_info[nid]["level"], font={'color': 'black', 'size': 12}) 
                             for nid in filtered_ids]
            display_edges = [Edge(source=u, target=v, color="#ABB2B9") for u, v in set(final_edges) 
                             if u in filtered_ids and v in filtered_ids]

# --- 主展示区 ---
if st.session_state.df is not None and st.session_state.selected_nodes:
    tab1, tab2 = st.tabs(["🌐 依赖全景图", "📑 节点血缘列表"])
    
    with tab1:
        if not display_nodes:
            st.warning("当前筛选条件下无节点，请在左侧侧边栏调整范围。")
        else:
            # 这里的 height=1000 确保了充足的展示空间
            config = Config(width=1600, height=1000, directed=True, physics=False, hierarchical=True, 
                            direction="LR", levelSeparation=600, nodeSpacing=200, sortMethod="directed")
            
            clicked = agraph(nodes=display_nodes, edges=display_edges, config=config)
            if clicked and clicked in node_info:
                st.info(node_info[clicked]["full_info"])

    with tab2:
        st.download_button("📥 导出明细", data=to_excel(df_details), file_name="lineage_details.xlsx")
        st.dataframe(df_details, use_container_width=True)
else:
    # 状态提示：引导用户操作
    if st.session_state.df is None:
        st.info("💡 请在左侧点击【🚀 从数仓同步最新血缘】获取数据。")
    elif not st.session_state.selected_nodes:
        st.info("🎯 请在左侧【选择核心分析节点】以生成血缘视图。")