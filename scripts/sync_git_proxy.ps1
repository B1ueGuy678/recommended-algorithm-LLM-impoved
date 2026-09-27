<#
.SYNOPSIS
    把 git 的 http.proxy 同步到「当前」Windows 系统代理端口。

.DESCRIPTION
    为什么需要这个脚本：
      VPN / 代理客户端（本项目实测为 Clash 内核的「星驰加速器」）启动时会随机挑一个
      空闲本地端口（Clash 配置里的 mixed-port: 0 即此含义），所以端口每次都可能变。

      而 git **不会读 Windows 系统代理设置**，它只用 .git/config 里写死的 http.proxy。
      端口一变，git 就在敲一个已经关掉的门，报：

          fatal: unable to access 'https://github.com/...': Failed to connect to
          github.com port 443 via 127.0.0.1 after 2101 ms: Could not connect to server

      注意报错里的 "via 127.0.0.1"——它说明 git 正在走代理、而不是直连。
      看到这个句式，第一反应应该是「代理端口对不上」，而不是「GitHub 被墙了」。

    本脚本从注册表读当前端口，同步到本仓库的 git 配置，然后验证连通性。

.PARAMETER NoVerify
    跳过连通性验证（不访问网络）。

.PARAMETER Quiet
    只在端口发生变化时输出。

.EXAMPLE
    pwsh -File scripts\sync_git_proxy.ps1

.EXAMPLE
    # 想每次开终端自动同步，把下面这行加进 $PROFILE：
    #   & "D:\DeepSeek\recommended algorithm-LLM-impoved\scripts\sync_git_proxy.ps1" -Quiet
#>
[CmdletBinding()]
param(
    [switch]$NoVerify,
    [switch]$Quiet
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$RegPath  = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings'

function Say($msg, $color = 'Gray') {
    if (-not $Quiet) { Write-Host $msg -ForegroundColor $color }
}

# --- 1. 读当前系统代理 -----------------------------------------------------
$settings = Get-ItemProperty -Path $RegPath -ErrorAction SilentlyContinue
if ($null -eq $settings) {
    Write-Host "[x] 读不到注册表项：$RegPath" -ForegroundColor Red
    exit 1
}

if (-not $settings.ProxyEnable) {
    Write-Host "[!] 系统代理当前是关闭的（ProxyEnable=0），但 git 里可能还留着旧的 http.proxy。" -ForegroundColor Yellow
    Write-Host "    两种情况分开处理：" -ForegroundColor Yellow
    Write-Host "      a) 你的 VPN 用的是 TUN / 全局模式 -> 根本不需要 git 代理，清掉它：" -ForegroundColor Yellow
    Write-Host "           git -C `"$RepoRoot`" config --unset http.proxy" -ForegroundColor Yellow
    Write-Host "      b) VPN 没开 -> 先启动它，再重跑本脚本。" -ForegroundColor Yellow
    exit 2
}

$m = [regex]::Match([string]$settings.ProxyServer, '127\.0\.0\.1:(\d+)')
if (-not $m.Success) {
    Write-Host "[!] 系统代理不是本机回环地址：$($settings.ProxyServer)" -ForegroundColor Yellow
    Write-Host "    请手动指定：git -C `"$RepoRoot`" config http.proxy `"http://<host>:<port>`"" -ForegroundColor Yellow
    exit 3
}
$port    = $m.Groups[1].Value
$newProxy = "http://127.0.0.1:$port"

# --- 2. 读 git 现有配置 ----------------------------------------------------
$oldProxy = (& git -C $RepoRoot config --get http.proxy) 2>$null
if ($null -eq $oldProxy) { $oldProxy = '' }

if ($oldProxy -eq $newProxy) {
    Say "[=] git 代理已是最新：$newProxy" 'Green'
} else {
    # 端口变化一定要说出来：这是本脚本存在的理由，静默修改会让人以为配置没被动过
    Write-Host "[*] git 代理端口已过期，正在同步：" -ForegroundColor Cyan
    Write-Host "      旧：$(if ($oldProxy) { $oldProxy } else { '(未设置)' })" -ForegroundColor DarkGray
    Write-Host "      新：$newProxy" -ForegroundColor Cyan
    & git -C $RepoRoot config http.proxy $newProxy
}

# --- 3. 顺手保证另一项必需配置 --------------------------------------------
# 本机 schannel 报 SEC_E_NO_CREDENTIALS，必须用 openssl 后端。
$ssl = (& git -C $RepoRoot config --get http.sslBackend) 2>$null
if ($ssl -ne 'openssl') {
    & git -C $RepoRoot config http.sslBackend openssl
    Say "[*] 已设置 http.sslBackend=openssl（本机 schannel 会报 SEC_E_NO_CREDENTIALS）" 'Cyan'
}

# --- 4. 验证连通性 --------------------------------------------------------
if ($NoVerify) { exit 0 }

Say "[*] 验证连通性（git ls-remote，不需要推送权限）..." 'Gray'
$out = & git -C $RepoRoot ls-remote origin HEAD 2>&1
if ($LASTEXITCODE -eq 0) {
    Say "[ok] 链路通了：$out" 'Green'
    exit 0
} else {
    Write-Host "[x] 仍然连不上。当前 git 代理 = $newProxy" -ForegroundColor Red
    Write-Host "    $out" -ForegroundColor DarkRed
    Write-Host "    排查顺序：" -ForegroundColor Yellow
    Write-Host "      1) 代理客户端是否在跑：netstat -ano | Select-String ':<port> '" -ForegroundColor Yellow
    Write-Host "      2) 注册表里的端口是否是权威值：ProxyServer = $($settings.ProxyServer)" -ForegroundColor Yellow
    Write-Host "      3) 注意 DSH 沙箱内 get-nettcpconnection / curl.exe 会给出假阴性" -ForegroundColor Yellow
    exit 4
}
