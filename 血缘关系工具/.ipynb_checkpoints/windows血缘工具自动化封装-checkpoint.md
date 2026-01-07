既然是提供给非技术部门，我们需要将复杂的环境配置自动化。我为您准备了一个自动化封装脚本。

这个脚本会自动下载 Python 便携版，安装所有必要的库（Pandas, Streamlit, PyMySQL等），并将您的 app.py 整合在一起，最终生成一个可以直接分发的压缩包。

1. 自动化封装工具 (make_dist.py)
请在您**自己的电脑（有 Python 和网络的环境）**上新建一个 make_dist.py，将以下代码贴进去运行：

``` Python
import os
import subprocess
import urllib.request
import zipfile
import shutil

# 配置信息
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
DIST_DIR = "Lineage_Tool_Dist"  # 最终生成的文件夹名

# 核心依赖：增加了 xlsxwriter 用于导出功能
DEPENDENCIES = [
    "streamlit", 
    "pandas", 
    "networkx", 
    "plotly", 
    "pymysql", 
    "openpyxl", 
    "xlsxwriter"  # 必须包含此项以支持导出 Excel
]

def build():
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)
    
    # 1. 下载并解压便携版 Python
    print("正在下载 Python 便携版...")
    zip_path = "python_embed.zip"
    try:
        urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.join(DIST_DIR, "python_env"))
        os.remove(zip_path)
    except Exception as e:
        print(f"下载 Python 失败: {e}")
        return

    # 2. 修改 python310._pth 允许加载 site-packages
    pth_file = os.path.join(DIST_DIR, "python_env", "python310._pth")
    if os.path.exists(pth_file):
        with open(pth_file, "a") as f:
            f.write("\nimport site\n")

    # 3. 安装 pip
    print("正在安装 pip...")
    env_dir = os.path.join(os.getcwd(), DIST_DIR, "python_env")
    python_exe = os.path.join(env_dir, "python.exe")
    pip_script = os.path.join(DIST_DIR, "get-pip.py")
    urllib.request.urlretrieve(GET_PIP_URL, pip_script)
    subprocess.run([python_exe, pip_script], check=True)
    os.remove(pip_script)

    # 4. 安装所有依赖库 (包含 xlsxwriter)
    print(f"正在安装依赖库 {DEPENDENCIES}，这可能需要几分钟...")
    subprocess.run([python_exe, "-m", "pip", "install"] + DEPENDENCIES, check=True)

    # 5. 拷贝整合了中间穿透和导出功能的 app.py
    if os.path.exists("app.py"):
        shutil.copy("app.py", os.path.join(DIST_DIR, "app.py"))
    else:
        print("错误：未找到 app.py 文件！请确保它在当前目录下。")

    # 6. 生成启动脚本
    print("正在生成启动脚本...")
    bat_content = f"""@echo off
set PATH=%~dp0python_env;%~dp0python_env\\Scripts;%PATH%
echo ========================================
echo   数据血缘分析平台 (已集成穿透与导出)
echo   正在启动... 请勿关闭此窗口
echo ========================================
start /b "" "%~dp0python_env\\python.exe" -m streamlit run "%~dp0app.py" --server.port 8501 --server.headless true
timeout /t 5
start http://localhost:8501
"""
    with open(os.path.join(DIST_DIR, "双击运行.bat"), "w", encoding="gbk") as f:
        f.write(bat_content)

    print(f"\n🎉 封装完成！")
    print(f"请将文件夹 '{DIST_DIR}' 压缩为 ZIP 发送给同事。")

if __name__ == "__main__":
    build()
```
2. 如何使用这个工具？
准备环境：确保你的目录下有：

你整合好的 app.py（代码见之前的回复）。

这个 make_dist.py。

执行命令：运行 python make_dist.py。

得到结果：程序运行结束后，会多出一个 Lineage_Tool_Dist 文件夹。

分发给同事：直接把这个文件夹压缩成 .zip 发给非技术部门的同事。

3. 给非技术同事的“懒人版”使用说明
您可以直接复制这段话作为交付说明：

数据血缘分析平台 - 快速上手指南

解压缩：收到文件后，请右键选择“解压到当前文件夹”（重要：请勿在压缩包内直接双击）。

运行：进入文件夹，双击运行 双击运行.bat。

等待：此时会弹出一个黑色的命令行窗口（这是后台服务器，请不要关闭），几秒钟后，您的浏览器会自动弹出分析界面。

常见问题：

如果浏览器没弹出，请手动在地址栏输入：http://localhost:8501。

如果提示无法连接数据库，请检查您的电脑是否连接了公司 VPN 或内网。

4. 为什么这个方案对他们最友好？
零配置：他们不需要知道 Python 是什么，也不需要配环境变量。

不污染系统：这是一个绿色软件，删掉文件夹就彻底卸载了，不会在他们的系统里留下垃圾文件。

内网友好：因为它保留了完整的 Python 网络功能，所以连接 192.168.101.199 数据库的稳定性是最高的。

您可以先用这个脚本封装一下您的 app.py 试试看，如有任何报错请随时告诉我！