<#
.SYNOPSIS
  Prepare a direct GitHub collaborator's personal branch and local safety hooks.
.DESCRIPTION
  Run only in a clean clone of kasra-dastranj/telegram-card-game-bot.
  This script never changes main, production data, or the VPS.
#>
param(
    [ValidatePattern('^[A-Za-z0-9-]+$')]
    [string]$GitHubUser
)

$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location -LiteralPath $projectRoot

function Invoke-Git {
    & git @args
    if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') failed ($LASTEXITCODE)" }
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw 'Git is required.' }
$origin = (& git remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or $origin -notmatch '(?i)github\.com[:/]kasra-dastranj/telegram-card-game-bot(\.git)?$') {
    throw "Unexpected origin: $origin"
}
if (& git status --porcelain) { throw 'Working tree is not clean. Commit or move your changes before setup.' }

if (-not $GitHubUser -and (Get-Command gh -ErrorAction SilentlyContinue)) {
    $login = & gh api user --jq .login 2>$null
    if ($LASTEXITCODE -eq 0 -and $login) { $GitHubUser = $login.Trim() }
}
if (-not $GitHubUser -or $GitHubUser -notmatch '^[A-Za-z0-9-]+$') {
    throw 'Sign in with gh auth login, or rerun with -GitHubUser YOUR_GITHUB_USERNAME.'
}
if (-not (& git config user.name) -or -not (& git config user.email)) {
    throw 'Set your own git user.name and user.email first; never use the owner identity.'
}

$branch = "collab/$GitHubUser"
Invoke-Git fetch origin main
& git show-ref --verify --quiet "refs/heads/$branch"
if ($LASTEXITCODE -eq 0) {
    Invoke-Git switch $branch
} else {
    $remoteBranch = & git ls-remote --heads origin "refs/heads/$branch"
    if ($LASTEXITCODE -ne 0) { throw 'Could not check the personal branch on GitHub.' }
    if ($remoteBranch) {
        Invoke-Git fetch origin "refs/heads/${branch}:refs/remotes/origin/${branch}"
        Invoke-Git switch --track -c $branch "origin/$branch"
    } else {
        Invoke-Git switch -c $branch origin/main
    }
}

Invoke-Git config --local telbattle.collaboratorBranch $branch
Invoke-Git config --local core.hooksPath scripts/git-hooks/collaborator
Invoke-Git push -u origin "HEAD:refs/heads/$branch"

Write-Host "Ready on $branch. Every commit on this branch will be pushed to origin/$branch."
Write-Host 'The local hooks block commits on other branches and pushes to other remote branches.'
