# uia_read.ps1 - read a window's text via Windows UI Automation (built-in).
param([string]$Title = "")

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes

$AE = [System.Windows.Automation.AutomationElement]
$cond = [System.Windows.Automation.Condition]::TrueCondition
$target = $null

if ($Title) {
    $wins = $AE::RootElement.FindAll([System.Windows.Automation.TreeScope]::Children, $cond)
    foreach ($w in $wins) {
        try { if ($w.Current.Name -like "*$Title*") { $target = $w; break } } catch {}
    }
    if (-not $target) { Write-Output "[uia:window-not-found] $Title"; exit 1 }
} else {
    Add-Type @"
using System;using System.Runtime.InteropServices;
public class FG2 { [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow(); }
"@
    $h = [FG2]::GetForegroundWindow()
    if ($h -eq [IntPtr]::Zero) { Write-Output "[uia:no-foreground]"; exit 1 }
    $target = $AE::FromHandle($h)
}

$texts = New-Object System.Collections.Generic.List[string]
$all = $target.FindAll([System.Windows.Automation.TreeScope]::Descendants, $cond)
foreach ($el in $all) {
    try {
        $name = $el.Current.Name
        if ($name) { [void]$texts.Add($name) }
        $vp = $null
        if ($el.TryGetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern, [ref]$vp)) {
            $val = $vp.Current.Value
            if ($val -and $val.Length -lt 1500) { [void]$texts.Add($val) }
        }
        $tp = $null
        if ($el.TryGetCurrentPattern([System.Windows.Automation.TextPattern]::Pattern, [ref]$tp)) {
            $doc = $tp.DocumentRange.GetText(1200)
            if ($doc) { [void]$texts.Add($doc) }
        }
    } catch { continue }
    if ($texts.Count -ge 260) { break }
}

if ($texts.Count -eq 0) { Write-Output "[uia:no-text]"; exit 0 }

$seen = New-Object System.Collections.Generic.HashSet[string]
$out = New-Object System.Collections.Generic.List[string]
foreach ($t in $texts) {
    $tt = $t.Trim()
    if ($tt -and $seen.Add($tt)) { [void]$out.Add($tt) }
    if ($out.Count -ge 120) { break }
}
Write-Output ($out -join "`n")
