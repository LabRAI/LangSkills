param(
  [switch]$Overwrite
)

$ErrorActionPreference = "Stop"

function Ensure-Newline([string]$text) {
  if ($null -eq $text) { return "`n" }
  if ($text.EndsWith("`n")) { return $text }
  return $text + "`n"
}

function Write-Utf8NoBomFile([string]$path, [string]$content) {
  $content = Ensure-Newline $content
  $dir = Split-Path -Parent $path
  if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
  }

  if (-not $Overwrite -and (Test-Path $path)) {
    return
  }

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [System.IO.File]::WriteAllText($path, $content, $utf8NoBom)
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")

$linuxReadmePath = Join-Path $repoRoot "skills/linux/README.md"

$topics = @(
  @{ topic = "filesystem"; slug = "find-files"; title = "用 find 精准查找文件与目录（按名称/时间/大小）"; risk = "medium" },
  @{ topic = "filesystem"; slug = "locate-which-whereis"; title = "用 locate/which/whereis/type 快速定位命令与路径"; risk = "low" },
  @{ topic = "filesystem"; slug = "safe-delete"; title = "安全删除文件：rm 的正确姿势与先预览后删除"; risk = "high" },
  @{ topic = "filesystem"; slug = "symlink-hardlink"; title = "创建与管理链接：符号链接 vs 硬链接（ln）"; risk = "low" },
  @{ topic = "filesystem"; slug = "permissions-chmod"; title = "文件权限入门：chmod 数字/符号写法与常见坑"; risk = "medium" },
  @{ topic = "filesystem"; slug = "ownership-chown"; title = "所有者与用户组：chown/chgrp 递归修改与安全边界"; risk = "medium" },
  @{ topic = "filesystem"; slug = "acl-basics"; title = "ACL 权限：getfacl/setfacl 做精细授权"; risk = "medium" },
  @{ topic = "filesystem"; slug = "disk-usage-du-df"; title = "磁盘空间排查：df/du 找出占用最大的目录与文件"; risk = "medium" },
  @{ topic = "filesystem"; slug = "archive-tar"; title = "打包与解包：tar（含 gzip/xz）最佳实践"; risk = "low" },

  @{ topic = "text"; slug = "view-files-less-tail"; title = "查看文件与日志：less/head/tail -f 的实战用法"; risk = "low" },
  @{ topic = "text"; slug = "search-grep-ripgrep"; title = "文本搜索：grep（或 rg）按关键字/正则定位问题"; risk = "low" },
  @{ topic = "text"; slug = "replace-sed"; title = "批量替换：sed 常见替换、就地修改与备份策略"; risk = "medium" },
  @{ topic = "text"; slug = "parse-awk"; title = "结构化文本处理：awk 提取列、统计、聚合"; risk = "low" },

  @{ topic = "network"; slug = "download-curl-wget"; title = "下载与 HTTP 调试：curl/wget（header、重试、代理）"; risk = "low" },
  @{ topic = "network"; slug = "dns-dig-nslookup"; title = "DNS 排查：dig/nslookup 看解析链路与 TTL"; risk = "low" },
  @{ topic = "network"; slug = "connectivity-ping-traceroute"; title = "连通性诊断：ping/traceroute（或 tracepath）"; risk = "low" },
  @{ topic = "network"; slug = "ports-ss-lsof"; title = "端口与进程：ss/lsof 找出谁在监听哪个端口"; risk = "medium" },

  @{ topic = "ssh"; slug = "ssh-keys"; title = "SSH 密钥登录：ssh-keygen + authorized_keys + ssh-agent"; risk = "medium" },
  @{ topic = "ssh"; slug = "scp-rsync"; title = "文件传输：scp vs rsync（增量、断点、权限保留）"; risk = "medium" },

  @{ topic = "process"; slug = "ps-top-kill"; title = "进程管理：ps/top/kill（含信号与优雅退出）"; risk = "high" },
  @{ topic = "process"; slug = "background-nohup"; title = "后台任务：nohup、&、disown 与日志重定向"; risk = "medium" },
  @{ topic = "process"; slug = "tmux-session"; title = "会话保持：tmux（创建/分离/恢复）"; risk = "low" },

  @{ topic = "system"; slug = "system-info-uname-dmesg"; title = "系统信息与启动排查：uname/lsb_release/dmesg"; risk = "low" },
  @{ topic = "system"; slug = "resources-free-vmstat"; title = "资源诊断：free/vmstat/iostat 区分 CPU/内存/IO 瓶颈"; risk = "low" },

  @{ topic = "systemd"; slug = "systemctl-service-status"; title = "systemd 服务管理：systemctl 状态/启动/重启/自启"; risk = "high" },
  @{ topic = "systemd"; slug = "journalctl-logs"; title = "systemd 日志：journalctl 按服务/时间/级别过滤"; risk = "low" },

  @{ topic = "scheduling"; slug = "cron-basics"; title = "定时任务：cron/crontab（环境差异与日志）"; risk = "medium" },

  @{ topic = "packages"; slug = "package-manager-basics"; title = "软件包管理（参数化）：apt/dnf/pacman 安装/更新/回滚思路"; risk = "high" },

  @{ topic = "users"; slug = "user-group-management"; title = "用户与组管理：useradd/usermod/groups（含 sudo 组）"; risk = "high" },

  @{ topic = "security"; slug = "sudoers-best-practice"; title = "sudo 最佳实践：visudo 编辑 sudoers、最小授权与审计"; risk = "high" }
)

function Skill-SkillMd([string]$title, [string]$risk) {
@"
# $title

## Goal
- TODO

## When to use
- TODO

## When NOT to use
- TODO

## Prerequisites
- Environment:
- Permissions:
- Tools:
- Inputs needed:

## Steps (<= 12)
1. TODO

## Verification
- TODO

## Safety & Risk
- Risk level: **$risk**
- Irreversible actions:
- Privacy/credential handling:
- Confirmation requirement:

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] TODO
- [2] TODO
- [3] TODO
"@
}

function Skill-LibraryMd() {
@'
# Library

## Copy-paste commands

```bash
# TODO
```

## Prompt snippet

```text
TODO
```
'@
}

function Skill-MetadataYaml([string]$topic, [string]$slug, [string]$title, [string]$risk) {
@"
id: linux/$topic/$slug
title: "$title"
domain: linux
level: bronze
risk_level: $risk
platforms: [linux]
tools: [bash]
tags: []
last_verified: ""
owners: []
aliases: []
"@
}

function Skill-ReferenceSourcesMd() {
@"
# Sources

> 每条来源需包含：URL、摘要、访问日期，以及它支撑了哪一步。

## [1]
- URL: TODO
- Accessed: YYYY-MM-DD
- Summary: TODO
- Supports: TODO

## [2]
- URL: TODO
- Accessed: YYYY-MM-DD
- Summary: TODO
- Supports: TODO

## [3]
- URL: TODO
- Accessed: YYYY-MM-DD
- Summary: TODO
- Supports: TODO
"@
}

function Skill-ReferenceTroubleshootingMd() {
@"
# Troubleshooting

TODO: 记录常见失败现象、原因、修复方式与验证方法。
"@
}

function Skill-ReferenceEdgeCasesMd() {
@"
# Edge cases

TODO: 记录版本差异、边界条件与容易踩坑的组合。
"@
}

function Skill-ReferenceExamplesMd() {
@"
# Examples

TODO: 放更长的可复制示例（避免塞进 skill.md）。
"@
}

function Skill-ReferenceChangelogMd() {
@"
# Changelog

- YYYY-MM-DD: init skeleton
"@
}

New-Item -ItemType Directory -Path (Join-Path $repoRoot "skills/linux") -Force | Out-Null

# skills/linux/README.md
$linuxReadmeLines = @()
$linuxReadmeLines += "# Linux Skills"
$linuxReadmeLines += ""
$linuxReadmeLines += "本目录包含 Linux domain 的初始骨架（30 个主题）。"
$linuxReadmeLines += ""
$linuxReadmeLines += "## 目录约定"
$linuxReadmeLines += ""
$linuxReadmeLines += '- 路径：`skills/linux/<topic>/<slug>/`'
$linuxReadmeLines += '- 每个 skill：`skill.md` + `library.md` + `metadata.yaml` + `reference/`'
$linuxReadmeLines += ""
$linuxReadmeLines += "## Topics"
$linuxReadmeLines += ""
$linuxReadmeLines += "| ID | Path | Risk |"
$linuxReadmeLines += "|---:|---|---:|"

$index = 1
foreach ($t in $topics) {
  $path = "skills/linux/$($t.topic)/$($t.slug)/"
  $linuxReadmeLines += ('| {0} | `{1}` | **{2}** |' -f $index, $path, $t.risk)
  $index++
}

Write-Utf8NoBomFile -path $linuxReadmePath -content ($linuxReadmeLines -join "`n")

# per-skill skeleton
foreach ($t in $topics) {
  $skillDir = Join-Path $repoRoot "skills/linux/$($t.topic)/$($t.slug)"
  New-Item -ItemType Directory -Path (Join-Path $skillDir "reference") -Force | Out-Null

  Write-Utf8NoBomFile -path (Join-Path $skillDir "skill.md") -content (Skill-SkillMd -title $t.title -risk $t.risk)
  Write-Utf8NoBomFile -path (Join-Path $skillDir "library.md") -content (Skill-LibraryMd)
  Write-Utf8NoBomFile -path (Join-Path $skillDir "metadata.yaml") -content (Skill-MetadataYaml -topic $t.topic -slug $t.slug -title $t.title -risk $t.risk)

  $refDir = Join-Path $skillDir "reference"
  Write-Utf8NoBomFile -path (Join-Path $refDir "sources.md") -content (Skill-ReferenceSourcesMd)
  Write-Utf8NoBomFile -path (Join-Path $refDir "troubleshooting.md") -content (Skill-ReferenceTroubleshootingMd)
  Write-Utf8NoBomFile -path (Join-Path $refDir "edge-cases.md") -content (Skill-ReferenceEdgeCasesMd)
  Write-Utf8NoBomFile -path (Join-Path $refDir "examples.md") -content (Skill-ReferenceExamplesMd)
  Write-Utf8NoBomFile -path (Join-Path $refDir "changelog.md") -content (Skill-ReferenceChangelogMd)
}

Write-Host "Linux skeleton created: $($topics.Count) skills" -ForegroundColor Green
