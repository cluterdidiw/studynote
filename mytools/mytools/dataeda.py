import pandas as pd

def calculate_unique_pivot(df, index_col, columns_col, values_col, pct_base='total'):
    # 校验百分比基准参数
    if pct_base not in ['total', 'row', 'col']:
        raise ValueError("pct_base参数必须为'total'、'row'或'col'")

    # 计算交叉非重复值数量（包含总计）
    count_pivot = df.pivot_table(
        index=index_col,
        columns=columns_col,
        values=values_col,
        aggfunc=lambda x: x.nunique(),  # 计算非重复值数量
        fill_value=0,
        margins=True,                   # 开启总计
        margins_name='总计'              # 自定义总计名称
    )

    # 计算百分比
    if pct_base == 'total':
        # 除以总体总计（即"总计"行和"总计"列的交叉值）
        total = count_pivot.loc['总计', '总计']
        pct_pivot = count_pivot.div(total) * 100

    elif pct_base == 'row':
        # 除以行总计（每行的"总计"列值）
        row_totals = count_pivot['总计']
        pct_pivot = count_pivot.div(row_totals, axis=0) * 100

    else:  # pct_base == 'col'
        # 除以列总计（每列的"总计"行值）
        col_totals = count_pivot.loc['总计']
        pct_pivot = count_pivot.div(col_totals, axis=1) * 100

    # 保留两位小数并处理可能的NaN（当除数为0时）
    pct_pivot = pct_pivot.round(2).fillna(0)

    return count_pivot, pct_pivot
