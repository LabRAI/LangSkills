# 软件包管理（参数化）：apt/dnf/pacman 安装/更新/回滚思路

## Goal
- 在不同发行版上安全管理软件包（apt/dnf/pacman）：先预览变更，再安装/升级/删除，并保留回滚路径。

## When to use
- 需要安装缺失工具或安全更新
- 需要升级某个依赖并验证兼容性
- 需要卸载冲突包或清理旧版本

## When NOT to use
- 生产环境临时升级且没有维护窗口/回滚方案（高风险）

## Prerequisites
- Environment: Linux（不同发行版包管理器不同）
- Permissions: 通常需要 sudo/root
- Tools: `apt-get` 或 `dnf` 或 `pacman`
- Inputs needed: 包名（可选版本）+ 期望动作（install/upgrade/remove）

## Steps (<= 12)
1. 识别包管理器：Debian/Ubuntu 用 apt；RHEL/Fedora 用 dnf；Arch 用 pacman（按系统选择对应命令）[[1][2][3]]
2. 刷新索引：apt `sudo apt-get update`；dnf `sudo dnf makecache`；pacman `sudo pacman -Syu`（避免只 -Sy）[[1][2][3]]
3. 安装包：apt `sudo apt-get install <pkg>`；dnf `sudo dnf install <pkg>`；pacman `sudo pacman -S <pkg>`[[1][2][3]]
4. 升级：apt `sudo apt-get upgrade`/`dist-upgrade`；dnf `sudo dnf upgrade`；pacman `sudo pacman -Syu`[[1][2][3]]
5. 卸载：apt `remove/purge`；dnf `remove`；pacman `-R/-Rns`（谨慎清依赖）[[1][2][3]]
6. 回滚思路：apt 指定版本安装；dnf `downgrade`；pacman 用缓存包 `pacman -U /var/cache/pacman/pkg/...`[[1][2][3]]

## Verification
- 确认目标包版本：`<tool> --version` 或查询包信息（apt-cache/dnf info/pacman -Qi）
- 运行依赖该包的服务/脚本做一次冒烟测试

## Safety & Risk
- Risk level: **high**
- Irreversible actions: 升级/移除可能引入依赖变更导致服务不可用；回滚不一定总能成功
- Privacy/credential handling: 无（但在工单里避免暴露内部仓库地址与 token）
- Confirmation requirement: 生产环境变更前必须预览要安装/删除的包列表并确认维护窗口；高风险变更保留回滚包/快照

## Troubleshooting
- See: reference/troubleshooting.md

## Sources
- [1] Debian man: apt-get(8): https://manpages.debian.org/bookworm/apt/apt-get.8.en.html
- [2] DNF docs: command reference: https://dnf.readthedocs.io/en/latest/command_ref.html
- [3] Arch man: pacman(8): https://man.archlinux.org/man/pacman.8.en.txt
