import streamlit as st
import pymysql
import pandas as pd
import re

# 1. 页面配置
st.set_page_config(page_title="Hive 元数据查询工具", layout="wide")

# 初始化 Session 状态
if 'history_tables' not in st.session_state:
    st.session_state['history_tables'] = []
if 'current_table' not in st.session_state:
    st.session_state['current_table'] = None

# 2. 数据库连接
DB_CONFIG = {
    "host": "192.168.101.199",
    "user": "dol",
    "password": "dol*123456",
    "database": "hive", 
    "charset": "utf8mb4"
}

@st.cache_data(ttl=300)
def get_data(sql, params=None):
    try:
        conn = pymysql.connect(**DB_CONFIG)
        with conn.cursor() as cursor:
            cursor.execute("SET NAMES utf8mb4")
        df = pd.read_sql(sql, conn, params=params)
        conn.close()
        return df
    except Exception as e:
        st.error(f"数据库访问失败: {e}")
        return pd.DataFrame()

def highlight_keywords(text, keyword):
    if not keyword or pd.isna(text):
        return text
    pattern = re.compile(f"({re.escape(keyword)})", re.IGNORECASE)
    return pattern.sub(r'<span style="color:white; background-color:#FF4B4B; padding:0 2px; border-radius:2px;">\1</span>', str(text))

# --- UI 界面 ---
st.title("🔍 Hive 元数据查询工具")

# 3. 搜索区域
c_input, c_type, c_clear = st.columns([3, 1, 1])
with c_input:
    kw = st.text_input("搜索关键字", placeholder="输入搜索内容...").strip()
with c_type:
    search_mode = st.radio("搜索范围", ["搜表名", "搜字段"], horizontal=True)
with c_clear:
    if st.button("🗑️ 清空选择", use_container_width=True):
        st.session_state['history_tables'] = []
        st.session_state['current_table'] = None
        st.rerun()

# 4. 数据查询逻辑：全量查询，不设 LIMIT
if kw:
    if search_mode == "搜表名":
        list_sql = """
            SELECT DISTINCT d.name as db_name, t.tbl_name as tbl_name, tp.param_value as tbl_comment
            FROM tbls t
            JOIN dbs d ON t.db_id = d.db_id
            LEFT JOIN table_params tp ON t.tbl_id = tp.tbl_id AND tp.param_key = 'comment'
            WHERE t.tbl_name LIKE %s 
            ORDER BY d.name, t.tbl_name
        """
        params = (f"%{kw}%",)
    else:
        list_sql = """
            SELECT DISTINCT d.name as db_name, t.tbl_name as tbl_name, tp.param_value as tbl_comment
            FROM tbls t
            JOIN dbs d ON t.db_id = d.db_id
            JOIN sds s ON t.sd_id = s.sd_id
            JOIN columns_v2 c ON s.cd_id = c.cd_id
            LEFT JOIN table_params tp ON t.tbl_id = tp.tbl_id AND tp.param_key = 'comment'
            WHERE c.column_name LIKE %s OR c.comment LIKE %s
            ORDER BY d.name, t.tbl_name
        """
        params = (f"%{kw}%", f"%{kw}%")
    df_list = get_data(list_sql, params)
else:
    # 默认加载全量库表，不再限制 200
    list_sql = """
        SELECT d.name as db_name, t.tbl_name as tbl_name, tp.param_value as tbl_comment
        FROM tbls t
        JOIN dbs d ON t.db_id = d.db_id
        LEFT JOIN table_params tp ON t.tbl_id = tp.tbl_id AND tp.param_key = 'comment'
        ORDER BY d.name, t.tbl_name
    """
    df_list = get_data(list_sql)

# 5. 左右布局
col_l, col_r = st.columns([1, 2.5])

with col_l:
    # 显示总表数统计
    st.subheader(f"📋 库表列表 ({len(df_list)})")
    if not df_list.empty:
        df_list['display_name'] = df_list.apply(lambda x: f"{x['tbl_name']} ({x['tbl_comment']})" if x['tbl_comment'] else x['tbl_name'], axis=1)
        
        # 按照库名分组
        grouped = df_list.groupby('db_name')
        for db_name, group in grouped:
            # 统计每个库下的表数量
            with st.expander(f"📁 {db_name} ({len(group)})", expanded=False):
                for _, row in group.iterrows():
                    full_name = f"{db_name}.{row['tbl_name']}"
                    # 点击表名：设置为当前焦点，并置顶历史记录
                    if st.button(f"📄 {row['display_name']}", key=f"btn_{full_name}", use_container_width=True):
                        st.session_state['current_table'] = full_name
                        if full_name in st.session_state['history_tables']:
                            st.session_state['history_tables'].remove(full_name)
                        st.session_state['history_tables'].insert(0, full_name)
                        st.rerun()
    else:
        st.warning("无匹配数据")

with col_r:
    # --- 历史记录快速切换区 ---
    if st.session_state['history_tables']:
        st.write("🕒 **最近查看 (点击切换):**")
        # 顶部横向显示最近 6 个历史记录
        hists = st.session_state['history_tables'][:6]
        cols = st.columns(len(hists) if len(hists) > 0 else 1)
        for idx, hist_name in enumerate(hists):
            # 短表名显示，节省空间
            short_name = hist_name.split('.')[-1]
            if cols[idx].button(f"{short_name}", key=f"hist_{hist_name}", use_container_width=True):
                st.session_state['current_table'] = hist_name
                st.rerun()
        st.divider()

    # --- 核心详情区 ---
    if st.session_state['current_table']:
        name = st.session_state['current_table']
        db_n, tbl_n = name.split(".")
        
        st.subheader(f"📍 当前表详情: {name}")
        
        # 包含普通字段和分区字段的 SQL
        det_sql = """
            SELECT res.idx as `序号`, res.col_name as `字段名`, res.col_type as `类型`, 
                   res.col_comment as `注释`, res.is_partition as `是否分区`
            FROM (
                SELECT c.integer_idx + 1 as idx, c.column_name as col_name, 
                       c.type_name as col_type, c.comment as col_comment, '否' as is_partition
                FROM columns_v2 c
                JOIN sds s ON c.cd_id = s.cd_id
                JOIN tbls t ON s.sd_id = t.sd_id
                JOIN dbs d ON t.db_id = d.db_id
                WHERE d.name = %s AND t.tbl_name = %s
                UNION ALL
                SELECT pk.integer_idx + 100, pk.pkey_name, pk.pkey_type, pk.pkey_comment, '是'
                FROM partition_keys pk
                JOIN tbls t ON pk.tbl_id = t.tbl_id
                JOIN dbs d ON t.db_id = d.db_id
                WHERE d.name = %s AND t.tbl_name = %s
            ) res ORDER BY res.is_partition ASC, res.idx ASC
        """
        df_col = get_data(det_sql, (db_n, tbl_n, db_n, tbl_n))
        
        if not df_col.empty:
            # 下载按钮
            csv_data = df_col.to_csv(index=False).encode('utf-8-sig')
            st.download_button(f"📥 导出 {tbl_n} 结构", csv_data, f"{name}.csv", "text/csv")
            
            # 高亮展示
            display_df = df_col.copy()
            if kw:
                display_df['字段名'] = display_df['字段名'].apply(lambda x: highlight_keywords(x, kw))
                display_df['注释'] = display_df['注释'].apply(lambda x: highlight_keywords(x, kw))
            
            # 使用 HTML 渲染以支持高亮颜色
            st.markdown(display_df.to_html(escape=False, index=False), unsafe_allow_html=True)
        else:
            st.warning("⚠️ 未找到字段详情，请检查表名或权限。")
    else:
        st.info("💡 操作提示：在左侧列表中点击具体表名，详情将立即在此显示。")