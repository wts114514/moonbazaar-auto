#!/usr/bin/env python3
"""
MoonBazaar 排行榜抓取工具（最终版）
抓取三个榜单并保存为干净的 JSON
"""

import requests
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

# ================= 配置区 =================
import os
COOKIE_STR = os.environ.get("MOON_COOKIE", "")

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
            # 拆分：用户名 | 任务商: XXX | 完成时间: XXX
            parts = re.split(r'任务商[:：]\s*', user_text)
            user_text = parts[0].strip()
            rest = parts[1] if len(parts) > 1 else ""

            # 提取任务商和完成时间
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
        # 单次榜额外字段
        if provider:
            item["provider"] = provider
        if finish_time:
            item["finish_time"] = finish_time

        data.append(item)
    return data


# ================= 主流程 =================
def main():
    print("=" * 55)
    print("MoonBazaar 排行榜抓取工具（最终版）")
    print("时间:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 55)

    url = "https://moonbazaar.xyz/home/toplist"
    print(f"\n[抓取] 正在请求页面 ...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"[失败] HTTP 状态码: {resp.status_code}")
            return
        html = resp.text
        print(f"[成功] 获取到 {len(html)} 字符")
    except Exception as e:
        print(f"[异常] 请求出错: {e}")
        return

    # 分别解析三个面板
    result = {}
    for key in ["weekly", "total", "single"]:
        data = parse_html(html, key)
        if data:
            result[key] = data
            print(f"\n[成功] {key} 解析出 {len(data)} 条数据")
            for item in data[:3]:
                print(f"    {item['rank']} {item['user']} - {item['amount']} GC")
        else:
            print(f"[错误] {key} 解析失败")

    # 保存 JSON
    if result:
        result["updatedAt"] = datetime.now().isoformat()
        with open("leaderboard.json", "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print("\n" + "=" * 55)
        print("[完成] 数据已保存到 leaderboard.json")
        print("=" * 55)
    else:
        print("\n[失败] 未抓取到任何数据。")


if __name__ == "__main__":
    main()
