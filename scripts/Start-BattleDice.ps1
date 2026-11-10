<#
.SYNOPSIS
    Sets up and starts Battle Dice from source on Windows.

.DESCRIPTION
    Idempotent launcher. Each run it:
      1. Finds a Python 3.15 or newer interpreter (3.15 is preferred): the py launcher, python
         on PATH, the standard install folders, then the registry. Use -Python to point at one.
      2. Creates the .venv virtual environment if it is missing or built on an older Python.
      3. Installs the game into .venv when pyproject.toml changed, when the checkout was moved,
         or when the game cannot be imported from .venv.
      4. Starts the game.

    The launcher does not download or install Python and never changes machine-wide settings.
    Everything it creates lives in the .venv folder inside the repository. An existing .venv is
    only removed after a usable Python has been found to rebuild it with.

.PARAMETER Python
    Full path to a python.exe (3.15 or newer) to use. Only needed when the launcher cannot find
    one by itself, for example when an older Python comes first on PATH.

.PARAMETER Seed
    Root seed for every run, so dice and enemy choices repeat exactly. Unsigned integer.

.PARAMETER Size
    Window size as WIDTHxHEIGHT. Minimum supported is 960x540.

.PARAMETER LogDir
    Folder for JSONL event logs. Defaults to the logs folder in the repository.

.PARAMETER Reinstall
    Build .venv again from scratch. The old .venv is kept if no usable Python is found.

.PARAMETER NoLaunch
    Set everything up, then exit without starting the game.

.PARAMETER SmokeTest
    Set everything up, then run the game's hidden self-check instead of opening a window: one
    full seeded run, exit code 0 on success. Uses the same start-up path as a normal launch.

.EXAMPLE
    .\scripts\Start-BattleDice.ps1

.EXAMPLE
    .\scripts\Start-BattleDice.ps1 -Seed 123 -Size 960x540

.EXAMPLE
    .\scripts\Start-BattleDice.ps1 -Python "$env:LOCALAPPDATA\Programs\Python\Python315\python.exe"

.EXAMPLE
    .\scripts\Start-BattleDice.ps1 -SmokeTest

.NOTES
    Works in Windows PowerShell 5.1 and PowerShell 7+.
#>
[CmdletBinding()]
param(
    [string]$Python,

    [ValidatePattern('^\d{1,20}$')]
    [string]$Seed,

    [ValidatePattern('^\d{3,5}x\d{3,5}$')]
    [string]$Size = '1280x720',

    [string]$LogDir,

    [switch]$Reinstall,

    [switch]$NoLaunch,

    [switch]$SmokeTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

#region VARIABLES
$RequiredVersion = [version]'3.15'    # the minimum; pyproject.toml says requires-python >= 3.15
$RepoRoot = Split-Path -Parent $PSScriptRoot
$ProjectFile = Join-Path $RepoRoot 'pyproject.toml'
$VenvDir = Join-Path $RepoRoot '.venv'
$VenvPython = Join-Path $VenvDir 'Scripts\python.exe'
$StampFile = Join-Path $VenvDir '.battle-dice-install-stamp'
$VersionProbe = "import sys; print('%d.%d.%d' % sys.version_info[:3])"
$DownloadPage = 'https://www.python.org/downloads/windows/'
$VersionDotted = "$($RequiredVersion.Major).$($RequiredVersion.Minor)"    # 3.15
$ImportProbe = 'import battle_dice'
# Older Python versions seen while searching; reported if no usable one is found.
$OtherPythons = New-Object System.Collections.Generic.List[string]
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
    # A full path is checked literally: Get-Command treats [ and ] in a path as wildcards.
    if ($Command -match '[\\/]') {
        if (-not (Test-Path -LiteralPath $Command -PathType Leaf)) {
            return $null
        }
    }
    elseif (-not (Get-Command -Name $Command -ErrorAction SilentlyContinue)) {
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
    <# True when the version is the required major and at least the required minor (3.15, 3.16, ...). #>
    param([version]$Version)
    return ($null -ne $Version) -and ($Version.Major -eq $RequiredVersion.Major) -and ($Version.Minor -ge $RequiredVersion.Minor)
}

function Get-MinorFromName {
    <# Minor version from a name such as "Python315", "3.16" or "pythoncore-3.15-64"; -1 if it is not usable. #>
    param([Parameter(Mandatory)][string]$Name)
    # Free-threaded ("3.15t") and 32-bit ("3.15-32") builds are skipped: pygame-ce may have no wheel for them.
    if ($Name -match '(^|[^0-9])3\.?(\d{2})(t|-32)($|[^0-9])') {
        return -1
    }
    if ($Name -match '(^|[^0-9])3\.?(\d{2})($|[^0-9])') {
        return [int]$Matches[2]
    }
    return -1
}

function Get-KnownPythonPath {
    <#
        Returns existing python.exe paths for Python 3.15 or newer: install folders, then the
        registry. The required minor comes first, newer ones after it in ascending order.
    #>
    $found = @()    # each: @{ Minor; Order; Path }

    $parents = @()
    if ($env:LOCALAPPDATA) {
        $parents += Join-Path $env:LOCALAPPDATA 'Programs\Python'    # python.org installer, per user
        $parents += Join-Path $env:LOCALAPPDATA 'Python'             # Python install manager
    }
    if ($env:ProgramFiles) {
        $parents += $env:ProgramFiles                                # python.org installer, all users
    }
    foreach ($parent in $parents) {
        if (-not (Test-Path -LiteralPath $parent)) {
            continue
        }
        foreach ($folder in @(Get-ChildItem -LiteralPath $parent -Directory -ErrorAction SilentlyContinue)) {
            if ($folder.Name -notmatch '^(Python3\d{2}|pythoncore-3\.\d{2}.*)$') {
                continue
            }
            $minor = Get-MinorFromName -Name $folder.Name
            $executable = Join-Path $folder.FullName 'python.exe'
            if ($minor -ge $RequiredVersion.Minor -and (Test-Path -LiteralPath $executable)) {
                $found += @{ Minor = $minor; Order = $found.Count; Path = $executable }
            }
        }
    }
    if ($env:LOCALAPPDATA) {
        # Aliases for the required version only (the Python install manager and the Store package).
        foreach ($alias in @("Python\bin\python$VersionDotted.exe", "Microsoft\WindowsApps\python$VersionDotted.exe")) {
            $executable = Join-Path $env:LOCALAPPDATA $alias
            if (Test-Path -LiteralPath $executable) {
                $found += @{ Minor = $RequiredVersion.Minor; Order = $found.Count; Path = $executable }
            }
        }
    }

    # PEP 514 registration: HK*\Software\Python\<Company>\<Tag>\InstallPath, as the py launcher reads it.
    foreach ($root in @('HKCU:\Software\Python', 'HKLM:\SOFTWARE\Python', 'HKLM:\SOFTWARE\WOW6432Node\Python')) {
        if (-not (Test-Path -Path $root)) {
            continue
        }
        foreach ($company in @(Get-ChildItem -Path $root -ErrorAction SilentlyContinue)) {
            foreach ($tag in @(Get-ChildItem -Path $company.PSPath -ErrorAction SilentlyContinue)) {
                $minor = Get-MinorFromName -Name $tag.PSChildName
                if ($minor -lt $RequiredVersion.Minor) {
                    continue
                }
                $installKeyPath = Join-Path $tag.PSPath 'InstallPath'
                if (-not (Test-Path -Path $installKeyPath)) {
                    continue
                }
                $installKey = Get-Item -Path $installKeyPath -ErrorAction SilentlyContinue
                if ($null -eq $installKey) {
                    continue
                }
                $executable = $installKey.GetValue('ExecutablePath')
                if (-not $executable) {
                    $installFolder = $installKey.GetValue('')
                    if ($installFolder) {
                        $executable = Join-Path $installFolder 'python.exe'
                    }
                }
                if ($executable -and (Test-Path -LiteralPath $executable)) {
                    $found += @{ Minor = $minor; Order = $found.Count; Path = $executable }
                }
            }
        }
    }
    # Sorted by minor version, then by the order found (Sort-Object -Stable needs PowerShell 6+).
    $ordered = @($found | Sort-Object -Property @{ Expression = { $_.Minor } }, @{ Expression = { $_.Order } })
    return @($ordered | ForEach-Object { $_.Path } | Select-Object -Unique)
}

function Find-RequiredPython {
    <#
        Returns @{ Command; PrefixArguments; Version } for the first Python 3.15 or newer, or $null.
        Python 3.15 itself is tried first. Older versions met on the way are recorded in
        $OtherPythons for the error message.
    #>
    param([string]$ExplicitPath)

    $candidates = @()
    if ($ExplicitPath) {
        $candidates += @{ Command = $ExplicitPath; PrefixArguments = @(); Label = "-Python '$ExplicitPath'" }
    }
    else {
        $candidates += @{ Command = 'py'; PrefixArguments = @("-$VersionDotted"); Label = "py -$VersionDotted" }
        $candidates += @{ Command = 'py'; PrefixArguments = @("-V:$VersionDotted"); Label = "py -V:$VersionDotted" }
        foreach ($name in @("python$VersionDotted", 'python', 'python3')) {
            $candidates += @{ Command = $name; PrefixArguments = @(); Label = "'$name' on PATH" }
        }
        # The newest Python 3 the py launcher knows: accepted when it is newer than 3.15.
        $candidates += @{ Command = 'py'; PrefixArguments = @('-3'); Label = 'py -3' }
        foreach ($path in @(Get-KnownPythonPath)) {
            $candidates += @{ Command = $path; PrefixArguments = @(); Label = $path }
        }
    }

    foreach ($candidate in $candidates) {
        if ($candidate.Command -notmatch '[\\/]') {
            # With .venv activated, "python" on PATH is the .venv itself, which cannot rebuild itself.
            $resolved = Get-Command -Name $candidate.Command -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($resolved -and $resolved.Source -and
                $resolved.Source.StartsWith($VenvDir, [System.StringComparison]::OrdinalIgnoreCase)) {
                continue
            }
        }
        $version = Get-PythonVersion -Command $candidate.Command -PrefixArguments $candidate.PrefixArguments
        if ($null -eq $version) {
            continue
        }
        if (Test-RequiredVersion -Version $version) {
            Write-Verbose "Using $($candidate.Label) (Python $version)."
            return @{ Command = $candidate.Command; PrefixArguments = $candidate.PrefixArguments; Version = $version }
        }
        $note = "$($candidate.Label) is Python $version"
        if (-not $OtherPythons.Contains($note)) {
            $OtherPythons.Add($note)
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
    $venvVersion = $null
    if (Test-Path -LiteralPath $VenvPython) {
        $venvVersion = Get-PythonVersion -Command $VenvPython
    }
    $venvUsable = Test-RequiredVersion -Version $venvVersion

    if ($Reinstall -or -not $venvUsable) {
        # Find the interpreter first. The existing .venv is only removed once there is
        # something to rebuild it with, so a failed search never leaves the player without one.
        $interpreter = Find-RequiredPython -ExplicitPath $Python
        if ($null -eq $interpreter) {
            $kept = ''
            if ($venvUsable) {
                $kept = ' The existing .venv was kept and still works; run the launcher without -Reinstall to use it.'
            }
            if ($Python) {
                $detail = 'It does not exist or does not run.'
                if ($OtherPythons.Count -gt 0) {
                    $detail = 'Found there: ' + ($OtherPythons -join '; ') + '.'
                }
                throw "The -Python path is not a working Python $RequiredVersion or newer. $detail$kept"
            }
            $found = 'No other Python was found either.'
            if ($OtherPythons.Count -gt 0) {
                $found = 'Found instead: ' + ($OtherPythons -join '; ') + '.'
            }
            throw ("Python $RequiredVersion or newer was not found. Looked at the py launcher, python on PATH, " +
                "the standard install folders and the registry. $found " +
                "If it is installed, pass its python.exe with -Python " +
                "(run 'py --list' or 'where.exe python' to locate it). " +
                "Otherwise install Python $RequiredVersion from $DownloadPage and run this launcher again.$kept")
        }
        if (Test-Path -LiteralPath $VenvDir) {
            if ($Reinstall) {
                Write-Status 'Removing the existing .venv (Reinstall requested).'
            }
            else {
                Write-Status "The existing .venv is not Python $RequiredVersion or newer; rebuilding it."
            }
            Remove-Item -LiteralPath $VenvDir -Recurse -Force
        }
        Write-Status "Creating .venv with Python $($interpreter.Version)."
        $venvArguments = @($interpreter.PrefixArguments) + @('-m', 'venv', $VenvDir)
        Invoke-Native -Command $interpreter.Command -Arguments $venvArguments -Description 'Creating the virtual environment'
    }
    else {
        Write-Status "Using the existing .venv (Python $venvVersion)."
        if ($Python) {
            Write-Status '-Python was given, but the existing .venv already works and was kept. Add -Reinstall to rebuild .venv from that interpreter.'
        }
    }
    #endregion Virtual environment

    #region Install
    # The stamp records what was installed and from where. An editable install stores the
    # absolute path of the checkout, so a moved or renamed checkout needs a new install.
    $projectHash = (Get-FileHash -LiteralPath $ProjectFile -Algorithm SHA256).Hash
    $stamp = "$projectHash|$RepoRoot"
    $installedStamp = $null
    if (Test-Path -LiteralPath $StampFile) {
        $installedStamp = (Get-Content -LiteralPath $StampFile -TotalCount 1).Trim()
    }

    $installReason = $null
    if ($null -eq $installedStamp) {
        $installReason = 'first run'
    }
    elseif ($installedStamp -ne $stamp) {
        if ($installedStamp -notmatch '\|') {
            $installReason = 'the install record was written by an older launcher'
        }
        elseif ($installedStamp.Split('|')[0] -ne $projectHash) {
            $installReason = 'pyproject.toml changed'
        }
        else {
            $installReason = 'the checkout was moved or renamed'
        }
    }
    else {
        # Last check: the game must actually import from this .venv.
        $previousPreference = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            & $VenvPython -c $ImportProbe 2>$null
            if ($LASTEXITCODE -ne 0) {
                $installReason = 'the game could not be imported from .venv'
            }
        }
        finally {
            $ErrorActionPreference = $previousPreference
        }
    }

    if ($installReason) {
        Write-Status "Installing Battle Dice and its dependencies ($installReason)."
        $installArguments = @('-m', 'pip', 'install', '--disable-pip-version-check', '-e', $RepoRoot)
        Invoke-Native -Command $VenvPython -Arguments $installArguments -Description 'Installing Battle Dice'
        Set-Content -LiteralPath $StampFile -Value $stamp -Encoding UTF8
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

    if ($SmokeTest) {
        $gameArguments = @('-m', 'battle_dice', '--smoke-test')
        Write-Status 'Running the hidden self-check (no window opens).'
    }
    else {
        $gameArguments = @('-m', 'battle_dice', '--size', $Size)
        if ($Seed) {
            $gameArguments += @('--seed', $Seed)
        }
        if ($LogDir) {
            $gameArguments += @('--log-dir', $LogDir)
        }
        Write-Status 'Starting the game.'
    }
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
    # One plain line on stderr. Write-Error would wrap the message in a PowerShell error record
    # (script path, "At line", CategoryInfo), which buries the part the player needs to read.
    [Console]::Error.WriteLine("[Battle Dice] $($_.Exception.Message)")
    exit 1
}
#endregion MAIN
