#!/usr/bin/env python3
"""
MoonBazaar 排行榜抓取工具 (最终修复版)
功能：抓取周榜、累计榜、单次高额榜，生成 leaderboard.json
特点：自动从环境变量读取 Cookie，时间戳强制转换为北京时间 (UTC+8)
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# ================= 配置区 =================
# 从 GitHub Secrets 中读取 Cookie，如果在本地运行则需要手动设置环境变量
COOKIE_STR = os.environ.get("MOON_COOKIE", "")

TARGET_URL = "https://moonbazaar.xyz/home/toplist"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Cookie": COOKIE_STR,
}

# ================= 解析函数 =================
def parse_html(html, panel_key):
    """根据 data-panel 属性，解析对应的榜单"""
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

        # ===== 处理用户名 =====
        user_text = user_el.get_text(strip=True)
        
        # 处理 "注册时间" 附加信息
        if "注册时间" in user_text:
            user_text = user_text.split("注册时间")[0].strip()

        # 处理单次榜的 "任务商" 附加信息
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

        # ===== 处理金额 =====
        amount_text = amount_el.get_text(strip=True).replace(",", "").replace("GC", "").strip()
        try:
            amount = float(amount_text)
        except ValueError:
            amount = 0.0

        item = {
            "rank": rank_el.get_text(strip=True) if rank_el else "",
            "user": user_text,
            "amount": amount,
        }
        if provider:
            item["provider"] = provider
        if finish_time:
            item["finish_time"] = finish_time

        data.append(item)
    return data


# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取 MoonBazaar 排行榜...")

    if not COOKIE_STR:
        print("[警告] 未检测到环境变量 MOON_COOKIE，请检查 GitHub Secrets 配置。")

    try:
        response = requests.get(TARGET_URL, headers=HEADERS, timeout=20)
        response.raise_for_status()
    except Exception as e:
        print(f"[错误] 请求页面失败: {e}")
        return

    html = response.text
    print(f"[成功] 获取页面 HTML，长度: {len(html)} 字符")

    result = {
        "weekly": parse_html(html, "weekly"),
        "total": parse_html(html, "total"),
        "single": parse_html(html, "single"),
    }

    # ===== 修复时区：强制输出北京时间 (UTC+8) =====
    bj_time = datetime.now(timezone.utc) + timedelta(hours=8)
    result["updatedAt"] = bj_time.strftime("%Y-%m-%d %H:%M:%S")

    # 保存文件
    with open("leaderboard.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[完成] 数据已保存到 leaderboard.json，更新时间: {result['updatedAt']}")
    print(f"       周榜: {len(result['weekly'])} 条")
    print(f"       累计榜: {len(result['total'])} 条")
    print(f"       单次榜: {len(result['single'])} 条")


if __name__ == "__main__":
    main()
