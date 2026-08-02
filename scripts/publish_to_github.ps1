[CmdletBinding()]
param(
    [string]$RepoOwner = "masei17021987-afk",
    [string]$RepoName = "CryptoHunter-Neural-Scalper",
    [ValidateSet("private", "public")]
    [string]$Visibility = "private"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$FullRepo = "$RepoOwner/$RepoName"
$Description = "Локальная нейросетевая лаборатория скальпинга по стакану с paper-trading"

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Refresh-ToolPath {
    $known = @(
        "C:\Program Files\Git\cmd",
        "C:\Program Files\GitHub CLI",
        "$env:LOCALAPPDATA\Programs\GitHub CLI"
    )
    foreach ($item in $known) {
        if ((Test-Path $item) -and ($env:Path -notlike "*$item*")) {
            $env:Path = "$item;$env:Path"
        }
    }
}

function Ensure-Tool([string]$CommandName, [string]$WingetId, [string]$DisplayName) {
    Refresh-ToolPath
    if (Get-Command $CommandName -ErrorAction SilentlyContinue) {
        return
    }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        throw "$DisplayName не найден, а winget недоступен. Установите $DisplayName вручную и повторите запуск."
    }
    Write-Step "Установка $DisplayName"
    & winget install --id $WingetId -e --source winget --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        throw "winget не смог установить $DisplayName (код $LASTEXITCODE)."
    }
    Refresh-ToolPath
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "$DisplayName установлен, но текущий процесс его не видит. Закройте окно и снова запустите PUBLISH_TO_GITHUB.bat."
    }
}

Write-Host "Проект: $ProjectRoot"
Write-Host "Репозиторий: $FullRepo"
Write-Host "Видимость: $Visibility"

Ensure-Tool -CommandName "git" -WingetId "Git.Git" -DisplayName "Git"
Ensure-Tool -CommandName "gh" -WingetId "GitHub.cli" -DisplayName "GitHub CLI"

Write-Step "Проверка авторизации GitHub"
& gh auth status --hostname github.com 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Откроется браузер. Авторизуйтесь в нужном GitHub-аккаунте." -ForegroundColor Yellow
    & gh auth login --hostname github.com --git-protocol https --web
    if ($LASTEXITCODE -ne 0) {
        throw "Авторизация GitHub CLI не завершена."
    }
}

Push-Location $ProjectRoot
try {
    Write-Step "Подготовка локального Git-репозитория"
    & git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        & git init -b main
        if ($LASTEXITCODE -ne 0) { throw "Не удалось выполнить git init." }
    }

    & git branch -M main

    $userName = (& git config user.name 2>$null)
    if (-not $userName) {
        & git config user.name "CryptoHunter"
    }
    $userEmail = (& git config user.email 2>$null)
    if (-not $userEmail) {
        & git config user.email "267742595+${RepoOwner}@users.noreply.github.com"
    }

    Write-Step "Проверка файлов перед коммитом"
    & git add -A
    if ($LASTEXITCODE -ne 0) { throw "git add завершился ошибкой." }

    & git diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        & git commit -m "Первый релиз с полной русской документацией"
        if ($LASTEXITCODE -ne 0) { throw "Не удалось создать commit." }
    } else {
        Write-Host "Новых изменений для коммита нет."
    }

    Write-Step "Проверка удалённого репозитория"
    & gh repo view $FullRepo *> $null
    $repoExists = ($LASTEXITCODE -eq 0)

    if (-not $repoExists) {
        Write-Step "Создание $Visibility-репозитория и первая отправка"
        $visibilityFlag = if ($Visibility -eq "public") { "--public" } else { "--private" }
        & gh repo create $FullRepo $visibilityFlag --description $Description --source . --remote origin --push
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub CLI не смог создать или отправить репозиторий."
        }
    } else {
        Write-Step "Репозиторий уже существует — безопасная отправка без force"
        $targetUrl = "https://github.com/$FullRepo.git"
        & git remote get-url origin *> $null
        if ($LASTEXITCODE -eq 0) {
            & git remote set-url origin $targetUrl
        } else {
            & git remote add origin $targetUrl
        }
        & git push -u origin main
        if ($LASTEXITCODE -ne 0) {
            throw "Push отклонён. Скрипт намеренно не применяет force push. Проверьте историю удалённого репозитория."
        }
    }

    Write-Step "Создание и отправка тега версии"
    & git rev-parse -q --verify "refs/tags/v0.1.1" *> $null
    if ($LASTEXITCODE -ne 0) {
        & git tag -a v0.1.1 -m "CryptoHunter Neural Scalper 0.1.1"
        if ($LASTEXITCODE -ne 0) { throw "Не удалось создать тег v0.1.1." }
    }
    & git push origin v0.1.1
    if ($LASTEXITCODE -ne 0) {
        throw "Не удалось отправить тег v0.1.1. Force push намеренно не используется."
    }

    Write-Step "Финальная проверка"
    & gh repo view $FullRepo --json nameWithOwner,isPrivate,defaultBranchRef,url
    if ($LASTEXITCODE -ne 0) { throw "Не удалось прочитать созданный репозиторий." }

    Write-Host "`nГотово: https://github.com/$FullRepo" -ForegroundColor Green
    & gh repo view $FullRepo --web
}
finally {
    Pop-Location
}
