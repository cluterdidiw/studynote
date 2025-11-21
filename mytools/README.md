# 说明

mytools中存放常用的函数或者类
## pyhive.py

```
from mytools import mpyhive
```
### hive_exe
用于到hive里执行DDL语句。

参数:
- db: str = 'temp', 
- host: str = '192.168.101.195', 
- port: int = 10000
其中，db host port三个参数是北极星的服务器。

# 示例

``` python
exe_res = hive_exe("CREATE TABLE IF NOT EXISTS temp_test_wh_py  as select * from ads.ads_slot_show_click_statistics limit 1000")

```

### hive_get
用于到hive里执行查询语句，并将获取数据返回Dataframe。

参数:
- db: str = 'temp', 
- host: str = '192.168.101.195', 
- port: int = 10000
其中，db host port三个参数是北极星的服务器。




``` python

# 示例
df = hive_get("SELECT * FROM temp_tbname LIMIT 10")

```



## dataeda.py

```
from mytools import dataeda
```
### my_unique_pivot
用于重复计数，计算指定DataFrame中行列交叉的非重复值数量及百分比。

参数:
- df (pd.DataFrame): 输入的DataFrame
- index_col (str or list): 作为行索引的列名（可选，支持多列）
- columns_col (str or list): 作为列索引的列名（可选，支持多列）
- values_col (str): 需要计算非重复数量的列名（必填）
- pct_base (str): 百分比计算基准，可选值：
    + 'total'：除以整体唯一值数量（默认）
    + 'row'：除以行总计
    + 'col'：除以列总计

返回:
- tuple: (count_pivot, pct_pivot)
    + count_pivot: 非重复计数值（含总计）
    + pct_pivot: 对应百分比（保留两位小数）

``` python

# 示例
data = {
    '地区': ['华东', '华东', '华北', '华北', '华南', '华东', '华北'],
    '产品': ['A', 'B', 'A', 'B', 'A', 'A', 'C'],
    '用户ID': [101, 102, 101, 103, 104, 105, 101]
}
df = pd.DataFrame(data)

# 1. 按总体总计计算百分比（默认）
count_df, pct_total = my_unique_pivot(
    df, index_col='地区', values_col='用户ID', pct_base='total'
)

# 2. 按行总计计算百分比（行内占比）
_, pct_row = my_unique_pivot(
    df, index_col='地区', values_col='用户ID', pct_base='row'
)

# 3. 按列总计计算百分比（列内占比）
_, pct_col = my_unique_pivot(
    df, index_col='地区', values_col='用户ID', pct_base='col'
)

print("非重复计数值：")
print(count_df)
print("\n按总体总计的百分比：")
print(pct_total)
print("\n按行总计的百分比：")
print(pct_row)
print("\n按列总计的百分比：")
print(pct_col)

```
