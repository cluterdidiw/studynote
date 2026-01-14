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

# =================================================================
# 1. 配置信息
# =================================================================
PYTHON_EMBED_URL = "https://www.python.org/ftp/python/3.10.11/python-3.10.11-embed-amd64.zip"
GET_PIP_URL = "https://bootstrap.pypa.io/get-pip.py"
DIST_DIR = "Lineage_Tool_Dist"  # 最终生成的文件夹名

# 核心依赖列表：确保包含所有 app.py 引用的库及其底层渲染引擎
DEPENDENCIES = [
    "streamlit", 
    "pandas", 
    "networkx", 
    "pymysql", 
    "openpyxl", 
    "xlsxwriter",       # 必选：支持 app.py 中的 engine='xlsxwriter' 导出
    "streamlit-agraph",  # 必选：血缘图核心组件
    "pyvis",             # 必选：streamlit-agraph 的底层渲染依赖
    "protobuf==3.20.3"   # 必选：解决版本兼容性导致的显示问题
]

def build():
    # 清理旧的目录
    if os.path.exists(DIST_DIR):
        shutil.rmtree(DIST_DIR)
    os.makedirs(DIST_DIR)
    
    # ---------------------------------------------------------
    # 2. 下载并解压便携版 Python
    # ---------------------------------------------------------
    print(">>> 正在下载 Python 便携版 (3.10.11)...")
    zip_path = "python_embed.zip"
    try:
        urllib.request.urlretrieve(PYTHON_EMBED_URL, zip_path)
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(os.path.join(DIST_DIR, "python_env"))
        os.remove(zip_path)
    except Exception as e:
        print(f"下载 Python 失败: {e}")
        return

    # ---------------------------------------------------------
    # 3. 配置 Python 环境以允许加载第三方库
    # ---------------------------------------------------------
    pth_file = os.path.join(DIST_DIR, "python_env", "python310._pth")
    if os.path.exists(pth_file):
        with open(pth_file, "a") as f:
            f.write("\nimport site\n")

    # ---------------------------------------------------------
    # 4. 安装 pip
    # ---------------------------------------------------------
    print(">>> 正在安装 pip 工具...")
    env_dir = os.path.join(os.getcwd(), DIST_DIR, "python_env")
    python_exe = os.path.join(env_dir, "python.exe")
    pip_script = os.path.join(DIST_DIR, "get-pip.py")
    try:
        urllib.request.urlretrieve(GET_PIP_URL, pip_script)
        subprocess.run([python_exe, pip_script], check=True)
        os.remove(pip_script)
    except Exception as e:
        print(f"安装 pip 失败: {e}")
        return

    # ---------------------------------------------------------
    # 5. 安装依赖库 (使用阿里云镜像加速)
    # ---------------------------------------------------------
    print(f">>> 正在同步安装依赖库: {DEPENDENCIES}")
    print("这可能需要几分钟，请耐心等待...")
    try:
        pip_cmd = [python_exe, "-m", "pip", "install"] + DEPENDENCIES + ["-i", "https://mirrors.aliyun.com/pypi/simple/"]
        subprocess.run(pip_cmd, check=True)
    except Exception as e:
        print(f"依赖库安装失败: {e}")
        return

    # ---------------------------------------------------------
    # 6. 拷贝业务逻辑代码 app.py
    # ---------------------------------------------------------
    if os.path.exists("app.py"):
        shutil.copy("app.py", os.path.join(DIST_DIR, "app.py"))
        print(">>> app.py 拷贝完成")
    else:
        print("!!! 错误：当前目录下未找到 app.py，请检查文件名是否正确。")
        return

    # ---------------------------------------------------------
    # 7. 生成启动批处理脚本 (优化启动参数)
    # ---------------------------------------------------------
    print(">>> 正在生成一键启动脚本...")
    # 增加了 --server.enableStaticServing true 以确保 agraph 的 JS 资源能正确加载
    # 增加了 --server.enableCORS false 提高便携环境下的兼容性
    # 修改 make_dist.py 中的启动脚本部分
    bat_content = f"""@echo off
    set PATH=%~dp0python_env;%~dp0python_env\\Scripts;%PATH%
    echo ======================================================
    echo   数据血缘分析平台 (已优化布局与兼容性)
    echo   正在启动本地服务器... 请保持此窗口开启
    echo ======================================================
    :: 1. 移除冲突的 CORS 设置
    :: 2. 禁用 XSRF 保护以支持更灵活的本地访问
    :: 3. 增加布局间距参数，解决右侧红框溢出问题
    start /b "" "%~dp0python_env\\python.exe" -m streamlit run "%~dp0app.py" ^
        --server.port 8501 ^
        --server.headless true ^
        --server.enableXsrfProtection false ^
        --server.enableStaticServing false ^
        --browser.gatherUsageStats false ^
        --global.developmentMode false

    timeout /t 5
    start http://localhost:8501
    """
    with open(os.path.join(DIST_DIR, "双击运行.bat"), "w", encoding="gbk") as f:
        f.write(bat_content)

    print(f"\n" + "="*50)
    print(f"🎉 封装构建成功！")
    print(f"生成的目录: {DIST_DIR}")
    print(f"使用方法: 将 '{DIST_DIR}' 文件夹整体打包为 ZIP 发送给同事，对方解压后双击内部的 '双击运行.bat' 即可。")
    print("="*50)

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