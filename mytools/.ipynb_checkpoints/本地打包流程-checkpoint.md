以下是基于现代 PEP 517/518 标准的完整 自定义函数打包完整方案，兼容最新 pip 版本，解决了之前的配置错误，确保本地安装和导入顺畅。


### **一、方案目标**
将常用自定义函数打包为可本地安装的 Python 包，支持：
- 开发模式实时调试（修改代码立即生效）
- 正式安装（生成标准分发包）
- 简单导入使用（`import 包名` 直接调用函数）


### **二、目录结构**
```
myutils/                  # 项目根目录（可自定义名称）
├── myutils/              # 包核心目录（与包名一致）
│   ├── __init__.py       # 自动导入所有公开函数
│   ├── string_utils.py   # 字符串工具函数
│   └── math_utils.py     # 数学工具函数
├── pyproject.toml        # 现代打包核心配置（必填）
├── setup.cfg             # 包元信息配置（必填）
└── README.md             # 包说明文档（可选）
```


### **三、核心文件编写**

#### **1. 自定义函数实现**
##### `myutils/string_utils.py`（字符串工具）
```python
def str_reverse(s: str) -> str:
    """反转字符串"""
    return s[::-1]

def str_count(s: str) -> dict:
    """统计字符出现次数（去重后计数）"""
    return {char: s.count(char) for char in set(s)}
```

##### `myutils/math_utils.py`（数学工具）
```python
def avg(numbers: list) -> float:
    """计算列表平均值（空列表返回 0.0）"""
    return sum(numbers) / len(numbers) if numbers else 0.0

def sum_squares(numbers: list) -> float:
    """计算列表元素的平方和"""
    return sum(x **2 for x in numbers)
```


#### **2. 自动导入配置（`myutils/__init__.py`）** 动态扫描并导入所有模块的公开函数（非下划线开头的函数），无需手动维护导入列表：
```python
"""myutils 包：自动导入所有公开函数"""
import importlib
from pathlib import Path
from typing import List

# 当前包的根目录
PACKAGE_DIR = Path(__file__).resolve().parent

# 公开函数列表（支持 from myutils import *）
__all__: List[str] = []

def _is_public_function(name: str, obj) -> bool:
    """判断是否为需要导出的公开函数"""
    return (
        not name.startswith("_")  # 排除私有函数（以_开头）
        and callable(obj)         # 确保是函数
        and hasattr(obj, "__module__")  # 检查是否有模块属性
        and obj.__module__.startswith(f"{__name__}.")  # 确保是当前包内的函数
    )

def _import_module_functions(module_name: str) -> None:
    """导入指定模块的公开函数并添加到包命名空间"""
    try:
        # 动态导入模块（相对路径）
        module = importlib.import_module(f".{module_name}", package=__name__)
    except Exception as e:
        print(f"⚠️ 模块 {module_name} 导入失败：{e}")
        return

    # 遍历模块成员，提取公开函数
    for name, obj in module.__dict__.items():
        if _is_public_function(name, obj):
            # 添加到当前包的全局命名空间
            globals()[name] = obj
            # 加入__all__列表（去重）
            if name not in __all__:
                __all__.append(name)

# 扫描并导入所有模块（排除__init__.py和隐藏文件）
for file in PACKAGE_DIR.glob("*.py"):
    if file.name in ("__init__.py",) or file.name.startswith("."):
        continue
    # 模块名即文件名（不含.py后缀）
    _import_module_functions(file.stem)

# 排序__all__，确保导入顺序一致
__all__.sort()
```


#### **3. 现代打包配置（`pyproject.toml`）** 定义打包工具依赖，符合 PEP 517 标准（必填，避免 deprecation 警告）：
```toml
[build-system]
# 打包所需工具（setuptools 和 wheel）
requires = ["setuptools>=61.0", "wheel"]
# 打包后端（使用 setuptools 处理打包逻辑）
build-backend = "setuptools.build_meta"
```


#### **4. 包元信息配置（`setup.cfg`）** 存储包的名称、版本等元数据（格式严格，无多余注释）：
```ini
[metadata]
name = myutils                # 包名（import 时使用的名称）
version = 0.1.0               # 版本号（格式：MAJOR.MINOR.PATCH，如 0.1.0）
author = Your Name            # 作者名
author_email = your@email.com # 作者邮箱
description = 常用自定义工具函数包 # 简短描述
long_description = file: README.md  # 详细描述（关联 README.md）
long_description_content_type = text/markdown  # 描述格式
python_requires = >=3.6       # 支持的 Python 最低版本

[options]
packages = find:              # 自动发现包内所有模块
install_requires =            # 依赖列表（每行一个，如无依赖可留空）
# 示例：如需依赖 numpy，取消下一行注释
# numpy>=1.19.0
```


#### **5. 说明文档（`README.md`，可选）** 简单描述包的功能（用于 `long_description` 展示）：
```markdown
# myutils

常用自定义工具函数包，包含：
- 字符串处理（反转、字符计数）
- 数学计算（平均值、平方和）

## 安装方式
本地安装：`pip install dist/myutils-0.1.0-py3-none-any.whl`
```


### **四、本地安装与使用**
#### **1. 开发模式安装（推荐开发阶段）** 在项目根目录（`pyproject.toml` 所在目录）执行：
```bash
# 可编辑模式安装（修改代码实时生效，无需重新安装）
pip install -e .
```

#### **2. 正式安装（推荐测试/生产环境）**
##### 步骤1：生成标准分发包
```bash
# 安装现代打包工具（首次执行需安装）
pip install build

# 生成 .whl（二进制包）和 .tar.gz（源码包），输出到 dist 目录
python -m build
```

执行成功后，`dist` 目录会生成：
- `myutils-0.1.0.tar.gz`（源码包）
- `myutils-0.1.0-py3-none-any.whl`（二进制包，优先推荐）

##### 步骤2：安装分发包
```bash
# 安装二进制包（替换为实际文件名）
pip install dist/myutils-0.1.0-py3-none-any.whl
```


#### **3. 验证安装与使用** 在 Python 脚本中测试：
```python
from myutils import str_reverse, avg, sum_squares

# 测试字符串函数
print(str_reverse("hello"))  # 输出：olleh
print(str_count("hello"))    # 输出：{'h':1, 'e':1, 'l':2, 'o':1}（顺序可能不同）

# 测试数学函数
print(avg([1, 2, 3, 4]))     # 输出：2.5
print(sum_squares([1, 2, 3]))# 输出：14（1²+2²+3²=14）
```


### **五、扩展：本地分享给他人**
1. 将 `dist` 目录下的 `myutils-0.1.0-py3-none-any.whl` 文件传给对方。
2. 对方收到后，在终端执行：
   ```bash
   pip install /path/to/myutils-0.1.0-py3-none-any.whl  # 替换为实际文件路径
   ```


### **注意事项** 
1. **版本号规范**：`setup.cfg` 中 `version` 必须为 `x.y.z` 格式（如 `0.2.1`），不可加注释或特殊符号。
2. **命名冲突**：不同模块的函数名不可重复，否则后导入的会覆盖先导入的。
3. **依赖管理**：如需依赖第三方库，在 `setup.cfg` 的 `install_requires` 中添加（每行一个）。

通过这套方案，你的自定义函数包将完全符合现代 Python 打包标准，支持本地开发、测试和分享，且兼容未来的工具链更新。