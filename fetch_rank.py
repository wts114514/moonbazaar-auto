#!/usr/bin/env python3
"""
MoonBazaar 排行榜抓取工具 (自动登录版)
用 Playwright 自动登录，绕过 Cookie 过期问题
"""

import os
import re
import json
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# ================= 配置 =================
USERNAME = os.environ.get("MOON_USERNAME", "")
PASSWORD = os.environ.get("MOON_PASSWORD", "")
FALLBACK_COOKIE = os.environ.get("MOON_COOKIE", "")
TARGET_URL = "https://moonbazaar.xyz/home/toplist"
LOGIN_URL = "https://moonbazaar.xyz/login"

HEADERS_TEMPLATE = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# ================= 自动登录 =================
def auto_login():
    """用 Playwright 自动登录，返回 Cookie 字符串"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("[错误] Playwright 未安装")
        return None

    print("[登录] 启动无头浏览器...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            '--disable-blink-features=AutomationControlled',
            '--no-sandbox',
        ])
        context = browser.new_context(
            user_agent=HEADERS_TEMPLATE["User-Agent"],
            viewport={'width': 1280, 'height': 900},
            locale='zh-CN',
        )
        # 反自动化检测
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)

        page = context.new_page()

        try:
            print(f"[登录] 访问 {LOGIN_URL}")
            page.goto(LOGIN_URL, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=15000)
            time.sleep(2)

            # 填写账号密码（尝试多种选择器）
            filled = False
            for user_sel in ['input[name="email"]', 'input[name="username"]', 'input[type="email"]', 'input[type="text"]']:
                try:
                    if page.locator(user_sel).count() > 0:
                        page.fill(user_sel, USERNAME)
                        print(f"[登录] 已填写用户名 ({user_sel})")
                        filled = True
                        break
                except Exception:
                    continue

            if not filled:
                print("[登录] 未找到用户名输入框")
                browser.close()
                return None

            for pass_sel in ['input[name="password"]', 'input[type="password"]']:
                try:
                    if page.locator(pass_sel).count() > 0:
                        page.fill(pass_sel, PASSWORD)
                        print(f"[登录] 已填写密码")
                        break
                except Exception:
                    continue

            time.sleep(1)

            # 处理 hCaptcha：点击复选框
            try:
                print("[登录] 尝试处理 hCaptcha...")
                hcaptcha_frame = page.frame_locator('iframe[src*="hcaptcha"]').first
                checkbox = hcaptcha_frame.locator('#checkbox')
                if checkbox.count() > 0:
                    checkbox.click()
                    print("[登录] 已点击 hCaptcha 复选框")
                    time.sleep(5)  # 等待验证完成
                else:
                    print("[登录] hCaptcha 复选框未找到")
            except Exception as e:
                print(f"[登录] hCaptcha 处理异常: {e}")

            # 提交
            time.sleep(1)
            submitted = False
            for btn_sel in ['button[type="submit"]', 'button:has-text("登录")', 'button:has-text("Login")', 'input[type="submit"]']:
                try:
                    if page.locator(btn_sel).count() > 0:
                        page.click(btn_sel)
                        print(f"[登录] 已点击登录按钮")
                        submitted = True
                        break
                except Exception:
                    continue

            if not submitted:
                print("[登录] 未找到登录按钮")
                browser.close()
                return None

            # 等待跳转
            time.sleep(5)
            current_url = page.url
            print(f"[登录] 当前 URL: {current_url}")

            if "/login" in current_url:
                print("[登录] ❌ 登录失败，可能 hCaptcha 未通过或账号密码错误")
                browser.close()
                return None

            # 提取 cookie
            cookies = context.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            print(f"[登录] ✅ 登录成功，获取 Cookie 长度: {len(cookie_str)}")

            browser.close()
            return cookie_str

        except Exception as e:
            print(f"[登录] 异常: {e}")
            browser.close()
            return None


# ================= 解析函数 =================
def parse_html(html, panel_key):
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(f'section[data-panel="{panel_key}"]')
    if not panel:
        return []
    data = []
    rows = panel.select(".leader-row")
    for row in rows:
        rank_el = row.select_one(".rank")
        user_el = row.select_one(".who")
        amount_el = row.select_one(".amount")
        if not (user_el and amount_el):
            continue
        user_text = user_el.get_text(strip=True)
        if "注册时间" in user_text:
            user_text = user_text.split("注册时间")[0].strip()
        provider = ""
        finish_time = ""
        if "任务商" in user_text:
            parts = re.split(r'任务商[:：]\s*', user_text)
            user_text = parts[0].strip()
            rest = parts[1] if len(parts) > 1 else ""
            if "完成时间" in rest:
                sub_parts = re.split(r'完成时间[:：]\s*', rest)
                provider = sub_parts[0].replace("•", "").strip()
                finish_time = sub_parts[1].strip() if len(sub_parts) > 1 else ""
            else:
                provider = rest.replace("•", "").strip()
        amount_text = amount_el.get_text(strip=True).replace(",", "").replace("GC", "").strip()
        try:
            amount = float(amount_text)
        except ValueError:
            amount = 0.0
        item = {"rank": rank_el.get_text(strip=True) if rank_el else "", "user": user_text, "amount": amount}
        if provider:
            item["provider"] = provider
        if finish_time:
            item["finish_time"] = finish_time
        data.append(item)
    return data


# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取 MoonBazaar...")

    # 策略 1：自动登录
    cookie_str = None
    if USERNAME and PASSWORD:
        print("[策略] 尝试自动登录...")
        cookie_str = auto_login()

    # 策略 2：用备用 Cookie
    if not cookie_str:
        print("[策略] 自动登录失败，使用备用 Cookie...")
        cookie_str = FALLBACK_COOKIE
        # 解析 JSON 格式
        if cookie_str.strip().startswith("["):
            try:
                data = json.loads(cookie_str)
                cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in data])
            except Exception:
                pass

    if not cookie_str:
        print("[错误] 没有可用的 Cookie")
        return

    headers = {**HEADERS_TEMPLATE, "Cookie": cookie_str}

    # 请求页面
    try:
        response = requests.get(TARGET_URL, headers=headers, timeout=20)
        response.raise_for_status()
    except Exception as e:
        print(f"[错误] 请求失败: {e}")
        return

    html = response.text
    print(f"[成功] 获取 HTML，长度: {len(html)}")

    if "jiajunba" not in html and "leader-row" not in html:
        print("[警告] 页面中没有排行榜数据，Cookie 可能已失效")
        return

    result = {
        "weekly": parse_html(html, "weekly"),
        "total": parse_html(html, "total"),
        "single": parse_html(html, "single"),
    }

    bj_time = datetime.now(timezone.utc) + timedelta(hours=8)
    result["updatedAt"] = bj_time.strftime("%Y-%m-%d %H:%M:%S")

    with open("leaderboard.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[完成] 周榜 {len(result['weekly'])} 条 | 累计榜 {len(result['total'])} 条 | 单次榜 {len(result['single'])} 条")
    print(f"[完成] 更新时间: {result['updatedAt']}")


if __name__ == "__main__":
    main()
