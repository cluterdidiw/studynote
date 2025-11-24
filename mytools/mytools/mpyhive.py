from pyhive import hive
import time
import pandas as pd

def hive_exe(sql: str,db: str = 'temp', host: str = '192.168.101.195', port: int = 10000) -> dict:
    """
    执行Hive DDL命令，返回执行结果
    
    Args:
        db: 数据库名
        sql: DDL语句
        host: Hive地址
        port: Hive端口
    
    Returns:
        执行结果字典（包含状态、耗时、错误信息）
    """
    result = {'status': 'failed', '耗时': 0, '错误': None}
    start = time.time()
    conn = None
    cursor = None
    
    try:
        conn = hive.Connection(host=host, port=port, database=db)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        result['status'] = 'success'
    except Exception as e:
        result['错误'] = str(e)
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        result['耗时'] = round(time.time() - start, 2)
    
    return result



def hive_get(sql: str, db: str = 'temp', host: str = '192.168.101.195', port: int = 10000) -> pd.DataFrame:
    """
    执行Hive查询语句，返回查询结果的DataFrame
    
    Args:
        sql: 查询SQL语句
        db: 数据库名（默认'temp'）
        host: Hive地址
        port: Hive端口
    
    Returns:
        查询结果的DataFrame（查询失败时返回空DataFrame）
    """
    # 初始化空DataFrame（失败时返回）
    result_df = pd.DataFrame()
    start = time.time()
    conn = None
    cursor = None

    try:
        # 建立Hive连接
        conn = hive.Connection(host=host, port=port, database=db)
        # 执行SQL并读取结果到DataFrame
        result_df = pd.read_sql(sql, conn)
        print(f"查询成功，返回 {len(result_df)} 条数据，耗时 {round(time.time() - start, 2)} 秒")

    except Exception as e:
        print(f"查询失败：{str(e)}，耗时 {round(time.time() - start, 2)} 秒")

    finally:
        # 确保资源释放
        if cursor:
            cursor.close()
        if conn:
            conn.close()

    return result_df