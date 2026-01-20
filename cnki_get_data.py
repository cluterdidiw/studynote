import re
import time
from datetime import datetime
from typing import List, Dict

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


# ======================= 基本配置 =======================
JOURNAL_URL = (
    "https://navi.cnki.net/knavi/detail?"
    "p=AcKg9NN3ni_D8yimk-mXlngB9EW9zzPE3j-uoDJJvE5ttdE3jVshMzbKqyOdyB20wSL9yq2KqbumaQVFCT5QDbmBN5JOCrGYdDRS8h60xA-6vXjTO0tOyQ=="
    "&uniplatform=NZKPT"
)

START_YEAR = 2022
END_YEAR = 2025

OUTPUT_EXCEL = "cnki_2022_2025.xlsx"

# 调试开关：仅在第一期输出详细结构日志，确认解析是否正确
DEBUG_FIRST_ISSUE = False

# Headless 模式开关：True=后台运行（不显示浏览器），False=显示浏览器窗口（便于调试）
USE_HEADLESS = False

# ======================= 期数 → 映射期数 =======================
def num_to_issue_code(n: int) -> str:
    """把期号 No.xx 转成形如 01A / 01B / 01C / 02A ... 的“期数”编码。

    规则（与你反馈一致）：
      - No.01 -> 01A
      - No.02 -> 01B
      - No.03 -> 01C
      - No.04 -> 02A
      - No.05 -> 02B
      - No.06 -> 02C
      ...
    """
    group = (n - 1) // 3 + 1
    suffix = "ABC"[(n - 1) % 3]
    return f"{group:02d}{suffix}"


def map_issue(issue_code: str) -> str:
    """
    输入“期数”如 '01A'，输出“映射期数”。

    你给出的部分规则：
        01A -> 01A
        02A -> 01B
        03A -> 01C
        04A -> 02A
        05A -> 03B
        06A -> 02C
        ……以此类推

    目前实现方式：
    1）先按“每 3 期一组，组内 A/B/C”生成一个默认映射；
    2）再用你给的前 6 条规则做覆盖。
    """
    m = re.match(r"^(\d{2})([A-Z])$", issue_code)
    if not m:
        return issue_code

    num = int(m.group(1))

    # 默认规则：01A,02A,03A,... 视为按时间顺序的第1,2,3期
    default_group = (num - 1) // 3 + 1          # 1,1,1,2,2,2,3,3,3,...
    idx = (num - 1) % 3                         # 0,1,2 -> A,B,C
    default_suffix = "ABC"[idx]
    default_mapped = f"{default_group:02d}{default_suffix}"

    overrides = {
        "01A": "01A",
        "02A": "01B",
        "03A": "01C",
        "04A": "02A",
        "05A": "03B",
        "06A": "02C",
    }
    return overrides.get(issue_code, default_mapped)


# ======================= Selenium 初始化 =======================
def init_driver() -> webdriver.Chrome:
    chrome_options = Options()
    if USE_HEADLESS:
        # 启用无头模式，后台运行
        chrome_options.add_argument("--headless=new")
        print("使用 Headless 模式（后台运行）")
    else:
        print("使用正常模式（显示浏览器窗口）")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1400,900")

    driver = webdriver.Chrome(options=chrome_options)
    driver.implicitly_wait(5)
    return driver


# ======================= DOM 操作工具 =======================
def click_js(driver, element):
    """用 JS click，兼容性更好。"""
    driver.execute_script("arguments[0].click();", element)
    time.sleep(1.0)


def click_issue_js(driver, element):
    """专门用于点击左侧期次，尽量触发页面自己的 JS 逻辑。"""
    try:
        # 优先调用页面上的 JournalDetail.BindIssueClick
        driver.execute_script("JournalDetail.BindIssueClick(arguments[0]);", element)
    except Exception:
        # 兜底方案：普通 click 或 JS click
        try:
            element.click()
        except Exception:
            driver.execute_script("arguments[0].click();", element)
    # 稍微等久一点，方便观察期次和目录是否真的变化
    time.sleep(2.0)


def get_year_elements(driver) -> Dict[int, object]:
    """
    根据你截图的结构：
      <div id="YearIssueTree" class="s-datalistbox">
        <div id="page1" style="display:block">
          <dl id="2025_Year_Issue" class="s-datalist clearfix">
            <dt onclick="JournalDetail.BindYearClick(this);">
              <em>2025</em>
    解析出 {年份: dt元素}
    """
    year_map: Dict[int, object] = {}

    # 尝试多种选择器策略
    selectors = [
        "div#YearIssueTree div#page1 dl[id$='_Year_Issue']",
        "div#YearIssueTree dl[id$='_Year_Issue']",
        "div.yearissuepage dl[id$='_Year_Issue']",
    ]
    
    year_dls = []
    for selector in selectors:
        try:
            year_dls = driver.find_elements(By.CSS_SELECTOR, selector)
            if year_dls:
                break
        except Exception:
            continue

    if not year_dls:
        return year_map

    for dl in year_dls:
        try:
            dt = dl.find_element(By.TAG_NAME, "dt")
            em = dt.find_element(By.TAG_NAME, "em")
            text = em.text.strip()
            if text.isdigit():
                y = int(text)
                year_map[y] = dt
        except Exception:
            continue

    return year_map


def get_issue_elements_for_year(driver, year: int) -> List[object]:
    """
    你截图中的期列表（简化）：
      <div id="yearissue0" class="yearissuepage">
        <dl id="2022_Year_Issue" class="s-datalist clearfix cur">
          <dt ...>2022</dt>
          <dd> <a ...>No.36</a> ... </dd>
        </dl>
        <dl id="2023_Year_Issue" ...> ... </dl>
        ...

    注意：yearissue0 下会同时存在多年的 dl，如果直接在 yearissue0 上找 a，
    会把所有年份的期次混在一起（你看到的“541 期”就是这个原因）。

    这里只在当前年份对应的 dl（如 2022_Year_Issue）下取 a。
    """
    try:
        year_dl = driver.find_element(By.ID, f"{year}_Year_Issue")
    except Exception:
        return []

    issue_links = year_dl.find_elements(By.CSS_SELECTOR, "dd a[onclick*='BindIssueClick']")

    # 按页面顺序返回
    return issue_links


def parse_article_list_with_selenium(driver) -> List[Dict]:
    """
    使用 Selenium 直接从当前 DOM 解析右侧"当前期"的文章列表，
    避免 page_source / BeautifulSoup 可能带来的差异。

    结构（来自你的截图）：
      <dl id="cataLogContentJ_list" class="list clearfix">
        <dt class="tit">某栏目</dt>
        <dd class="row clearfix bgcGray">
          <span class="name">
            <a ...>文章标题</a>
        (接着多个 dd.row，直到下一个 dt.tit)
    """
    global DEBUG_FIRST_ISSUE
    result: List[Dict] = []
    dl = None

    # 优先按原来的 id 查找
    try:
        dl = driver.find_element(By.ID, "cataLogContentJ_list")
    except Exception:
        dl = None

    # 如果找不到，退而求其次：在右侧目录容器中找第一个 dl.list
    if dl is None:
        try:
            right_container = driver.find_element(By.ID, "rightCataloglist")
            dls = right_container.find_elements(
                By.CSS_SELECTOR, "dl[class*='list']"
            )
            if dls:
                dl = dls[0]
        except Exception:
            dl = None

    if dl is None:
        if DEBUG_FIRST_ISSUE:
            print("    [调试] 未找到文章列表 dl 元素")
        return result

    # 遍历 dl 下所有后代元素（包括 div / dt / dd），保持“栏目 dt” 与后续 dd 的对应关系
    elements = dl.find_elements(By.XPATH, ".//*")

    if DEBUG_FIRST_ISSUE:
        print("    [调试] cataLogContentJ_list 后代节点数量：", len(elements))
    current_column = ""

    for idx, el in enumerate(elements):
        tag = el.tag_name.lower()
        classes = (el.get_attribute("class") or "").split()

        if DEBUG_FIRST_ISSUE and idx < 25:
            print(f"      [节点{idx}] tag={tag}, class={' '.join(classes)}")

        if tag == "dt" and "tit" in classes:
            current_column = el.text.strip()
            continue

        if tag == "dd" and "row" in classes:
            try:
                name_span = el.find_element(By.CSS_SELECTOR, "span.name")
                a = name_span.find_element(By.TAG_NAME, "a")
                title = a.text.strip()
            except Exception:
                continue

            if not title:
                continue

            result.append(
                {
                    "栏目": current_column,
                    "文章标题": title,
                }
            )

    if DEBUG_FIRST_ISSUE:
        print("    [调试] 本次从 DOM 解析到文章条数：", len(result))
        # 只在第一次期次解析时打印，后续不再输出
        DEBUG_FIRST_ISSUE = False

    return result


# ======================= 抓取主流程 =======================
def crawl_journal() -> pd.DataFrame:
    driver = init_driver()
    print("正在加载页面...")
    driver.get(JOURNAL_URL)
    # 给页面和 JS 更多时间完全加载（headless 模式下可能需要更长时间）
    print("等待页面完全加载...")
    time.sleep(8)

    all_rows = []

    try:
        # 先切换到"刊期浏览"这个 Tab（li id="selectjournal"），否则 YearIssueTree 不会出现在 DOM 中
        tab_clicked = False
        print("尝试切换到刊期浏览 Tab...")
        
        # 优先使用纯 JavaScript 切换，避免 headless 模式下的点击问题
        try:
            time.sleep(3)  # 等待页面稳定
            # 直接通过 JS 触发 Tab 点击事件
            driver.execute_script("""
                (function() {
                    var tab = document.getElementById('selectjournal');
                    if (tab) {
                        // 触发点击事件
                        if (tab.onclick) {
                            tab.onclick();
                        } else {
                            tab.click();
                        }
                        // 也尝试调用页面的切换函数
                        if (typeof JournalDetail !== 'undefined' && JournalDetail.BindTabClick) {
                            JournalDetail.BindTabClick(tab);
                        }
                        return true;
                    }
                    return false;
                })();
            """)
            tab_clicked = True
            print("通过 JavaScript 切换 Tab")
        except Exception as e:
            print(f"JavaScript 切换失败：{e}，尝试 Selenium 点击...")
            # 如果 JS 失败，再尝试 Selenium 点击
            try:
                tab_elem = WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "selectjournal"))
                )
                click_js(driver, tab_elem)
                tab_clicked = True
                print("通过 Selenium 点击切换 Tab")
            except Exception as e2:
                print(f"Selenium 点击也失败：{e2}")
        
        # 等待 YearIssueTree 加载完成
        if tab_clicked:
            print("等待年份树加载...")
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_element_located((By.ID, "YearIssueTree"))
                )
                time.sleep(3)  # 再等待一下，确保年份列表渲染完成
                print("Tab 切换成功，年份树已加载")
            except Exception as e:
                print(f"警告：年份树加载超时：{e}")
        else:
            print("警告：Tab 切换失败，但继续尝试检测年份（可能页面已默认显示）")

        # 检测年份（即使 Tab 切换失败也尝试）
        print("开始检测年份...")
        year_elements = get_year_elements(driver)
        print("首次检测到年份：", sorted(year_elements.keys()))
        
        # 如果年份列表为空，尝试多种策略
        if not year_elements:
            print("年份列表为空，尝试其他策略...")
            
            # 策略1：等待更长时间后重试
            print("  策略1：等待 8 秒后重试...")
            time.sleep(8)
            year_elements = get_year_elements(driver)
            if year_elements:
                print("  策略1成功，检测到年份：", sorted(year_elements.keys()))
            
            # 策略2：如果还是空，尝试通过 JS 强制触发 Tab 切换
            if not year_elements:
                print("  策略2：通过 JS 强制切换 Tab...")
                try:
                    driver.execute_script("""
                        (function() {
                            var tab = document.getElementById('selectjournal');
                            if (tab) {
                                var event = new MouseEvent('click', {
                                    view: window,
                                    bubbles: true,
                                    cancelable: true
                                });
                                tab.dispatchEvent(event);
                                if (typeof JournalDetail !== 'undefined' && JournalDetail.BindTabClick) {
                                    JournalDetail.BindTabClick(tab);
                                }
                            }
                        })();
                    """)
                    print("  等待 10 秒让页面响应...")
                    time.sleep(10)
                    year_elements = get_year_elements(driver)
                    if year_elements:
                        print("  策略2成功，检测到年份：", sorted(year_elements.keys()))
                except Exception as e:
                    print(f"  策略2失败：{e}")
            
            # 策略3：最后尝试一次，等待更长时间
            if not year_elements:
                print("  策略3：最后等待 15 秒后重试...")
                time.sleep(15)
                year_elements = get_year_elements(driver)
                if year_elements:
                    print("  策略3成功，检测到年份：", sorted(year_elements.keys()))
            
            print("最终检测到年份：", sorted(year_elements.keys()))
            
            # 如果最终还是检测不到，输出调试信息
            if not year_elements:
                print("错误：无法检测到年份，可能的原因：")
                print("  1. 页面加载不完整")
                print("  2. 需要登录或验证")
                print("  3. 网络连接问题")
                print("  建议：尝试禁用 headless 模式查看实际情况")

        for year in range(START_YEAR, END_YEAR + 1):
            dt_for_year = year_elements.get(year)
            if not dt_for_year:
                print(f"年份 {year} 在页面中未找到，跳过")
                continue

            print(f"\n{'='*60}")
            print(f"处理年份: {year}")
            print(f"{'='*60}")
            click_js(driver, dt_for_year)

            # 等待当前年份对应的 dl（如 2022_Year_Issue）渲染出来
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located(
                        (By.ID, f"{year}_Year_Issue")
                    )
                )
            except Exception:
                print(f"年份 {year} 的期次列表未加载成功，跳过")
                continue

            issue_links = get_issue_elements_for_year(driver, year)
            total_issues = len(issue_links)
            print(f"  年 {year} 共检测到 {total_issues} 期")

            year_article_count = 0  # 统计本年文章总数

            # 遍历本年的每一期
            for issue_idx, issue_el in enumerate(issue_links, start=1):
                # 期次链接文本形如 "No.36" / "No.01"，从中解析真实 No 号
                txt = (issue_el.text or "").strip()
                m = re.search(r"No\.(\d+)", txt, flags=re.IGNORECASE)
                if not m:
                    print(f"    未能从期次文本解析 No 号：{txt}，跳过")
                    continue
                no_num = int(m.group(1))
                
                # 真实期数：保存页面上的原始文本，如 "No.35"
                real_issue = f"No.{no_num:02d}"
                # 映射期数：按规则计算，如 35 -> 12B
                mapped_issue = num_to_issue_code(no_num)

                print(f"  年 {year}，{real_issue} -> 映射期数 {mapped_issue}")

                # 点击期次，触发目录刷新
                click_issue_js(driver, issue_el)

                # 等右侧文章目录容器出现（id="rightCataloglist"）
                try:
                    WebDriverWait(driver, 15).until(
                        EC.presence_of_element_located(
                            (By.ID, "rightCataloglist")
                        )
                    )
                except Exception:
                    pass

                articles = parse_article_list_with_selenium(driver)
                article_count = len(articles)
                year_article_count += article_count
                print(f"    本期解析到 {article_count} 篇文章 [{issue_idx}/{total_issues}]")

                for rec in articles:
                    all_rows.append({
                        "年份": year,
                        "期数": real_issue,
                        "映射期数": mapped_issue,
                        "栏目": rec.get("栏目", ""),
                        "文章标题": rec.get("文章标题", ""),
                    })
            
            # 年份处理完成，输出汇总
            print(f"  ✓ 年份 {year} 处理完成，共 {total_issues} 期，{year_article_count} 篇文章")

    finally:
        driver.quit()

    df = pd.DataFrame(all_rows)
    return df


def main():
    start_time = datetime.now()
    print("=" * 60)
    print(f"开始爬取 CNKI 期刊数据")
    print(f"时间范围：{START_YEAR} - {END_YEAR}")
    print(f"开始时间：{start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    df = crawl_journal()
    
    end_time = datetime.now()
    duration = end_time - start_time
    
    print("=" * 60)
    print(f"爬取完成！")
    print(f"共获取到 {len(df)} 条记录")
    print(f"结束时间：{end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"耗时：{duration}")
    print("=" * 60)
    
    df.to_excel(OUTPUT_EXCEL, index=False)
    print(f"已写入 Excel：{OUTPUT_EXCEL}")


if __name__ == "__main__":
    main()