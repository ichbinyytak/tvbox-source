# TVBox 精选多源保鲜自动化与 6 梯队优化流水线

[![GitHub License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![TVBox Compatible](https://img.shields.io/badge/TVBox-Compatible-brightgreen.svg)](#)
[![Auto Freshness](https://img.shields.io/badge/保鲜机制-30天动态淘汰-orange.svg)](#)

本项目是专为 **TVBox / 影视仓 / FongMi / 猫影视** 等大屏客户端量身打造的**全自动化上游源拉取、智能修复、真实吞吐测速与 6 梯队重排流水线**。

---

## 🌟 核心特性与设计规范

1. **准入前置双铁律 · 杜绝电视报错**：
   - **铁律一（严格语法准入）**：全自动清洗非标准注释与尾随逗号，并通过严格 `json.loads` 核验。任何损坏或格式错误源立即熔断，绝不放行。
   - **铁律二（Spider Jar 探活与自动补全）**：真实探活目标 Jar 地址（HTTP 200/206 与 Zip/Dex 魔数校验）。严禁无法解析的相对路径（`./jar/` 或 `./py/`），自动将其展开为高可用 CDN 绝对路径；探活失败自动重定向至备用高可用 Jar 镜像，根治“加载 jar 失败”。
2. **全员保活 · 绝不误杀**：
   - 完整保留上游所有站点，不设粗暴死黑名单。对于内置 Java 爬虫（`csp_xxx`）的点播源保持正常保活，绝不乱标死链。
3. **真实宽带测速 · 极简打标**：
   - 采用 **` |{下载速度}|{延迟}`** 格式（例如 ` |4.5M|220ms`），直观呈现当前网络连通质量；
   - 真实探测超时或死链站点统一标记为 ` |0` 并沉底排列。
4. **大屏搜索 6 梯队物理重排体系**：
   - **第 1 梯队**：首页排头兵（豆豆/片单/切源索引，固定第 1 位）
   - **第 2 梯队**：直链影视点播类（按真实握手延迟与下载速度降序物理重排，快源在前，0 速沉底）
   - **第 3 梯队**：高清磁力类（标记为 ` |磁力`，4K 离线加速）
   - **第 4 梯队**：垂直非影视类（标记为 ` |非影`，少儿教育、动漫、听书、儿歌、音乐、体育等）
   - **第 5 梯队**：网盘扫码类（标记为 ` |盘`，花卷、玩偶、多多、木偶等，免测速放后部展示）
   - **第 6 梯队**：JS 脚本引擎类（标记为 ` |js`，兜底展示）
5. **动态保鲜淘汰机制（30 天淘汰制）**：
   - 自动检测 GitHub Commit 提交时间与内容变更指纹。若上游源超过 30 天未更新，自动判定为弃坑断更源并淘汰，保持源库持续鲜活。
6. **全局净屏与电视直播专线**：
   - 彻底关闭全局与站点外挂弹幕开关，杜绝大屏飘字挡屏；
   - 直播源保留正规电视广播专线，剔除网络录像与垃圾轮播。

---

## 📺 客户端接口使用地址

### 1. 主推接口 (主页推荐配置)
- **国内加速地址 (推荐)**：
  ```text
  https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/my_box.json
  ```
- **GitHub 直连地址**：
  ```text
  https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/my_box.json
  ```

---

### 2. 精选优化单源一览 (6 梯队加工版)

| 源名称 | 标识 (`key`) | 包含站点数 | 加速订阅地址 |
| :--- | :---: | :---: | :--- |
| **饭太硬** | `fty` | 48 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/fty_fix.json` |
| **玩偶影视 (原版结构)** | `pg` | 87 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/pg_fix.json` |
| **OK宝盒** | `ok` | 101 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/ok_fix.json` |
| **王二小** | `wex` | 98 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/wex_fix.json` |
| **潇洒** | `xiaosa` | 111 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/xiaosa_fix.json` |
| **肥猫** | `feimao` | 41 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/feimao_fix.json` |
| **摸鱼** | `moyu` | 104 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/moyu_fix.json` |
| **摸鱼4K** | `moyu4k` | 104 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/moyu4k_fix.json` |
| **南风** | `nanfeng` | 91 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/nanfeng_fix.json` |
| **TVBox官方** | `tvboxorg` | 160 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/tvboxorg_fix.json` |
| **二月红** | `eyh` | 28 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/eyh_fix.json` |
| **牛二** | `niu2` | 63 | `https://gh-proxy.com/https://raw.githubusercontent.com/ichbinyytak/tvbox-source/main/yy/niu2_fix.json` |

---

## 🛠️ 本地运行与自动化

```bash
# 1. 抓取各源最新数据并执行保鲜质检、相对路径修复落盘至 source/
python3 fetch_sources.py

# 2. 执行多线程并发真实测速、特征分类与 6 梯队优化重排输出至 yy/
python3 test_and_fix.py
```

## 📄 许可协议
本项目基于 [MIT License](LICENSE) 开源。所有规则与数据接口仅供个人学习、技术研究与大屏体验优化之用，请勿用于非法用途。
