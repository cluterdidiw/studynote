import pandas as pd
import streamlit as st
import networkx as nx
import plotly.graph_objects as go
import chardet
import os

# ---------------------- 1. 页面核心配置 ----------------------
st.set_page_config(
    page_title="核心节点依赖关系查询",
    page_icon="🔍",
    layout="wide"
)

# ---------------------- 2. 数据加载函数 ----------------------
@st.cache_data
def load_data(file_path=None, uploaded_file=None):
    try:
        if uploaded_file is not None:
            file_ext = os.path.splitext(uploaded_file.name)[1].lower()
            if file_ext == ".csv":
                encode = chardet.detect(uploaded_file.getvalue())["encoding"] or "gbk"
                df = pd.read_csv(uploaded_file, encoding=encode)
            elif file_ext in [".xlsx", ".xls"]:
                engine = "openpyxl" if file_ext == ".xlsx" else "xlrd"
                df = pd.read_excel(uploaded_file, engine=engine)
            else:
                st.error("❌ 不支持的文件格式！仅支持CSV/Excel（.csv/.xlsx/.xls）")
                return None
        elif file_path and os.path.exists(file_path):
            file_ext = os.path.splitext(file_path)[1].lower()
            if file_ext == ".csv":
                encode = chardet.detect(open(file_path, "rb").read())["encoding"] or "gbk"
                df = pd.read_csv(file_path, encoding=encode)
            elif file_ext in [".xlsx", ".xls"]:
                engine = "openpyxl" if file_ext == ".xlsx" else "xlrd"
                df = pd.read_excel(file_path, engine=engine)
            else:
                st.error("❌ 不支持的文件格式！仅支持CSV/Excel（.csv/.xlsx/.xls）")
                return None
        else:
            st.warning("⚠️ 文件路径不存在或未上传文件，请检查！")
            return None
        
        required_cols = ["source", "target"]
        if not all(col in df.columns for col in required_cols):
            st.error(f"❌ 文件缺少必要列！必须包含：{required_cols}")
            return None
        
        st.success(f"✅ 数据加载成功！共 {len(df)} 行，{len(df.columns)} 列")
        return df
    except Exception as e:
        st.error(f"❌ 数据加载失败：{str(e)}")
        return None

# ---------------------- 3. 核心计算函数 ----------------------
def build_panorama_relation(df, target_nodes):
    """全景图：多核心节点合并计算（类似之前的共享模式）"""
    G = nx.DiGraph()
    edge_list = []
    for _, row in df.iterrows():
        source = str(row["source"]) if pd.notna(row["source"]) else ""
        target = str(row["target"]) if pd.notna(row["target"]) else ""
        if source and target and source != target:
            G.add_edge(source, target)
            edge_list.append((source, target))
    
    core_node_set = set(target_nodes)
    all_downstream_node_depth = {}
    all_upstream_node_depth = {}
    
    # 多核心下游层级
    def get_multi_core_downstream(node, current_depth, core_node):
        if node in core_node_set and node != core_node:
            return
        if node in all_downstream_node_depth:
            if current_depth > all_downstream_node_depth[node]:
                all_downstream_node_depth[node] = current_depth
        else:
            all_downstream_node_depth[node] = current_depth
        children = list(G.successors(node))
        children = [c for c in children if c.strip() and c not in core_node_set]
        for child in children:
            get_multi_core_downstream(child, current_depth + 1, core_node)
    
    for core_node in core_node_set:
        core_children = list(G.successors(core_node))
        for child in core_children:
            get_multi_core_downstream(child, 1, core_node)
    
    # 多核心上游层级
    def get_multi_core_upstream(node, current_depth, core_node):
        if node in core_node_set and node != core_node:
            return
        if node in all_upstream_node_depth:
            if current_depth > all_upstream_node_depth[node]:
                all_upstream_node_depth[node] = current_depth
        else:
            all_upstream_node_depth[node] = current_depth
        parents = list(G.predecessors(node))
        parents = [p for p in parents if p.strip() and p not in core_node_set]
        for parent in parents:
            get_multi_core_upstream(parent, current_depth + 1, core_node)
    
    for core_node in core_node_set:
        core_parents = list(G.predecessors(core_node))
        for parent in core_parents:
            get_multi_core_upstream(parent, 1, core_node)
    
    # 层级分组
    downstream_hierarchy = {k: sorted(list(set(v))) for k, v in sorted({
        depth: [node for node, d in all_downstream_node_depth.items() if d == depth]
        for depth in all_downstream_node_depth.values()
    }.items())}
    upstream_hierarchy = {k: sorted(list(set(v))) for k, v in sorted({
        depth: [node for node, d in all_upstream_node_depth.items() if d == depth]
        for depth in all_upstream_node_depth.values()
    }.items())}
    
    # 边处理
    downstream_edges = []
    for (parent, child) in edge_list:
        if parent in core_node_set and child in all_downstream_node_depth:
            downstream_edges.append((parent, child))
        elif parent in all_downstream_node_depth and child in all_downstream_node_depth:
            if all_downstream_node_depth[parent] < all_downstream_node_depth[child]:
                downstream_edges.append((parent, child))
    downstream_edges = list(set(downstream_edges))
    
    upstream_edges = []
    for (parent, child) in edge_list:
        if child in core_node_set and parent in all_upstream_node_depth:
            upstream_edges.append((parent, child))
        elif parent in all_upstream_node_depth and child in all_upstream_node_depth:
            if all_upstream_node_depth[parent] > all_upstream_node_depth[child]:
                upstream_edges.append((parent, child))
    upstream_edges = list(set(upstream_edges))
    
    # 节点信息
    all_related_nodes = list(core_node_set)
    all_related_nodes.extend(all_upstream_node_depth.keys())
    all_related_nodes.extend(all_downstream_node_depth.keys())
    all_related_nodes = list(set(all_related_nodes))
    
    node_basic_info = {}
    core_color_list = ["#4CAF50", "#2196F3", "#FF9800", "#9C27B0", "#F44336", "#00BCD4"]
    core_colors = {core: core_color_list[i%len(core_color_list)] for i, core in enumerate(core_node_set)}
    
    for node in all_related_nodes:
        related_task = []
        related_project = []
        if "task_name" in df.columns or "project" in df.columns:
            mask = (df["source"].astype(str) == node) | (df["target"].astype(str) == node)
            if "task_name" in df.columns:
                related_task = df[mask]["task_name"].dropna().astype(str).unique().tolist()
            if "project" in df.columns:
                related_project = df[mask]["project"].dropna().astype(str).unique().tolist()
        
        if node in core_node_set:
            final_depth_type = "core"
            final_depth = 0
            node_color = core_colors[node]
        elif node in all_upstream_node_depth:
            final_depth_type = "upstream"
            final_depth = all_upstream_node_depth[node]
            node_color = f"#{13 + (final_depth-1)*20:02x}{71 + (final_depth-1)*15:02x}{161 + (final_depth-1)*10:02x}"
        else:
            final_depth_type = "downstream"
            final_depth = all_downstream_node_depth[node]
            node_color = f"#{230 + (final_depth-1)*5:02x}{81 + (final_depth-1)*10:02x}{0 + (final_depth-1)*5:02x}"
        
        node_basic_info[node] = {
            "related_task": related_task,
            "related_project": related_project,
            "final_depth_type": final_depth_type,
            "final_depth": final_depth,
            "is_core": node in core_node_set,
            "node_color": node_color
        }
    
    return (upstream_hierarchy, downstream_hierarchy, node_basic_info, 
            upstream_edges, downstream_edges, G, all_upstream_node_depth, 
            all_downstream_node_depth, core_node_set)

def build_single_core_relation(df, target_node):
    """单核心节点计算"""
    G = nx.DiGraph()
    edge_list = []
    for _, row in df.iterrows():
        source = str(row["source"]) if pd.notna(row["source"]) else ""
        target = str(row["target"]) if pd.notna(row["target"]) else ""
        if source and target and source != target:
            G.add_edge(source, target)
            edge_list.append((source, target))
    
    core_node_set = {target_node}
    downstream_node_depth = {}
    upstream_node_depth = {}
    
    # 下游层级
    def get_downstream_depth(node, current_depth):
        if node in downstream_node_depth:
            if current_depth > downstream_node_depth[node]:
                downstream_node_depth[node] = current_depth
        else:
            downstream_node_depth[node] = current_depth
        children = list(G.successors(node))
        children = [c for c in children if c.strip() and c != target_node]
        for child in children:
            get_downstream_depth(child, current_depth + 1)
    
    core_children = list(G.successors(target_node))
    for child in core_children:
        get_downstream_depth(child, 1)
    
    # 上游层级
    def get_upstream_depth(node, current_depth):
        if node in upstream_node_depth:
            if current_depth > upstream_node_depth[node]:
                upstream_node_depth[node] = current_depth
        else:
            upstream_node_depth[node] = current_depth
        parents = list(G.predecessors(node))
        parents = [p for p in parents if p.strip() and p != target_node]
        for parent in parents:
            get_upstream_depth(parent, current_depth + 1)
    
    core_parents = list(G.predecessors(target_node))
    for parent in core_parents:
        get_upstream_depth(parent, 1)
    
    # 层级分组
    downstream_hierarchy = {k: sorted(list(set(v))) for k, v in sorted({
        depth: [node for node, d in downstream_node_depth.items() if d == depth]
        for depth in downstream_node_depth.values()
    }.items())}
    upstream_hierarchy = {k: sorted(list(set(v))) for k, v in sorted({
        depth: [node for node, d in upstream_node_depth.items() if d == depth]
        for depth in upstream_node_depth.values()
    }.items())}
    
    # 边处理
    downstream_edges = []
    for (parent, child) in edge_list:
        if parent == target_node and child in downstream_node_depth:
            downstream_edges.append((parent, child))
        elif parent in downstream_node_depth and child in downstream_node_depth:
            if downstream_node_depth[parent] < downstream_node_depth[child]:
                downstream_edges.append((parent, child))
    downstream_edges = list(set(downstream_edges))
    
    upstream_edges = []
    for (parent, child) in edge_list:
        if child == target_node and parent in upstream_node_depth:
            upstream_edges.append((parent, child))
        elif parent in upstream_node_depth and child in upstream_node_depth:
            if upstream_node_depth[parent] > upstream_node_depth[child]:
                upstream_edges.append((parent, child))
    upstream_edges = list(set(upstream_edges))
    
    # 节点信息
    all_related_nodes = [target_node]
    all_related_nodes.extend(upstream_node_depth.keys())
    all_related_nodes.extend(downstream_node_depth.keys())
    all_related_nodes = list(set(all_related_nodes))
    
    node_basic_info = {}
    core_color = "#4CAF50"
    for node in all_related_nodes:
        related_task = []
        related_project = []
        if "task_name" in df.columns or "project" in df.columns:
            mask = (df["source"].astype(str) == node) | (df["target"].astype(str) == node)
            if "task_name" in df.columns:
                related_task = df[mask]["task_name"].dropna().astype(str).unique().tolist()
            if "project" in df.columns:
                related_project = df[mask]["project"].dropna().astype(str).unique().tolist()
        
        if node == target_node:
            final_depth_type = "core"
            final_depth = 0
            node_color = core_color
        elif node in upstream_node_depth:
            final_depth_type = "upstream"
            final_depth = upstream_node_depth[node]
            node_color = f"#{13 + (final_depth-1)*20:02x}{71 + (final_depth-1)*15:02x}{161 + (final_depth-1)*10:02x}"
        else:
            final_depth_type = "downstream"
            final_depth = downstream_node_depth[node]
            node_color = f"#{230 + (final_depth-1)*5:02x}{81 + (final_depth-1)*10:02x}{0 + (final_depth-1)*5:02x}"
        
        node_basic_info[node] = {
            "related_task": related_task,
            "related_project": related_project,
            "final_depth_type": final_depth_type,
            "final_depth": final_depth,
            "is_core": node == target_node,
            "node_color": node_color
        }
    
    return (upstream_hierarchy, downstream_hierarchy, node_basic_info, 
            upstream_edges, downstream_edges, G, upstream_node_depth, 
            downstream_node_depth, core_node_set)

# ---------------------- 4. 可视化函数 ----------------------
def plot_panorama_graph(target_nodes, upstream_hierarchy, downstream_hierarchy, 
                       node_basic_info, upstream_edges, downstream_edges, G, 
                       upstream_node_depth, downstream_node_depth, core_node_set):
    """全景图绘制（多核心合并）"""
    max_upstream_depth = max(upstream_hierarchy.keys()) if upstream_hierarchy else 0
    max_downstream_depth = max(downstream_hierarchy.keys()) if downstream_hierarchy else 0
    
    # 坐标计算：核心节点垂直排列在x=0
    x_step = 8
    node_coords = {}
    core_count = len(core_node_set)
    core_spacing = 8
    start_y = -(core_count - 1) * core_spacing / 2
    
    for i, core_node in enumerate(sorted(core_node_set)):
        node_coords[core_node] = (0, start_y + i * core_spacing)
    
    # 上游/下游x坐标
    x_coords = {}
    for depth in upstream_hierarchy:
        x_coords[f"up_{depth}"] = -x_step * depth
    for depth in downstream_hierarchy:
        x_coords[f"down_{depth}"] = x_step * depth
    
    # 上游节点布局
    for depth in sorted(upstream_hierarchy.keys()):
        nodes = upstream_hierarchy[depth]
        if not nodes:
            continue
        
        parent_to_children = {}
        for node in nodes:
            children = [c for c in G.successors(node) if c in node_coords]
            parent_to_children[node] = children
        
        def sort_by_child_y(node):
            children = parent_to_children[node]
            if not children:
                return 0
            child_ys = [node_coords[c][1] for c in children]
            return sum(child_ys) / len(child_ys)
        
        sorted_nodes = sorted(nodes, key=sort_by_child_y)
        spacing = 3.5
        start_y = -(len(sorted_nodes) - 1) * spacing / 2
        for i, node in enumerate(sorted_nodes):
            node_coords[node] = (x_coords[f"up_{depth}"], start_y + i * spacing)
    
    # 下游节点布局
    for depth in sorted(downstream_hierarchy.keys()):
        nodes = downstream_hierarchy[depth]
        if not nodes:
            continue
        
        child_to_parents = {}
        for node in nodes:
            parents = [p for p in G.predecessors(node) if p in node_coords]
            child_to_parents[node] = parents
        
        def sort_by_parent_y(node):
            parents = child_to_parents[node]
            if not parents:
                return 0
            parent_ys = [node_coords[p][1] for p in parents]
            return sum(parent_ys) / len(parent_ys)
        
        sorted_nodes = sorted(nodes, key=sort_by_parent_y)
        spacing = 3.5
        start_y = -(len(sorted_nodes) - 1) * spacing / 2
        for i, node in enumerate(sorted_nodes):
            node_coords[node] = (x_coords[f"down_{depth}"], start_y + i * spacing)
    
    # 边绘制
    fig = go.Figure()
    all_edges = upstream_edges + downstream_edges
    edge_x = []
    edge_y = []
    for (parent, child) in all_edges:
        if parent in node_coords and child in node_coords:
            edge_x.extend([node_coords[parent][0], node_coords[child][0], None])
            edge_y.extend([node_coords[parent][1], node_coords[child][1], None])
    
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=2, color="rgba(102, 102, 102, 0.7)"),
        hoverinfo="none",
        marker=dict(size=8, symbol="arrow-right"),
        showlegend=False
    ))
    
    # 节点绘制
    node_x = []
    node_y = []
    node_color = []
    node_size = []
    node_text = []
    node_labels = []
    
    for node in node_coords:
        node_x.append(node_coords[node][0])
        node_y.append(node_coords[node][1])
        info = node_basic_info[node]
        node_color.append(info["node_color"])
        
        if info["is_core"]:
            node_size.append(40)
            node_labels.append(f"核心：{node.split('.')[-1]}")
        else:
            node_size.append(max(18, 30 - (info["final_depth"]-1)*2))
            node_labels.append(node.split('.')[-1])
        
        # 【修改1】悬停信息增加task_name
        node_text.append(
            f"节点：{node}<br>"
            f"类型：{info['final_depth_type']}{info['final_depth'] if info['final_depth']>0 else ''}<br>"
            f"关联Project：{', '.join(info['related_project']) if info['related_project'] else '无'}<br>"
            f"关联TaskName：{', '.join(info['related_task']) if info['related_task'] else '无'}"
        )
    
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_labels,
        textposition="top center",
        marker=dict(
            color=node_color,
            size=node_size,
            line=dict(width=2, color="black"),
            symbol="circle"
        ),
        hovertext=node_text,
        hoverinfo="text",
        hoverlabel=dict(font_size=12),
        zorder=10,
        showlegend=False
    ))
    
    # 布局
    all_x = [v[0] for v in node_coords.values()] if node_coords else []
    x_min = min(all_x) - 15 if all_x else -20
    x_max = max(all_x) + 15 if all_x else 20
    all_y = [v[1] for v in node_coords.values()] if node_coords else []
    y_min = min(all_y) - 10 if all_y else -20
    y_max = max(all_y) + 10 if all_y else 20
    
    core_nodes_str = ", ".join(sorted(core_node_set))
    fig.update_layout(
        width=max(2500, x_max - x_min + 600),
        height=max(1600, y_max - y_min + 500),
        hovermode="closest",
        dragmode="pan",
        xaxis=dict(
            range=[x_min, x_max],
            showgrid=True, gridcolor="#eee",
            zeroline=True, zerolinecolor="#4CAF50", zerolinewidth=4,
            showticklabels=False,
            title=f"全景视图：上游{max_upstream_depth}层 ← 核心[{core_nodes_str}] → 下游{max_downstream_depth}层"
        ),
        yaxis=dict(
            range=[y_min, y_max],
            showgrid=True, gridcolor="#eee",
            showticklabels=False
        ),
        plot_bgcolor="#ffffff",
        title=f"<b>核心节点[{core_nodes_str}] 全景依赖关系图</b>",
        title_font_size=22,
        title_x=0.5,
        showlegend=False
    )
    
    return fig

def plot_single_core_graph(target_node, upstream_hierarchy, downstream_hierarchy, 
                           node_basic_info, upstream_edges, downstream_edges, G, 
                           upstream_node_depth, downstream_node_depth, core_node_set):
    """单核心图绘制"""
    max_upstream_depth = max(upstream_hierarchy.keys()) if upstream_hierarchy else 0
    max_downstream_depth = max(downstream_hierarchy.keys()) if downstream_hierarchy else 0
    
    # 坐标计算：核心节点居中
    x_step = 8
    node_coords = {}
    node_coords[target_node] = (0, 0)
    
    # 上游/下游x坐标
    x_coords = {}
    for depth in upstream_hierarchy:
        x_coords[f"up_{depth}"] = -x_step * depth
    for depth in downstream_hierarchy:
        x_coords[f"down_{depth}"] = x_step * depth
    
    # 上游节点布局
    for depth in sorted(upstream_hierarchy.keys()):
        nodes = upstream_hierarchy[depth]
        if not nodes:
            continue
        
        parent_to_children = {}
        for node in nodes:
            children = [c for c in G.successors(node) if c in node_coords]
            parent_to_children[node] = children
        
        def sort_by_child_y(node):
            children = parent_to_children[node]
            if not children:
                return 0
            child_ys = [node_coords[c][1] for c in children]
            return sum(child_ys) / len(child_ys)
        
        sorted_nodes = sorted(nodes, key=sort_by_child_y)
        spacing = 3.5
        start_y = -(len(sorted_nodes) - 1) * spacing / 2
        for i, node in enumerate(sorted_nodes):
            node_coords[node] = (x_coords[f"up_{depth}"], start_y + i * spacing)
    
    # 下游节点布局
    for depth in sorted(downstream_hierarchy.keys()):
        nodes = downstream_hierarchy[depth]
        if not nodes:
            continue
        
        child_to_parents = {}
        for node in nodes:
            parents = [p for p in G.predecessors(node) if p in node_coords]
            child_to_parents[node] = parents
        
        def sort_by_parent_y(node):
            parents = child_to_parents[node]
            if not parents:
                return 0
            parent_ys = [node_coords[p][1] for p in parents]
            return sum(parent_ys) / len(parent_ys)
        
        sorted_nodes = sorted(nodes, key=sort_by_parent_y)
        spacing = 3.5
        start_y = -(len(sorted_nodes) - 1) * spacing / 2
        for i, node in enumerate(sorted_nodes):
            node_coords[node] = (x_coords[f"down_{depth}"], start_y + i * spacing)
    
    # 边绘制
    fig = go.Figure()
    all_edges = upstream_edges + downstream_edges
    edge_x = []
    edge_y = []
    for (parent, child) in all_edges:
        if parent in node_coords and child in node_coords:
            edge_x.extend([node_coords[parent][0], node_coords[child][0], None])
            edge_y.extend([node_coords[parent][1], node_coords[child][1], None])
    
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y,
        mode="lines",
        line=dict(width=2, color="rgba(102, 102, 102, 0.7)"),
        hoverinfo="none",
        marker=dict(size=8, symbol="arrow-right"),
        showlegend=False
    ))
    
    # 节点绘制
    node_x = []
    node_y = []
    node_color = []
    node_size = []
    node_text = []
    node_labels = []
    
    for node in node_coords:
        node_x.append(node_coords[node][0])
        node_y.append(node_coords[node][1])
        info = node_basic_info[node]
        node_color.append(info["node_color"])
        
        if info["is_core"]:
            node_size.append(40)
            node_labels.append(f"核心：{node.split('.')[-1]}")
        else:
            node_size.append(max(18, 30 - (info["final_depth"]-1)*2))
            node_labels.append(node.split('.')[-1])
        
        # 【修改2】悬停信息增加task_name
        node_text.append(
            f"节点：{node}<br>"
            f"类型：{info['final_depth_type']}{info['final_depth'] if info['final_depth']>0 else ''}<br>"
            f"关联Project：{', '.join(info['related_project']) if info['related_project'] else '无'}<br>"
            f"关联TaskName：{', '.join(info['related_task']) if info['related_task'] else '无'}"
        )
    
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        text=node_labels,
        textposition="top center",
        marker=dict(
            color=node_color,
            size=node_size,
            line=dict(width=2, color="black"),
            symbol="circle"
        ),
        hovertext=node_text,
        hoverinfo="text",
        hoverlabel=dict(font_size=12),
        zorder=10,
        showlegend=False
    ))
    
    # 布局
    all_x = [v[0] for v in node_coords.values()] if node_coords else []
    x_min = min(all_x) - 15 if all_x else -20
    x_max = max(all_x) + 15 if all_x else 20
    all_y = [v[1] for v in node_coords.values()] if node_coords else []
    y_min = min(all_y) - 10 if all_y else -20
    y_max = max(all_y) + 10 if all_y else 20
    
    fig.update_layout(
        width=max(2500, x_max - x_min + 600),
        height=max(1600, y_max - y_min + 500),
        hovermode="closest",
        dragmode="pan",
        xaxis=dict(
            range=[x_min, x_max],
            showgrid=True, gridcolor="#eee",
            zeroline=True, zerolinecolor="#4CAF50", zerolinewidth=4,
            showticklabels=False,
            title=f"单节点视图：上游{max_upstream_depth}层 ← 核心[{target_node}] → 下游{max_downstream_depth}层"
        ),
        yaxis=dict(
            range=[y_min, y_max],
            showgrid=True, gridcolor="#eee",
            showticklabels=False
        ),
        plot_bgcolor="#ffffff",
        title=f"<b>核心节点[{target_node}] 独立依赖关系图</b>",
        title_font_size=22,
        title_x=0.5,
        showlegend=False
    )
    
    return fig

# ---------------------- 5. 页面UI（核心交互逻辑） ----------------------
st.title("🔍 核心节点依赖关系查询")
st.divider()

# 初始化会话状态
if "view_mode" not in st.session_state:
    st.session_state.view_mode = "panorama"  # 默认全景图
if "current_single_node" not in st.session_state:
    st.session_state.current_single_node = None
if "selected_nodes" not in st.session_state:
    st.session_state.selected_nodes = []
# 新增：标记是否需要刷新视图（避免多选时频繁重渲染）
if "need_refresh_view" not in st.session_state:
    st.session_state.need_refresh_view = False

with st.sidebar:
    # 1. 数据加载
    st.header("📁 数据加载")
    file_path = st.text_input(
        "输入文件路径（Win：C:\\xxx.xlsx / Linux：/home/xxx.xlsx）",
        placeholder="C:\\Users\\xxx\\data.xlsx"
    )
    uploaded_file = st.file_uploader(
        "或上传文件（CSV/Excel）",
        type=["csv", "xlsx", "xls"]
    )
    st.divider()
    
    df = load_data(file_path, uploaded_file)
    if df is not None:
        # 获取所有节点
        all_nodes = set()
        all_nodes.update(df["source"].dropna().astype(str).unique())
        all_nodes.update(df["target"].dropna().astype(str).unique())
        all_nodes = sorted([n for n in all_nodes if n.strip()])
        
        # 2. 节点选择
        st.header("🔎 选择核心节点")
        input_mode = st.radio("选择方式", ["多选节点", "关键字搜索"], index=0)
        selected_nodes = st.session_state.selected_nodes  # 先读取会话状态
        
        if input_mode == "多选节点":
            # 优化：移除即时更新，改为手动确认
            new_selected = st.multiselect(
                "直接选择节点（按住Ctrl/Command可多选）",
                options=all_nodes,
                placeholder="请选择核心节点...",
                default=selected_nodes,
                key="node_multiselect"
            )
            # 仅当点击确认按钮时才更新选中节点
            if st.button("✅ 确认选择", use_container_width=True):
                st.session_state.selected_nodes = new_selected
                st.session_state.need_refresh_view = True
                # 重置单节点视图（确认选择后回到全景）
                st.session_state.view_mode = "panorama"
                st.session_state.current_single_node = None
        
        else:
            keyword = st.text_input("输入关键字搜索节点", placeholder="例如：resume_delivery")
            matched_nodes = []
            if keyword:
                matched_nodes = [n for n in all_nodes if keyword.lower() in n.lower()]
                st.info(f"匹配到 {len(matched_nodes)} 个节点：{', '.join(matched_nodes[:10])}{'...' if len(matched_nodes)>10 else ''}")
                if st.checkbox(f"选中所有匹配的 {len(matched_nodes)} 个节点"):
                    selected_nodes = matched_nodes
                # 手动确认搜索结果
                if st.button("✅ 确认搜索选择", use_container_width=True):
                    st.session_state.selected_nodes = selected_nodes
                    st.session_state.need_refresh_view = True
                    st.session_state.view_mode = "panorama"
                    st.session_state.current_single_node = None
        
        # 3. 左侧导航栏：已选节点列表（点击切换）
        if st.session_state.selected_nodes:
            st.divider()
            st.header("🎯 已选核心节点")
            st.caption("点击切换单节点视图，再次点击恢复全景")
            
            for node in st.session_state.selected_nodes:
                # 按钮文本高亮当前选中的单节点
                btn_text = f"🔹 {node}" if st.session_state.current_single_node == node else node
                if st.button(btn_text, key=f"btn_{node}", use_container_width=True):
                    if st.session_state.current_single_node == node:
                        # 再次点击：恢复全景
                        st.session_state.view_mode = "panorama"
                        st.session_state.current_single_node = None
                    else:
                        # 第一次点击：切换到单节点
                        st.session_state.view_mode = "single"
                        st.session_state.current_single_node = node
                    # 标记需要刷新视图
                    st.session_state.need_refresh_view = True
                    st.rerun()

# 主内容区域
if df is not None and st.session_state.selected_nodes:
    # 仅当需要刷新或视图切换时才重新计算和渲染
    if st.session_state.view_mode == "panorama":
        # 默认展示全景图
        st.success(f"当前视图：全景（共{len(st.session_state.selected_nodes)}个核心节点）")
        
        # 计算全景数据
        (upstream_hierarchy, downstream_hierarchy, node_basic_info, 
         upstream_edges, downstream_edges, G, upstream_node_depth, 
         downstream_node_depth, core_node_set) = build_panorama_relation(df, st.session_state.selected_nodes)
        
        # 显示节点信息
        st.subheader("📋 全景节点层级信息")
        node_detail = []
        for node in node_basic_info:
            detail = node_basic_info[node]
            node_detail.append({
                "节点名称": node,
                "节点类型": detail["final_depth_type"],
                "层级深度": detail["final_depth"],
                "是否核心": detail["is_core"],
                "关联Project": ", ".join(detail["related_project"]) if detail["related_project"] else "无",
                # 【修改3】表格增加TaskName列
                "关联TaskName": ", ".join(detail["related_task"]) if detail["related_task"] else "无"
            })
        st.dataframe(pd.DataFrame(node_detail), use_container_width=True)
        
        # 显示全景图
        st.divider()
        st.subheader("📊 全景依赖关系可视化")
        fig = plot_panorama_graph(
            st.session_state.selected_nodes, upstream_hierarchy, downstream_hierarchy, 
            node_basic_info, upstream_edges, downstream_edges, G, 
            upstream_node_depth, downstream_node_depth, core_node_set
        )
        st.plotly_chart(fig, use_container_width=True)
    
    else:
        # 单节点视图
        current_node = st.session_state.current_single_node
        st.success(f"当前视图：单节点「{current_node}」（点击左侧该节点可恢复全景）")
        
        # 计算单节点数据
        (upstream_hierarchy, downstream_hierarchy, node_basic_info, 
         upstream_edges, downstream_edges, G, upstream_node_depth, 
         downstream_node_depth, core_node_set) = build_single_core_relation(df, current_node)
        
        # 显示节点信息
        st.subheader(f"📋 {current_node} 节点层级信息")
        node_detail = []
        for node in node_basic_info:
            detail = node_basic_info[node]
            node_detail.append({
                "节点名称": node,
                "节点类型": detail["final_depth_type"],
                "层级深度": detail["final_depth"],
                "关联Project": ", ".join(detail["related_project"]) if detail["related_project"] else "无",
                # 【修改4】表格增加TaskName列
                "关联TaskName": ", ".join(detail["related_task"]) if detail["related_task"] else "无"
            })
        st.dataframe(pd.DataFrame(node_detail), use_container_width=True)
        
        # 显示单节点图
        st.divider()
        st.subheader(f"📊 {current_node} 独立依赖关系可视化")
        fig = plot_single_core_graph(
            current_node, upstream_hierarchy, downstream_hierarchy, 
            node_basic_info, upstream_edges, downstream_edges, G, 
            upstream_node_depth, downstream_node_depth, core_node_set
        )
        st.plotly_chart(fig, use_container_width=True)

elif df is not None and not st.session_state.selected_nodes:
    st.info("💡 请在左侧选择至少一个核心节点，默认展示全景图")

elif df is None:
    st.info("💡 请先上传数据文件或输入有效的文件路径")

# 重置刷新标记
if st.session_state.need_refresh_view:
    st.session_state.need_refresh_view = False