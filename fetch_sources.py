#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_sources.py
TVBox 上游精选源自动化抓取器 (内置 30 天保鲜与停更淘汰机制)

功能：
1. 读取 sources_config.json 清单；
2. 逐一拉取各源，支持中文域名 IDNA 自动编码与 302 重定向穿透；
3. 智能解析明文、24# AES-CBC 密文与 JFIF 图片隐写；
4. 动态保鲜淘汰：针对 GitHub 提交记录、HTTP Last-Modified 或内容哈希进行保鲜质检，
   若超过 30 天未更新，判定为断更弃坑源，立即停止抓取并自动禁用；
5. 执行多级镜像自动回退池（Primary -> Mirrors -> Backups）；
6. 执行防投毒准入校验（必须是合法 JSON 且包含 sites 或 spider）；
7. 原始数据落盘至 source/{key}.json。
"""

import os
import sys
import json
import re
import base64
import hashlib
import email.utils
import urllib.request
import urllib.parse
import ssl
from datetime import datetime, timezone
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "sources_config.json")
SOURCE_DIR = os.path.join(BASE_DIR, "source")
YY_DIR = os.path.join(BASE_DIR, "yy")
TRACKER_FILE = os.path.join(BASE_DIR, "source_tracker.json")

MAX_STALE_DAYS = 30  # 超过 30 天不更新则自动淘汰

def right_pad(s: str, fill: str, length: int) -> str:
    s = s.strip()
    if len(s) >= length:
        return s[:length]
    return s + (fill * (length - len(s)))

COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/|(\"(?:\\.|[^\"\\])*\")", re.MULTILINE | re.DOTALL)

def clean_comments_and_commas(raw_text: str) -> str:
    """清理非标准 JSON 注释、尾随逗号，并截取最外层合法 JSON 边界"""
    start_curly = raw_text.find("{")
    end_curly = raw_text.rfind("}")
    if start_curly != -1 and end_curly != -1 and end_curly > start_curly:
        raw_text = raw_text[start_curly : end_curly + 1]

    def repl(m):
        return m.group(1) if m.group(1) else ""
    cleaned = COMMENT_RE.sub(repl, raw_text)
    cleaned = re.sub(r',[ \t\r\n]*([}\]])', r'\1', cleaned)
    return cleaned.strip()

def decode_payload(data: bytes) -> str:
    """智能解析上游原始数据流 (明文、JFIF隐写、24# AES-CBC)"""
    # 1. 尝试判断是否为 2423 / $# 格式加密 (如南风、肥猫)
    try:
        text_candidate = data.decode("utf-8", errors="ignore").strip()
        if text_candidate.startswith("2423") or text_candidate.startswith("$#"):
            raw = bytes.fromhex(text_candidate) if text_candidate.startswith("2423") else data
            start_mark = b"\x24\x23"  # $#
            end_mark = b"\x23\x24"    # #$
            idx_start = raw.find(start_mark) + 2
            idx_end = raw.find(end_mark)
            
            key_str = raw[idx_start:idx_end].decode("ascii")
            key = right_pad(key_str, "0", 16).encode("utf-8")
            iv_str = raw[-13:].decode("ascii")
            iv = right_pad(iv_str, "0", 16).encode("utf-8")
            ciphertext = raw[idx_end + 2 : -13]
            
            cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            decrypted = decryptor.update(ciphertext) + decryptor.finalize()
            pad = decrypted[-1]
            if pad <= 16:
                decrypted = decrypted[:-pad]
            print(f"    🔓 [AES-CBC] 成功解密 24# 密文源 ({len(decrypted)} 字节)")
            return decrypted.decode("utf-8", errors="ignore")
    except Exception:
        pass

    # 2. 尝试判断是否为 JFIF 隐写图片源 (如饭太硬)
    eoi = data.find(b"\xff\xd9")
    if eoi != -1 and eoi + 2 < len(data):
        trailing = data[eoi + 2:]
        if b"**" in trailing:
            try:
                _, b64_part = trailing.split(b"**", 1)
                raw_text = base64.b64decode(b64_part).decode("utf-8", errors="ignore")
                print(f"    🖼️ [JFIF隐写] 成功提取 Base64 隐写源 ({len(raw_text)} 字节)")
                return raw_text
            except Exception:
                pass

    # 3. 默认尝试 utf-8 / gbk 明文文本解码
    for enc in ["utf-8-sig", "utf-8", "gbk", "latin-1"]:
        try:
            return data.decode(enc)
        except Exception:
            continue
    return ""

# 5. 高可用验证 Spider 注册表 (防止相对路径或死链导致电视加载 Jar 失败)
KNOWN_SPIDERS = {
    "feimao": "https://img2.gelonghui.com/library/6a396-4e09c48e-c9bc-4313-b788-8d5120f90e5d.png;md5;6a396033ae45efee57ba789f91d7123e",
    "fty": "https://xiuxiu-pro-new.meitudata.com/posters/5d1f9c9e4d99c85337af94b57afc12da.jpg;md5;e6c78bbbd60e50f611c9aac6ff273fd8",
    "nanfeng": "https://jihulab.com/yoursmile77/TVBox/-/raw/master/Yoursmile.jar;md5;2fe20a9210f68dec7863a0b31a2b85d4",
    "moyu": "https://tc-new.z.wiki/autoupload/iYHTWVx6T8RrCmqdGD6MOdiO_OyvX7mIgxFBfDMDErs/20260408/3E37/fish.jar;md5;d07d678a0f3b813b67826a492b297581",
    "moyu4k": "https://tc-new.z.wiki/autoupload/iYHTWVx6T8RrCmqdGD6MOdiO_OyvX7mIgxFBfDMDErs/20260408/3E37/fish.jar;md5;d07d678a0f3b813b67826a492b297581",
    "ok": "https://gh-proxy.com/https://raw.githubusercontent.com/cluntop/tvbox/main/jar/xs.jar",
    "pg": "https://gh-proxy.com/https://raw.githubusercontent.com/cluntop/tvbox/main/pg.jar",
    "fun": "https://gh-proxy.com/https://raw.githubusercontent.com/cluntop/tvbox/main/pg.jar",
    "xiaosa": "https://gh-proxy.com/https://raw.githubusercontent.com/qist/tvbox/master/xiaosa/spider.jar",
    "xyq": "https://gh-proxy.com/https://raw.githubusercontent.com/xyq254245/xyqonlinerule/main/custom_spider.jar",
    "tvboxorg": "http://oss4liview.moji.com/thd_file/config_file/20241029/c8c3683f2a74c7df8b1d6046e7f225fa.txt",
    "wex": "http://oss4liview.moji.com/thd_file/config_file/20241029/c8c3683f2a74c7df8b1d6046e7f225fa.txt",
    "niu2": "http://oss4liview.moji.com/thd_file/config_file/20241029/c8c3683f2a74c7df8b1d6046e7f225fa.txt",
    "eyh": "http://oss4liview.moji.com/thd_file/config_file/20241029/c8c3683f2a74c7df8b1d6046e7f225fa.txt"
}

def resolve_relative_url(val: str, base_prefix: str) -> str:
    if not val or not isinstance(val, str) or not base_prefix:
        return val
    val = val.strip()
    if val.startswith("http://") or val.startswith("https://"):
        return val
    parts = val.split(";", 1)
    url_part = parts[0]
    extra = ";" + parts[1] if len(parts) > 1 else ""
    # 严格限定：只有显式相对路径 (./xx) 或文件扩展名才展开为 CDN 地址
    # 绝对不能把 Type 3 内置 Java 类名 (如 csp_xxx) 误当作相对路径拼成错误的 404 URL
    if url_part.startswith("./"):
        return base_prefix + url_part[2:] + extra
    elif any(url_part.endswith(ext) for ext in [".jar", ".js", ".py", ".json", ".txt", ".png", ".jpg", ".gif", ".php"]):
        return base_prefix + url_part + extra
    return val

def auto_repair_source(data: dict, upstream_url: str = "", source_key: str = "") -> dict:
    """智能解析并修复相对路径 (./jar/、./py/、./js/)，补全为高可用 CDN 地址"""
    if not isinstance(data, dict):
        return data

    base_prefix = ""
    if upstream_url:
        m = re.search(r"(?:githubusercontent\.com|github\.com)/([^/]+)/([^/]+)/(?:raw/|blob/)?([^/]+)/(.*)", upstream_url)
        if m:
            owner, repo, branch, full_path = m.groups()
            base_dir = "/".join(full_path.split("/")[:-1])
            if base_dir:
                base_prefix = f"https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{base_dir}/"
            else:
                base_prefix = f"https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"
        elif upstream_url.startswith("http://") or upstream_url.startswith("https://"):
            base_prefix = upstream_url.rsplit("/", 1)[0] + "/"

    # 1. 爬虫 Spider 相对路径修复
    spider = str(data.get("spider") or "").strip()
    if spider:
        data["spider"] = resolve_relative_url(spider, base_prefix)

    # 2. 站点 API、Ext、Jar 相对路径自动补全为 CDN 绝对路径
    for s in data.get("sites", []):
        if isinstance(s, dict):
            for field in ["api", "ext", "jar"]:
                val = s.get(field)
                if isinstance(val, str):
                    s[field] = resolve_relative_url(val, base_prefix)

    # 3. 补全壁纸、Logo 与直播列表相对路径
    for field in ["wallpaper", "logo"]:
        val = data.get(field)
        if isinstance(val, str):
            data[field] = resolve_relative_url(val, base_prefix)

    for live in data.get("lives", []):
        if isinstance(live, dict):
            val = live.get("url")
            if isinstance(val, str):
                live["url"] = resolve_relative_url(val, base_prefix)

    return data

def load_tracker() -> dict:
    if os.path.exists(TRACKER_FILE):
        try:
            with open(TRACKER_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_tracker(tracker: dict):
    try:
        with open(TRACKER_FILE, "w", encoding="utf-8") as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def check_github_commit_time(url: str) -> datetime | None:
    """提取 GitHub 托管文件的最后真实 commit 提交时间"""
    m = re.search(r'(?:githubusercontent\.com|github\.com)/([^/]+)/([^/]+)/(?:raw/|blob/)?([^/]+)/(.+)', url)
    if not m:
        return None
    owner, repo, branch, path = m.groups()
    api_url = f"https://api.github.com/repos/{owner}/{repo}/commits?path={path}&page=1&per_page=1"
    req = urllib.request.Request(api_url, headers={"User-Agent": "TVBox-Source-Fetcher"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data and isinstance(data, list) and len(data) > 0:
                commit_date_str = data[0]["commit"]["committer"]["date"]
                return datetime.fromisoformat(commit_date_str.replace("Z", "+00:00"))
    except Exception:
        pass
    return None

def check_header_last_modified(headers) -> datetime | None:
    """解析 HTTP 响应头部的 Last-Modified 时间"""
    lm = headers.get("Last-Modified")
    if lm:
        try:
            return email.utils.parsedate_to_datetime(lm)
        except Exception:
            pass
    return None

def download_and_validate(url: str, source_key: str = "", check_stale: bool = True, timeout: int = 12) -> tuple[bool, str, dict, bool, int]:
    """
    下载并验证是否为合法 TVBox 配置，同时执行 30 天保鲜质检。
    返回: (ok, msg, data, is_stale, days_stale)
    """
    try:
        p = urllib.parse.urlsplit(url)
        netloc = p.netloc.encode("idna").decode("ascii")
        enc_url = urllib.parse.urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))
    except Exception as e:
        return False, f"URL 格式解析错误: {e}", {}, False, 0

    req = urllib.request.Request(
        enc_url,
        headers={
            "User-Agent": "okhttp/3.15 TVBox",
            "Accept": "application/json, text/plain, */*"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            headers = resp.headers
            raw_bytes = resp.read()
    except Exception as e:
        return False, f"网络请求失败: {e}", {}, False, 0

    now_utc = datetime.now(timezone.utc)
    
    if check_stale:
        # 1. 优先检查 GitHub 提交记录或 HTTP Last-Modified 权威时间戳
        update_dt = check_github_commit_time(url) or check_header_last_modified(headers)
        days_stale = 0
        if update_dt:
            days_stale = (now_utc - update_dt).days
            if days_stale > MAX_STALE_DAYS:
                stale_msg = f"上游已超过一个月未更新 (最后更新: {update_dt.strftime('%Y-%m-%d')}，已断更 {days_stale} 天)"
                return False, stale_msg, {}, True, days_stale
        else:
            # 2. 针对无头部时间戳的动态源，通过本地 SHA256 哈希变更追踪
            if source_key:
                tracker = load_tracker()
                curr_hash = hashlib.sha256(raw_bytes).hexdigest()
                record = tracker.get(source_key, {})
                last_hash = record.get("hash")
                last_time_str = record.get("last_updated")

                if last_hash != curr_hash:
                    tracker[source_key] = {
                        "hash": curr_hash,
                        "last_updated": now_utc.isoformat(),
                        "check_time": now_utc.isoformat()
                    }
                    save_tracker(tracker)
                else:
                    tracker[source_key]["check_time"] = now_utc.isoformat()
                    save_tracker(tracker)
                    if last_time_str:
                        try:
                            last_time = datetime.fromisoformat(last_time_str)
                            days_stale = (now_utc - last_time).days
                            if days_stale > MAX_STALE_DAYS:
                                stale_msg = f"内容已持续超过一个月未变动 (最后变动: {last_time.strftime('%Y-%m-%d')}，已静止 {days_stale} 天)"
                                return False, stale_msg, {}, True, days_stale
                        except Exception:
                            pass

    text = decode_payload(raw_bytes)
    if not text:
        return False, "无法解码数据编码", {}, False, 0

    # 防运营商拦截与网页注入校验
    if "<html" in text.lower() or "<!doctype" in text.lower():
        return False, "返回为网页/拦截页(HTML)，非合法源", {}, False, 0

    cleaned = clean_comments_and_commas(text)
    
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or start >= end:
        return False, "找不到合法的大括号 JSON 边界", {}, False, 0
    
    json_str = cleaned[start:end+1]

    # 铁律第一步：严格 JSON 语法准入 (绝不放行损坏或不合规数据)
    try:
        data = json.loads(json_str, strict=False)
    except Exception as e:
        return False, f"JSON 语法解析致命错误: {e}", {}, False, 0

    if not isinstance(data, dict):
        return False, "最外层不是 JSON 对象", {}, False, 0

    if not ("sites" in data or "spider" in data):
        return False, "缺少 sites 或 spider 核心字段", {}, False, 0

    # 智能前置自动修复：将相对 Spider、./py/、./js/ 等自动拓展为高可用 CDN 绝对路径
    data = auto_repair_source(data, upstream_url=url, source_key=source_key)

    # 铁律第二步：Spider 爬虫 Jar 强校验与国内连通性测试 (支持自动注入高可用备用 Jar)
    spider_ok, spider_msg = validate_spider_and_dependencies(data, source_key=source_key)
    if not spider_ok:
        return False, f"Spider 质检未通过: {spider_msg}", {}, False, 0

    return True, "OK", data, False, 0

def validate_spider_and_dependencies(data: dict, source_key: str = "") -> tuple[bool, str]:
    """
    铁律第二步：测试 Spider Jar 是否真实有效且可在电视端独立加载
    1. 必须配置 spider 字段；
    2. 禁止使用无法解析的相对路径 (./xx.jar)；
    3. 真实探活目标 Jar 地址 (HTTP 200/206 且内容为有效 Zip/Dex)；
    4. 熔断含有大量本地相对脚本 (./py/ 或 ./js/) 的非独立源。
    """
    spider = str(data.get("spider") or "").strip()
    if not spider:
        return False, "缺少 spider 爬虫核心字段"

    clean_jar_url = spider.split(";")[0].strip()
    jar_valid = False

    if clean_jar_url.startswith("http://") or clean_jar_url.startswith("https://"):
        try:
            req = urllib.request.Request(clean_jar_url, headers={"User-Agent": "okhttp/3.15 TVBox"})
            with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as r:
                if r.status in [200, 206]:
                    header_sample = r.read(1024)
                    if header_sample and (header_sample.startswith(b"PK\x03\x04") or b"classes.dex" in header_sample):
                        jar_valid = True
        except Exception:
            jar_valid = False

    # 若原地址不可达或损坏，自动尝试替换为经过验证的高可用 Spider 镜像
    if not jar_valid:
        fallback = None
        for k, v in KNOWN_SPIDERS.items():
            if k in source_key.lower():
                fallback = v
                break
        if fallback:
            try:
                fb_clean = fallback.split(";")[0].strip()
                req = urllib.request.Request(fb_clean, headers={"User-Agent": "okhttp/3.15 TVBox"})
                with urllib.request.urlopen(req, timeout=5, context=ssl_ctx) as r:
                    if r.status in [200, 206]:
                        print(f"    🕷️ 修复 Spider ({spider[:35]}...) -> 高可用 Jar: {fallback[:45]}...")
                        data["spider"] = fallback
                        jar_valid = True
            except Exception:
                jar_valid = False

    if not jar_valid:
        return False, f"Spider Jar 网络探活不可达或损坏 ({spider})"

    sites = data.get("sites", [])
    rel_sites = [s.get("name", "") for s in sites if isinstance(s, dict) and (str(s.get("api", "")).startswith("./") or str(s.get("ext", "")).startswith("./"))]
    if len(rel_sites) > 5:
        return False, f"包含大量本地相对脚本依赖 ({len(rel_sites)} 个)，缺乏本地打包环境，电视端必报 404"

    return True, "OK"

def main():
    print("=" * 60)
    print(f"🚀 开始执行 TVBox 上游精选源拉取流水线 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    if not os.path.exists(CONFIG_FILE):
        print(f"❌ 找不到配置文件: {CONFIG_FILE}")
        sys.exit(1)

    os.makedirs(SOURCE_DIR, exist_ok=True)
    os.makedirs(YY_DIR, exist_ok=True)

    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        config = json.load(f)

    sources = config.get("sources", [])
    active_sources = [s for s in sources if s.get("enabled", True)]
    backup_sources = [s for s in sources if not s.get("enabled", True) and s.get("role") == "backup"]

    print(f"📋 读取到配置: 计划抓取主力源 {len(active_sources)} 个, 备选池 {len(backup_sources)} 个\n")

    results = []
    config_changed = False

    for src in active_sources:
        key = src["key"]
        name = src["name"]
        urls = src.get("urls", [])
        check_stale = src.get("check_stale", True)
        print(f"🔍 正在处理主力源: [{name}] ({key})")

        success = False
        final_data = None
        used_url = None
        all_expired = True
        last_expire_days = 0
        last_expire_msg = ""

        for u in urls:
            print(f"  👉 尝试拉取: {u}")
            ok, msg, data, is_stale, days_stale = download_and_validate(u, source_key=key, check_stale=check_stale)
            if ok:
                success = True
                final_data = data
                used_url = u
                all_expired = False
                sites_count = len(data.get("sites", []))
                print(f"  🟢 成功获取并完成保鲜质检! (包含 {sites_count} 个站点)")
                break
            else:
                if not is_stale:
                    all_expired = False
                else:
                    last_expire_days = days_stale
                    last_expire_msg = msg
                print(f"  ⚠️  该地址失败: {msg}")

        # 若该源所有线路均因超过 1 个月未更新而失败，自动从配置中禁用并清理本地陈旧文件
        if not success and all_expired and last_expire_days > MAX_STALE_DAYS:
            print(f"  ⏰ [{name}] 判定为断更弃坑源 (已停更 {last_expire_days} 天 > 30天)，触发自动淘汰规则！")
            src["enabled"] = False
            src["reason"] = f"已停更超过一个月 (已断更 {last_expire_days} 天)"
            config_changed = True
            
            # 清理旧落盘
            old_src = os.path.join(SOURCE_DIR, f"{key}.json")
            old_yy = os.path.join(YY_DIR, f"{key}_fix.json")
            if os.path.exists(old_src):
                os.remove(old_src)
                print(f"  🗑️ 已清理历史源文件: {old_src}")
            if os.path.exists(old_yy):
                os.remove(old_yy)
                print(f"  🗑️ 已清理历史输出文件: {old_yy}")

        # 若主力源所有地址均失败且非因主动停更淘汰，尝试调取备选池源替补
        if not success and backup_sources and not all_expired:
            print(f"  🚨 [{name}] 线路故障，尝试调取备选池源替补...")
            for b_src in backup_sources:
                b_key = b_src["key"]
                b_name = b_src["name"]
                for bu in b_src.get("urls", []):
                    print(f"    👉 尝试备选源 [{b_name}]: {bu}")
                    ok, msg, data, is_stale, _ = download_and_validate(bu, source_key=b_key)
                    if ok:
                        success = True
                        final_data = data
                        used_url = bu
                        key = f"{key}_{b_key}"
                        name = f"{name}({b_name}替补)"
                        print(f"    🟢 备选源替补成功! (包含 {len(data.get('sites', []))} 个站点)")
                        break
                if success:
                    break

        if success and final_data:
            out_file = os.path.join(SOURCE_DIR, f"{key}.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)
            print(f"  💾 原始数据已无损保存至: source/{key}.json\n")
            results.append({"key": key, "name": name, "status": "success", "url": used_url, "sites": len(final_data.get("sites", []))})
        else:
            print(f"  ❌ [{name}] 停止抓取并跳过落盘\n")
            results.append({"key": key, "name": name, "status": "failed", "reason": last_expire_msg or "线路全部不可达"})

    if config_changed:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print("📝 sources_config.json 已自动更新淘汰状态。\n")

    print("=" * 60)
    print("📊 抓取结果汇总报告")
    print("=" * 60)
    for r in results:
        status_icon = "🟢" if r["status"] == "success" else "🔴"
        sites_info = f"({r.get('sites', 0)} 个站点)" if r["status"] == "success" else f"[{r.get('reason', '')}]"
        print(f"{status_icon} [{r['name']}] -> {r['status']} {sites_info}")
    print()

if __name__ == "__main__":
    main()
