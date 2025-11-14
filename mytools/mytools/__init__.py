"""
mytools 包初始化文件
自动扫描并导入包内所有模块的公开函数（非下划线开头的函数）
"""

import os
import importlib
from pathlib import Path
from typing import List

# 获取当前包的路径（__init__.py 所在目录）
PACKAGE_DIR = Path(__file__).resolve().parent

# 存储所有公开可导入的函数/对象名称（用于 from mytools import *）
__all__: List[str] = []

def _is_public_function(name: str, obj) -> bool:
    """判断是否为需要导出的公开函数"""
    # 排除私有成员（以_开头）
    if name.startswith("_"):
        return False
    # 确保是函数类型
    if not callable(obj):
        return False
    # 排除内置函数和从其他模块导入的函数
    if hasattr(obj, "__module__"):
        # 只保留当前包内定义的函数
        return obj.__module__.startswith(f"{__name__}.")
    return False

def _import_module_functions(module_name: str) -> None:
    """导入指定模块的公开函数并添加到当前包命名空间"""
    try:
        # 动态导入模块（相对导入）
        module = importlib.import_module(f".{module_name}", package=__name__)
    except ImportError as e:
        print(f"⚠️ 警告：模块 {module_name} 导入失败 - {str(e)}")
        return
    except Exception as e:
        print(f"⚠️ 警告：处理模块 {module_name} 时出错 - {str(e)}")
        return

    # 遍历模块成员，提取公开函数
    for name, obj in module.__dict__.items():
        if _is_public_function(name, obj):
            # 添加到当前包的全局命名空间
            globals()[name] = obj
            # 添加到__all__列表
            if name not in __all__:
                __all__.append(name)

# 扫描并导入所有模块
for file_path in PACKAGE_DIR.glob("*.py"):
    # 跳过自身和隐藏文件
    if file_path.name in ("__init__.py",) or file_path.name.startswith("."):
        continue
    
    # 模块名（不带.py后缀）
    module_name = file_path.stem
    _import_module_functions(module_name)

# 对__all__排序，确保导入顺序一致
__all__.sort()

# 打印导入信息（可选，调试用）
if os.environ.get("MYUTILS_DEBUG") == "1":
    print(f"✅ myutils 包初始化完成，导入公开函数：{__all__}")
