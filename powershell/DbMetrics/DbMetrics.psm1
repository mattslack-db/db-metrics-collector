# Dot-source every function file beside this module, then export public functions.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
Get-ChildItem -Path $here -Filter '*.ps1' -File |
    Where-Object { $_.Name -ne 'DbMetrics.psm1' } |
    ForEach-Object { . $_.FullName }

# Export all functions defined by the dot-sourced files.
Export-ModuleMember -Function *
