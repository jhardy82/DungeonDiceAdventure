<#
.SYNOPSIS
    Sets up and starts Battle Dice from source on Windows.

.DESCRIPTION
    Idempotent launcher. Each run it:
      1. Finds a Python 3.15 interpreter (py launcher first, then python on PATH).
      2. Creates the .venv virtual environment if it is missing or built on another Python.
      3. Installs the game into .venv only when pyproject.toml changed since the last install.
      4. Starts the game.

    It never installs Python itself and never changes machine-wide settings. Everything it
    creates lives in the .venv folder inside the repository.

.PARAMETER Seed
    Root seed for every run, so dice and enemy choices repeat exactly. Unsigned integer.

.PARAMETER Size
    Window size as WIDTHxHEIGHT. Minimum supported is 960x540.

.PARAMETER LogDir
    Folder for JSONL event logs. Defaults to the logs folder in the repository.

.PARAMETER Reinstall
    Delete .venv and build it again from scratch.

.PARAMETER NoLaunch
    Set everything up, then exit without starting the game.

.EXAMPLE
    .\scripts\Start-BattleDice.ps1

.EXAMPLE
    .\scripts\Start-BattleDice.ps1 -Seed 123 -Size 960x540

.NOTES
    Works in Windows PowerShell 5.1 and PowerShell 7+.
#>
[CmdletBinding()]
param(
    [ValidatePattern('^\d{1,20}$')]
    [string]$Seed,

    [ValidatePattern('^\d{3,5}x\d{3,5}$')]
    [string]$Size = '1280x720',

    [string]$LogDir,

    [switch]$Reinstall,

    [switch]$NoLaunch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region VARIABLES
$RequiredVersion = [version]'3.15'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ProjectFile = Join-Path $RepoRoot 'pyproject.toml'
$VenvDir = Join-Path $RepoRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$StampFile = Join-Path $VenvDir '.battle-dice-install-stamp'
$VersionProbe = "import sys; print('%d.%d.%d' % sys.version_info[:3])"
$DownloadPage = 'https://www.python.org/downloads/windows/'
#endregion VARIABLES

#region FUNCTIONS
function Write-Status {
    <# Progress line for the person running the launcher. #>
    param([Parameter(Mandatory)][string]$Message)
    Write-Information -MessageData "[Battle Dice] $Message" -InformationAction Continue
}

function Get-PythonVersion {
    <# Returns the [version] of a Python command, or $null if it is missing or not runnable. #>
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$PrefixArguments = @()
    )
    if (-not (Get-Command -Name $Command -ErrorAction SilentlyContinue)) {
        return $null
    }
    # Native stderr must not become a terminating error while probing.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $Command @PrefixArguments -c $VersionProbe 2>$null
        if ($LASTEXITCODE -eq 0 -and $output) {
            return [version](@($output)[0].ToString().Trim())
        }
    }
    catch {
        Write-Verbose "Probe of '$Command $PrefixArguments' failed: $($_.Exception.Message)"
    }
    finally {
        $ErrorActionPreference = $previousPreference
    }
    return $null
}

function Test-RequiredVersion {
    <# True when the version is on the required major.minor line. #>
    param([version]$Version)
    return ($null -ne $Version) -and ($Version.Major -eq $RequiredVersion.Major) -and ($Version.Minor -eq $RequiredVersion.Minor)
}

function Find-RequiredPython {
    <# Returns @{ Command; PrefixArguments; Version } for the first Python 3.15 found, or $null. #>
    $candidates = @(
        @{ Command = 'py'; PrefixArguments = @('-3.15') },
        @{ Command = 'py'; PrefixArguments = @('-V:3.15') },
        @{ Command = 'python'; PrefixArguments = @() },
        @{ Command = 'python3'; PrefixArguments = @() }
    )
    foreach ($candidate in $candidates) {
        $version = Get-PythonVersion -Command $candidate.Command -PrefixArguments $candidate.PrefixArguments
        if (Test-RequiredVersion -Version $version) {
            return @{ Command = $candidate.Command; PrefixArguments = $candidate.PrefixArguments; Version = $version }
        }
    }
    return $null
}

function Invoke-Native {
    <# Runs a native command and throws if it exits non-zero. #>
    param(
        [Parameter(Mandatory)][string]$Command,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory)][string]$Description
    )
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE."
    }
}
#endregion FUNCTIONS

#region MAIN
try {
    if (-not (Test-Path -LiteralPath $ProjectFile)) {
        throw "pyproject.toml was not found in '$RepoRoot'. Run this script from a Battle Dice checkout."
    }

    #region Virtual environment
    if ($Reinstall -and (Test-Path -LiteralPath $VenvDir)) {
        Write-Status 'Removing the existing .venv (Reinstall requested).'
        Remove-Item -LiteralPath $VenvDir -Recurse -Force
    }

    $venvVersion = $null
    if (Test-Path -LiteralPath $VenvPython) {
        $venvVersion = Get-PythonVersion -Command $VenvPython
    }

    if (-not (Test-RequiredVersion -Version $venvVersion)) {
        $python = Find-RequiredPython
        if ($null -eq $python) {
            throw ("Python $RequiredVersion was not found. Install it from $DownloadPage " +
                "(with the Python install manager you can run: py install $RequiredVersion), " +
                'then run this launcher again.')
        }
        if (Test-Path -LiteralPath $VenvDir) {
            Write-Status "The existing .venv is not Python $RequiredVersion; rebuilding it."
            Remove-Item -LiteralPath $VenvDir -Recurse -Force
        }
        Write-Status "Creating .venv with Python $($python.Version)."
        $venvArguments = @($python.PrefixArguments) + @('-m', 'venv', $VenvDir)
        Invoke-Native -Command $python.Command -Arguments $venvArguments -Description 'Creating the virtual environment'
    }
    else {
        Write-Status "Using the existing .venv (Python $venvVersion)."
    }
    #endregion Virtual environment

    #region Install
    $projectHash = (Get-FileHash -LiteralPath $ProjectFile -Algorithm SHA256).Hash
    $installedHash = $null
    if (Test-Path -LiteralPath $StampFile) {
        $installedHash = (Get-Content -LiteralPath $StampFile -TotalCount 1).Trim()
    }

    if ($installedHash -ne $projectHash) {
        Write-Status 'Installing Battle Dice and its dependencies (first run, or pyproject.toml changed).'
        $installArguments = @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', $RepoRoot)
        Invoke-Native -Command $VenvPython -Arguments $installArguments -Description 'Installing Battle Dice'
        Set-Content -LiteralPath $StampFile -Value $projectHash -Encoding ASCII
    }
    else {
        Write-Status 'Battle Dice is already installed and up to date.'
    }
    #endregion Install

    #region Launch
    if ($NoLaunch) {
        Write-Status 'Set-up complete. NoLaunch was given, so the game was not started.'
        exit 0
    }

    $gameArguments = @('-m', 'battle_dice', '--size', $Size)
    if ($Seed) {
        $gameArguments += @('--seed', $Seed)
    }
    if ($LogDir) {
        $gameArguments += @('--log-dir', $LogDir)
    }
    Write-Status 'Starting the game.'
    Push-Location -LiteralPath $RepoRoot
    try {
        & $VenvPython @gameArguments
        $gameExitCode = $LASTEXITCODE
    }
    finally {
        Pop-Location
    }
    exit $gameExitCode
    #endregion Launch
}
catch {
    Write-Error -Message "[Battle Dice] $($_.Exception.Message)" -ErrorAction Continue
    exit 1
}
#endregion MAIN
