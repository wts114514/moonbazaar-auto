#!/usr/bin/env python3
"""
MoonBazaar 排行榜抓取工具 (自动续期版)
用 Session 保持会话，服务器会自动刷新 PHPSESSID，实现滚动续期
"""

import os
import re
import json
import base64
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

# ================= 配置 =================
COOKIE_STR = os.environ.get("MOON_COOKIE", "")
GH_PAT = os.environ.get("GH_PAT", "")
GH_REPO = os.environ.get("GITHUB_REPOSITORY", "")
BASE_URL = "https://moonbazaar.xyz"
TARGET_URL = f"{BASE_URL}/home/toplist"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
      "AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0.0.0 Safari/537.36")


# ================= 解析函数 =================
def parse_html(html, panel_key):
    soup = BeautifulSoup(html, "html.parser")
    panel = soup.select_one(f'section[data-panel="{panel_key}"]')
    if not panel:
        return []
    data = []
    for row in panel.select(".leader-row"):
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
                sub = re.split(r'完成时间[:：]\s*', rest)
                provider = sub[0].replace("•", "").strip()
                finish_time = sub[1].strip() if len(sub) > 1 else ""
            else:
                provider = rest.replace("•", "").strip()
        amt_text = amount_el.get_text(strip=True).replace(",", "").replace("GC", "").strip()
        try:
            amount = float(amt_text)
        except ValueError:
            amount = 0.0
        item = {"rank": rank_el.get_text(strip=True) if rank_el else "", "user": user_text, "amount": amount}
        if provider:
            item["provider"] = provider
        if finish_time:
            item["finish_time"] = finish_time
        data.append(item)
    return data


# ================= Cookie 处理 =================
def parse_cookie_str(cookie_str):
    result = {}
    if not cookie_str:
        return result
    if cookie_str.strip().startswith("["):
        try:
            arr = json.loads(cookie_str)
            for item in arr:
                if "name" in item and "value" in item:
                    result[item["name"]] = item["value"]
            return result
        except Exception:
            pass
    for pair in cookie_str.split(";"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def dict_to_cookie_str(d):
    return "; ".join([f"{k}={v}" for k, v in d.items()])


# ================= GitHub Secret 更新 =================
def update_github_secret(secret_name, secret_value):
    if not GH_PAT or not GH_REPO:
        print("[GitHub] 跳过（缺少 GH_PAT 或仓库信息）")
        return False
    try:
        from nacl import encoding, public as nacl_public
    except ImportError:
        print("[GitHub] 未安装 PyNaCl，跳过")
        return False

    headers = {
        "Authorization": f"Bearer {GH_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        url = f"https://api.github.com/repos/{GH_REPO}/actions/secrets/public-key"
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        key_data = r.json()
        key_id = key_data["key_id"]
        pub_key = nacl_public.PublicKey(key_data["key"].encode(), encoding.Base64Encoder())
        sealed = nacl_public.SealedBox(pub_key)
        enc = base64.b64encode(sealed.encrypt(secret_value.encode())).decode()

        url = f"https://api.github.com/repos/{GH_REPO}/actions/secrets/{secret_name}"
        r = requests.put(url, headers=headers, json={"encrypted_value": enc, "key_id": key_id}, timeout=15)
        r.raise_for_status()
        print(f"[GitHub] ✅ Secret {secret_name} 已更新")
        return True
    except Exception as e:
        print(f"[GitHub] ❌ Secret 更新失败: {e}")
        return False


# ================= 主流程 =================
def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始抓取...")

    old_cookies = parse_cookie_str(COOKIE_STR)
    print(f"[信息] 原 Cookie 字段数: {len(old_cookies)}")
    has_remember = "remember_me" in old_cookies
    print(f"[信息] 含 remember_me: {has_remember}")

    # 建立 Session，加载所有 Cookie
    session = requests.Session()
    session.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    })
    for k, v in old_cookies.items():
        session.cookies.set(k, v, domain="moonbazaar.xyz", path="/")

    # ===== 第一步：访问首页，让服务器自动续期 PHPSESSID =====
    print(f"[1/2] 访问首页，尝试自动续期...")
    try:
        r = session.get(f"{BASE_URL}/home", timeout=20, allow_redirects=True)
        print(f"[信息] 响应 URL: {r.url}, 状态码: {r.status_code}")

        # 如果被重定向到 /login，说明 remember_me 也失效了
        if "/login" in r.url:
            print("[警告] 被重定向到登录页，remember_me 可能已失效")
    except Exception as e:
        print(f"[错误] 访问首页失败: {e}")
        return

    # ===== 第二步：访问排行榜页面 =====
    print(f"[2/2] 访问排行榜页面...")
    try:
        r = session.get(TARGET_URL, timeout=20)
        r.raise_for_status()
    except Exception as e:
        print(f"[错误] 请求排行榜失败: {e}")
        return

    html = r.text
    print(f"[成功] HTML 长度: {len(html)}")

    # ===== 提取新 Cookie 并自续期 =====
    new_cookies = {c.name: c.value for c in session.cookies}
    print(f"[信息] 当前 Session Cookie 字段数: {len(new_cookies)}")

    # 找出变更
    changed_fields = []
    for k, v in new_cookies.items():
        if old_cookies.get(k) != v:
            changed_fields.append(k)
    # 合并（新的为主，旧的补）
    merged = dict(old_cookies)
    merged.update(new_cookies)

    if changed_fields:
        print(f"[Cookie] 变化字段: {', '.join(changed_fields)}")
        new_cookie_str = dict_to_cookie_str(merged)
        update_github_secret("MOON_COOKIE", new_cookie_str)
    else:
        print("[Cookie] 无变化")

    # ===== 判断数据 =====
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

    print(f"[完成] 周榜 {len(result['weekly'])} | 累计榜 {len(result['total'])} | 单次榜 {len(result['single'])}")
    print(f"[完成] 更新时间: {result['updatedAt']}")


if __name__ == "__main__":
    main()
