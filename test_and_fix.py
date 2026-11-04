#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_and_fix.py
TVBox 站点极简打标与大屏 6 梯队优化重排流水线 (超时标记为 0 版)

核心规范 (基于 SIMPLE_RULES)：
1. 全员保活 · 绝不误杀：48个原始站点完整保留，不设死黑名单；
2. 取消 |手机 标签：影视点播源全部执行方案 B 测速；
3. 专用功能标签保留：|盘、|磁力、|非影、|js、|死链 完整保留；
4. 测速格式：|下载速度|延迟 (如 |4.5M|220ms)，超时/失效统一标记为 |0；
5. 大屏搜索与首页 6 梯队优化物理重排：
   - 梯队 1：首页排头兵 (豆豆┃片单)
   - 梯队 2：影视点播类 (内部按真实下载速度从快到慢降序排列，|0 站点沉底排在末尾)
   - 梯队 3：高清磁力类 (新6V┃磁力)
   - 梯队 4：垂直非影视类 (少儿教育、音乐MV、体育看球、一直播、短漫剧等)
   - 梯队 5：网盘扫码类 (玩偶哥哥、海绵、立播、盘搜等)
   - 梯队 6：JS 脚本引擎类 (虎牙js、斗鱼js、兔小贝js)
6. 严格保持原始数据字段完整，输出为 {源名称}_fix.json。
"""

import os
import sys
import json
import re
import time
import urllib.request
import urllib.parse
import ssl
from concurrent.futures import ThreadPoolExecutor

# SSL 容错配置
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

# 1. 网盘扫码站规则库 (免测速，直接标 |盘)
PAN_KEYWORDS = [
    "云盘", "网盘", "阿里", "夸克", "115", "四盘", "多盘", "盘搜", "易搜", 
    "盘她", "盘他", "抠抠", "优汐", "优熙", "闪电", "推送", "海绵", "玩偶", "木偶",
    "蜗牛", "光鸭", "123", "土豆", "立播", "至尊", "聚剧", "上头", "晃悠",
    "媒体库", "蜡笔", "花卷", "观影", "七味", "盘库", "虎斑", "快影", "快映",
    "剧透", "原盘", "盘迷", "逸动", "移动", "异动", "无名", "双星", "天逸", "天翼",
    "讯蕾", "卡卡", "爱盘", "爱盼", "九七", "米搜", "觅盘", "酷乐", "百酷", "趣盘",
    "给力", "摆烂", "煮雪", "棠梨", "开饭", "歇会", "发呆", "随缘", "躺平", "赖床",
    "板凳", "慢点", "知我", "等风", "流映", "嗑剧", "凝光", "素笺", "长泽", "云岫",
    "搬运", "指南", "小丑", "八零", "即刻", "云集", "珈珈", "tiu6", "至臻", "简搜",
    "星河", "扫码", "网盘类", "emby", "alist", "webdav", "pansou", "duopan",
    "pansearch", "panhunt", "yiso", "yunpan", "配置", "市场", "自定义"
]
PAN_APIS = [
    "mydrive", "wogg", "seedhub", "s_zps", "ypanso", "bpanso", "kkss", "uuss", 
    "push", "hmys", "woniu", "panweb", "fishcloud", "fishdrive", "tudou", "shangtou",
    "huangyou", "cloud", "alishare", "quark", "pansou", "duopan", "pansearch", "panhunt",
    "tgyunpan", "huajuan", "guanying", "qwmkv", "pianku", "huban", "muou",
    "kuaiying", "labi", "shandian", "jutou", "libvio", "zhinan", "pan1me", "yidong",
    "emby", "alist", "webdav", "soai", "haiyin", "pansoo", "aipanso", "kaka", "panguard",
    "pancms", "jiansou", "yisou", "alips", "upyun", "fourkzn", "fishps", "misou",
    "market", "panmarket", "nullname", "wexwo", "wexpan", "tyso", "baiduso", "haiyinso",
    "97panso", "115share", "banyundao", "aipan", "jike", "shuangxing", "kkpan", "hdmoli", "wexdiy",
    "config", "panconfig", "wexconfig", "wexokconfig", "xunleipan"
]
PAN_EXT_KEYWORDS = [
    "cloud-drive", "token.json", "woggpan", "aliyun", "quark", "panweb", "123pan",
    "webdav", "emby", "panhunt", "pansou", "pansearch", "commonconfig", "wexconfig",
    "wexokconfig", "muoua", "yydsys", "xhban", "hjzhencai", "sidhub", "4kzn", "4kxc"
]

# 2. 高清磁力站规则库 (免测速，直接标 |磁力，梯队 3)
MAGNET_KEYWORDS = [
    "🧲", "磁力", "迅雷", "种子", "荐片", "torrent", "magnet", "p2p", "6v", "xb6v"
]
MAGNET_APIS = [
    "sixv", "jianpian", "jpjguard", "jpianamns", "dygod", "dygang", 
    "meijutt", "meijumi", "blsgod", "xunlei", "qnmp4", "btdx", "cili", "torrent", "magnet", "xb6v"
]

# 3. 垂直非影视规则库 (免测速，直接标 |非影)
AUX_KEYWORDS = [
    "儿歌", "听书", "教学", "舞曲", "电台", "跳舞", "戏曲", "音乐", "体育", "看球", 
    "球通", "飞球", "wwe", "动漫", "次元", "宝宝", "贝贝", "兔兔", "课堂", "教育",
    "少儿", "小学", "初中", "高中", "短剧", "短漫", "漫短", "漫剧", "一直播", "直播",
    "虎牙", "斗鱼", "bili", "哔哔", "mv", "ktv", "好看", "星星", "小薇", "悦庭",
    "爱上", "蜻蜓", "酷听", "易听", "小酷", "轮回", "八八", "咖啡", "合集", "预告",
    "吃瓜", "急救", "广告", "壁纸", "文件", "相声", "小品", "解说", "养生", "启蒙"
]
AUX_APIS = [
    "bili", "kanqiu", "livegz", "firstaid", "tingshu", "liveai", "manjuai",
    "duanjuai", "animeai", "anime", "book", "childrenai", "musicai", "sportai", "wallpaper", "local"
]

# 4. 影视点播源服务节点探测库 (方案 B：真实服务节点握手与吞吐测速)
SITE_PROBE_ENDPOINTS = {
    "厂长": "https://www.czzy77.com/",
    "瓜子": "https://api.guazitv.tv/",
    "比特": "https://www.bttwoo.com/",
    "视界": "https://www.99ys.tv/",
    "茉莉": "https://www.99ys.tv/",
    "奥特": "https://auete.com/",
    "热播": "https://www.cz01.vip/",
    "风云": "https://www.fengyunyingshi.com/",
    "剧圈": "https://www.juquanquan.tv/",
    "糯米": "https://www.nmys.vip/",
    "文采": "https://www.jpys.vip/",
    "荐片": "http://api2.jianpian.com/",
    "巴士": "https://www.dm84.tv/",
    "光影": "https://www.gyys.vip/",
    "奶酪": "https://nl.nlvod.cc/"
}

COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/|(\"(?:\\.|[^\"\\])*\")", re.MULTILINE | re.DOTALL)

def clean_comments_and_commas(raw_text: str) -> str:
    """清理非标准 JSON 注释、尾随逗号，同时严密保护字符串内部的 /* 与 //"""
    start_curly = raw_text.find("{")
    end_curly = raw_text.rfind("}")
    if start_curly != -1 and end_curly != -1 and end_curly > start_curly:
        raw_text = raw_text[start_curly : end_curly + 1]

    def repl(m):
        return m.group(1) if m.group(1) else ""
    cleaned = COMMENT_RE.sub(repl, raw_text)
    cleaned = re.sub(r',[ \t\r\n]*([}\]])', r'\1', cleaned)
    return cleaned.strip()

def format_speed(ttfb_ms: int, bytes_per_sec: float) -> str:
    """格式化为用户指定的 |下载速度|延迟 格式 (下载速度在前，延迟在后)"""
    speed_kb_s = bytes_per_sec / 1024.0
    if speed_kb_s >= 1024:
        dl_str = f"{speed_kb_s/1024.0:.1f}M"
    else:
        dl_str = f"{int(speed_kb_s)}K"

    if ttfb_ms < 1000:
        conn_str = f"{ttfb_ms}ms"
    else:
        conn_str = f"{ttfb_ms/1000:.1f}s"

    return f" |{dl_str}|{conn_str}"

def test_service_speed(probe_url: str, timeout: int = 4) -> tuple:
    """方案 B：对服务节点进行真实握手延迟与数据吞吐测速，返回 (tag, speed_kb_s, ttfb_ms)"""
    req = urllib.request.Request(probe_url, headers={
        "User-Agent": "okhttp/3.15 TVBox Android/10",
        "Accept": "*/*"
    })
    try:
        t0 = time.time()
        resp = urllib.request.urlopen(req, context=ctx, timeout=timeout)
        ttfb = int((time.time() - t0) * 1000)

        t_start_read = time.time()
        data = resp.read(1024 * 64) # 读取 64KB 样本计算带宽
        read_time = time.time() - t_start_read
        if read_time <= 0.001:
            read_time = 0.001

        bytes_per_sec = len(data) / read_time
        speed_kb_s = bytes_per_sec / 1024.0
        return format_speed(ttfb, bytes_per_sec), speed_kb_s, ttfb
    except Exception:
        return " |0", 0.0, 999999

def clean_danmaku(data: dict):
    """从源头彻底关闭并清除所有外挂弹幕接口与开关"""
    # 1. 移除全局顶层弹幕服务器接口
    for k in ["danmaku", "danmu", "danMu", "danmu_api"]:
        if k in data:
            del data[k]
    
    # 2. 遍历所有站点，强制关闭站点及 ext 内的弹幕
    for site in data.get("sites", []):
        if not isinstance(site, dict):
            continue
        if "danmu" in site:
            site["danmu"] = False
        if "danMu" in site:
            site["danMu"] = False
        
        ext = site.get("ext")
        if isinstance(ext, dict):
            if "danmu" in ext:
                ext["danmu"] = False
            if "danMu" in ext:
                ext["danMu"] = False
        elif isinstance(ext, str) and "danmu" in ext.lower():
            try:
                ext_obj = json.loads(ext)
                if isinstance(ext_obj, dict):
                    for dk in ["danmu", "danMu"]:
                        if dk in ext_obj:
                            ext_obj[dk] = False
                    site["ext"] = json.dumps(ext_obj, ensure_ascii=False)
            except Exception:
                pass

def clean_lives(data: dict):
    """
    根据用户要求与 best-fan/iptv-sources 项目规范：
    仅保留 best-fan 高清电视直播专线，剔除所有无关杂项与网络录像轮播。
    """
    data["lives"] = [
        {
            "name": "best-fan 电视直播",
            "type": 0,
            "url": "http://192.168.2.4:8888/live.txt",
            "playerType": 1,
            "epg": "https://epg.112114.xyz/?ch={name}&date={date}",
            "logo": "https://epg.112114.xyz/logo/{name}.png"
        },
        {
            "name": "best-fan 原生M3U8",
            "type": 0,
            "url": "http://192.168.2.4:8888/live.m3u8",
            "playerType": 1,
            "epg": "https://epg.112114.xyz/?ch={name}&date={date}",
            "logo": "https://epg.112114.xyz/logo/{name}.png"
        }
    ]

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

KNOWN_PREFIXES = {
    "pg": "https://gh-proxy.com/https://raw.githubusercontent.com/cluntop/tvbox/main/",
    "fun": "https://gh-proxy.com/https://raw.githubusercontent.com/cluntop/tvbox/main/",
    "ok": "https://gh-proxy.com/https://raw.githubusercontent.com/cluntop/tvbox/main/",
    "xiaosa": "https://gh-proxy.com/https://raw.githubusercontent.com/qist/tvbox/master/xiaosa/",
    "xyq": "https://gh-proxy.com/https://raw.githubusercontent.com/xyq254245/xyqonlinerule/main/"
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

def auto_repair_source(data: dict, file_key: str = "", upstream_url: str = "") -> dict:
    """智能解析并修复相对路径 (./jar/、./py/、./js/)，补全为高可用 CDN 地址"""
    if not isinstance(data, dict):
        return data

    base_prefix = ""
    for k, v in KNOWN_PREFIXES.items():
        if k in file_key.lower():
            base_prefix = v
            break

    if not base_prefix and upstream_url:
        m = re.search(r"(?:githubusercontent\.com|github\.com)/([^/]+)/([^/]+)/(?:raw/|blob/)?([^/]+)/(.*)", upstream_url)
        if m:
            owner, repo, branch, full_path = m.groups()
            base_dir = "/".join(full_path.split("/")[:-1])
            if base_dir:
                base_prefix = f"https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{base_dir}/"
            else:
                base_prefix = f"https://gh-proxy.com/https://raw.githubusercontent.com/{owner}/{repo}/{branch}/"

    # 1. 爬虫 Spider 修复
    spider = str(data.get("spider") or "").strip()
    if spider and base_prefix:
        data["spider"] = resolve_relative_url(spider, base_prefix)

    # 2. 站点 API、Ext、Jar 相对路径自动补全
    if base_prefix:
        for s in data.get("sites", []):
            if isinstance(s, dict):
                for field in ["api", "ext", "jar"]:
                    val = s.get(field)
                    if isinstance(val, str):
                        s[field] = resolve_relative_url(val, base_prefix)

        for field in ["wallpaper", "logo"]:
            val = data.get(field)
            if isinstance(val, str):
                data[field] = resolve_relative_url(val, base_prefix)

    return data

def check_and_fix_spider(data: dict, file_key: str) -> tuple[bool, str]:
    """
    铁律第二步：测试全局 Spider 爬虫 Jar 是否真实有效且可在电视端独立加载
    1. 必须配置 spider 字段；
    2. 禁止使用无法解析的相对路径 (./xx.jar) 或不可达地址；
    3. 真实探活目标 Jar 地址 (HTTP 200/206 且内容为有效 Zip/Dex)；
    4. 熔断含有大量本地相对脚本 (./py/ 或 ./js/) 的非独立源。
    """
    spider = str(data.get("spider") or "").strip()
    is_valid = False
    
    clean_url = spider.split(";")[0].strip()
    if clean_url.startswith("http://") or clean_url.startswith("https://"):
        try:
            req = urllib.request.Request(clean_url, headers={"User-Agent": "okhttp/3.15 TVBox"})
            with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
                if resp.status in [200, 206]:
                    head_sample = resp.read(1024)
                    if head_sample.startswith(b"PK\x03\x04") or b"classes.dex" in head_sample:
                        is_valid = True
        except Exception:
            is_valid = False

    if not is_valid:
        fallback = None
        for k, v in KNOWN_SPIDERS.items():
            if k in file_key.lower():
                fallback = v
                break
        if fallback:
            try:
                fb_clean = fallback.split(";")[0].strip()
                req = urllib.request.Request(fb_clean, headers={"User-Agent": "okhttp/3.15 TVBox"})
                with urllib.request.urlopen(req, timeout=4, context=ctx) as resp:
                    if resp.status in [200, 206]:
                        print(f"  🕷️ 检测到 Spider 异常 ({spider[:35]}...)，已自动修复为高可用直连: {fallback[:45]}...")
                        data["spider"] = fallback
                        is_valid = True
            except Exception:
                is_valid = False

    if not is_valid:
        return False, f"Spider Jar 真实探活失败或格式损坏 ({spider})"

    # 检查站点依赖熔断
    sites = data.get("sites") or []
    rel_count = sum(1 for s in sites if isinstance(s, dict) and (str(s.get("api", "")).startswith("./") or str(s.get("ext", "")).startswith("./")))
    if rel_count > 5:
        return False, f"包含大量本地相对脚本依赖 ({rel_count} 个)，缺乏本地打包环境，电视端必报 404"

    return True, "OK"

def classify_and_tag(site: dict) -> dict:
    """对单个站点执行特征分析、测速与梯队归类"""
    name = str(site.get("name") or "")
    key = str(site.get("key") or "")
    api = str(site.get("api") or "")
    ext = site.get("ext", "")
    ext_s = json.dumps(ext, ensure_ascii=False) if ext else ""
    try:
        timeout = int(site.get("timeout", 10))
    except (ValueError, TypeError):
        timeout = 10

    original_name = name

    # 1. 梯队 1：判定是否为首页排头兵 (豆豆/豆瓣/片单聚合推荐/首页公告)
    is_head = (
        key in ["点我切源", "豆瓣", "Douban", "Tg豆瓣", "db"] or
        key.lower().startswith("douban") or
        any(k in name for k in ["片单", "豆豆", "肥猫宝贝", "切源", "Tg豆瓣", "更新日期", "免费分享"]) or
        any(a in api for a in ["DouDou", "Douban", "PianDan", "TgYunDouBanPan"])
    )
    if is_head and not any(k in name for k in ["网盘", "扫码", "盘类"]):
        site["indexs"] = 1
        site["changeable"] = 1
        site["quickSearch"] = 1
        return {
            "site": site,
            "orig_name": original_name,
            "new_name": original_name, # 保持原名不打扰首页
            "category": "首页排头兵",
            "tier": 1,
            "subtier": 0,
            "speed_kb_s": 999999.0,
            "ttfb": 0
        }

    name_l = name.lower()
    key_l = key.lower()
    api_l = str(api).lower()
    ext_l = ext_s.lower()

    # 2. 梯队 4：判定是否为垂直非影视类 (儿歌/听书/教学/短剧/动漫/体育等，先于网盘匹配以防儿歌被误标为盘)
    is_aux = (
        any(k in name for k in AUX_KEYWORDS) or
        any(k in key for k in AUX_KEYWORDS) or
        any(a in api_l for a in AUX_APIS) or
        any(a in key_l for a in AUX_APIS)
    )
    if is_aux:
        clean_orig = original_name.rstrip()
        new_name = clean_orig if clean_orig.endswith("|非影") else f"{clean_orig} |非影"
        return {
            "site": site,
            "orig_name": original_name,
            "new_name": new_name,
            "category": "垂直非影视",
            "tier": 4,
            "subtier": 0,
            "speed_kb_s": 0.0,
            "ttfb": 999999
        }

    # 3. 梯队 5：判定是否为网盘扫码类 (含 4K 云盘/配置中心/网盘聚合)
    is_4k_pan = ("4k" in name_l or "4k" in key_l) and not any(w in name for w in ["秒播", "点播", "直连", "采集", "1080p"])
    is_pan = (
        is_4k_pan or
        any(k.lower() in name_l for k in PAN_KEYWORDS) or
        any(k.lower() in key_l for k in PAN_KEYWORDS) or
        any(k.lower() in ext_l for k in PAN_EXT_KEYWORDS) or
        any(a.lower() in api_l for a in PAN_APIS) or
        any(a.lower() in key_l for a in PAN_APIS)
    )
    if is_pan:
        clean_orig = original_name.rstrip()
        new_name = clean_orig if clean_orig.endswith("|盘") else f"{clean_orig} |盘"
        return {
            "site": site,
            "orig_name": original_name,
            "new_name": new_name,
            "category": "网盘扫码类",
            "tier": 5,
            "subtier": 0,
            "speed_kb_s": 0.0,
            "ttfb": 999999
        }

    # 4. 梯队 3：判定是否为高清磁力站
    is_magnet = (
        any(k in name for k in MAGNET_KEYWORDS) or
        any(k.lower() in key_l for k in MAGNET_KEYWORDS) or
        any(a.lower() in api_l for a in MAGNET_APIS) or
        any(a.lower() in key_l for a in MAGNET_APIS) or
        "magnet:?" in ext_l
    )
    if is_magnet:
        clean_orig = original_name.rstrip()
        new_name = clean_orig if clean_orig.endswith("|磁力") else f"{clean_orig} |磁力"
        return {
            "site": site,
            "orig_name": original_name,
            "new_name": new_name,
            "category": "高清磁力站",
            "tier": 3,
            "subtier": 0,
            "speed_kb_s": 0.0,
            "ttfb": 999999
        }

    # 5. 梯队 6：判定是否为 JS 脚本引擎站
    is_js = (
        "[js]" in name_l or
        (isinstance(api, str) and (".js" in api_l or "drpy" in api_l))
    )
    if is_js:
        clean_orig = original_name.rstrip()
        new_name = clean_orig if clean_orig.endswith("|js") else f"{clean_orig} |js"
        return {
            "site": site,
            "orig_name": original_name,
            "new_name": new_name,
            "category": "JS脚本引擎",
            "tier": 6,
            "subtier": 0,
            "speed_kb_s": 0.0,
            "ttfb": 999999
        }

    # 6. 提取站点明确提供的网址（用于死链检测与直连探针）
    explicit_url = None
    if isinstance(ext, dict) and "siteUrl" in ext:
        explicit_url = ext["siteUrl"]
    elif isinstance(ext, str) and ext.startswith("http"):
        explicit_url = ext
    elif isinstance(api, str) and api.startswith("http"):
        explicit_url = api

    # 如果配置给出了明文 URL，先进行死链检查
    if explicit_url:
        req = urllib.request.Request(explicit_url, headers={
            "User-Agent": "okhttp/3.15 TVBox Android/10",
            "Accept": "*/*"
        })
        try:
            with urllib.request.urlopen(req, context=ctx, timeout=min(timeout, 4)) as resp:
                pass
        except urllib.error.HTTPError as e:
            if e.code in [404, 500, 502, 503]:
                return {
                    "site": site,
                    "orig_name": original_name,
                    "new_name": f"{original_name} |死链",
                    "category": f"HTTP {e.code}",
                    "tier": 2,
                    "subtier": 1,
                    "speed_kb_s": 0.0,
                    "ttfb": 999999
                }
        except Exception as e:
            err_str = str(e)
            if any(w in err_str for w in ["Name or service not known", "Errno -2", "CERTIFICATE_VERIFY_FAILED", "Connection refused"]):
                return {
                    "site": site,
                    "orig_name": original_name,
                    "new_name": f"{original_name} |死链",
                    "category": "域名失效/死链",
                    "tier": 2,
                    "subtier": 1,
                    "speed_kb_s": 0.0,
                    "ttfb": 999999
                }

    # 7. 梯队 2：其余所有影视点播站执行方案 B 测速
    probe_url = explicit_url
    if not probe_url:
        probe_url = SITE_PROBE_ENDPOINTS.get(key)
    if not probe_url:
        for k in SITE_PROBE_ENDPOINTS:
            if k in name:
                probe_url = SITE_PROBE_ENDPOINTS[k]
                break

    if probe_url:
        speed_tag, speed_kb_s, ttfb = test_service_speed(probe_url, timeout=min(timeout, 4))
        is_timeout = (speed_tag == " |0")
        category = "点播源 (方案B测速)" if not is_timeout else "点播源 (不可用/0速)"
        subtier = 1 if is_timeout else 0 # 0=测通优先，1=0速沉底
    else:
        # 无明文探测 URL 的内置/私有爬虫源：绝不妄扣 |0 标签，保持原名正常保活！
        speed_tag = ""
        speed_kb_s = 500.0
        ttfb = 500
        is_timeout = False
        category = "点播源 (内置协议/保活)"
        subtier = 0

    # 启用聚搜与换源联动
    site["searchable"] = 1
    site["quickSearch"] = 1
    site["changeable"] = 1

    return {
        "site": site,
        "orig_name": original_name,
        "new_name": f"{original_name}{speed_tag}",
        "category": category,
        "tier": 2,
        "subtier": subtier,
        "speed_kb_s": speed_kb_s,
        "ttfb": ttfb
    }

def process_file(target_path: str, output_path: str = None) -> bool:
    if not os.path.exists(target_path):
        print(f"❌ 找不到输入文件: {target_path}")
        return False

    base_no_ext = os.path.splitext(target_path)[0]
    filename = os.path.basename(base_no_ext)
    if filename.endswith("_original_raw"):
        out_name = filename.replace("_original_raw", "")
    else:
        out_name = filename

    if not output_path:
        output_path = f"{out_name}_fix.json"
    elif os.path.isdir(output_path):
        output_path = os.path.join(output_path, f"{out_name}_fix.json")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    print("==================================================")
    print("🚀 TVBox 极简打标与大屏 6 梯队优化重排流水线 (超时标记为 0)")
    print(f"📂 原始输入文件: {target_path}")
    print(f"📁 处理输出文件: {output_path}")
    print("==================================================")

    with open(target_path, "r", encoding="utf-8-sig") as f:
        raw_text = f.read()

    cleaned_text = clean_comments_and_commas(raw_text)
    # 铁律第一步：严格检查是否有语法错误
    try:
        data = json.loads(cleaned_text)
    except Exception as e:
        print(f"❌ [语法熔断] JSON 语法致命错误: {e}，一切白干，直接阻断！\n")
        return False

    # 智能前置自动修复：解析相对路径并补全为绝对 CDN 路径
    data = auto_repair_source(data, file_key=out_name)

    # 铁律第二步：测试 Jar 是否真实有效，禁止一切白干
    spider_ok, spider_msg = check_and_fix_spider(data, out_name)
    if not spider_ok:
        print(f"❌ [Jar熔断] Spider 爬虫质检未通过: {spider_msg}，一切白干，直接阻断！\n")
        return False

    # 用户特批例外：pg 源不经过测速打标与重排，完整保留原源 JSON 结构（仅修复 Jar 确保加载正常）
    if out_name in ["pg", "fun"]:
        print(f"⭐ [{out_name}] 触发用户特批例外规则：跳过测速打标与 6 梯队重排，直接 100% 保持原始源结构落盘！")
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 输出文件落地: {output_path}\n")
        return True

    raw_sites = data.get("sites") or []
    sites = [s for s in raw_sites if isinstance(s, dict)]
    print(f"📊 读取到站点总数: {len(sites)} 行")
    print(f"⚡ 启动多线程并发特征打标与真实健康测速...\n")

    start_time = time.time()
    with ThreadPoolExecutor(max_workers=16) as executor:
        results = list(executor.map(classify_and_tag, sites))
    elapsed = time.time() - start_time

    # 核心：大屏 6 梯队多级重排逻辑
    sorted_results = sorted(
        results, 
        key=lambda r: (r["tier"], r["subtier"], -r["speed_kb_s"], r["ttfb"])
    )

    # 组装最终 sites 数组
    sorted_sites = []
    for r in sorted_results:
        site_obj = r["site"]
        site_obj["name"] = r["new_name"]
        sorted_sites.append(site_obj)

    data["sites"] = sorted_sites

    # 全局净屏：彻底清除所有外挂弹幕接口与开关
    clean_danmaku(data)

    # 电视直播源净化：仅保留正规电视广播专线，彻底清除网络轮播与失效死链
    clean_lives(data)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 终极回环核验：再次反向加载写出文件，确保 100% 绝对合规无语法损伤
    try:
        with open(output_path, "r", encoding="utf-8") as f_check:
            json.load(f_check)
    except Exception as e:
        print(f"❌ [写出校验失败] 落盘文件损坏: {e}")
        return False

    print(f"✅ 处理并重排完成！全流程耗时: {elapsed:.2f} 秒")
    print(f"💾 输出文件落地: {output_path}\n")
    return True

def main():
    if len(sys.argv) > 1:
        target_path = sys.argv[1]
        out_arg = sys.argv[2] if len(sys.argv) > 2 else None
        process_file(target_path, out_arg)
    else:
        # 默认模式：自动批量处理 source/ 下的所有 JSON，统一输出到 yy/
        source_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "source")
        yy_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yy")
        
        if os.path.exists(source_dir):
            json_files = sorted([f for f in os.listdir(source_dir) if f.endswith(".json")])
            if json_files:
                print(f"📦 发现 source/ 目录下待处理源: {len(json_files)} 个 ({', '.join(json_files)})")
                for jf in json_files:
                    in_path = os.path.join(source_dir, jf)
                    process_file(in_path, yy_dir)
                return

        # 若无 source 目录则回退到原默认单文件
        process_file("fanty_original_raw.json")

if __name__ == "__main__":
    main()
