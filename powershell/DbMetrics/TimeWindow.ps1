Set-Variable -Name DbDefaultInterval -Value 'PT1M' -Scope Script -Option Constant -ErrorAction SilentlyContinue

function ConvertFrom-Iso8601Duration {
    [OutputType([timespan])] param([Parameter(Mandatory)][string]$Text)
    $rx = '^P(?:(?<d>\d+)D)?(?:T(?:(?<h>\d+)H)?(?:(?<m>\d+)M)?(?:(?<s>\d+)S)?)?$'
    $t = $Text.Trim()
    $mch = [regex]::Match($t, $rx)
    if (-not $mch.Success) { throw "Invalid ISO-8601 duration: '$Text'" }
    $d = [int]($mch.Groups['d'].Value -as [int]); $h = [int]($mch.Groups['h'].Value -as [int])
    $m = [int]($mch.Groups['m'].Value -as [int]); $s = [int]($mch.Groups['s'].Value -as [int])
    $span = New-TimeSpan -Days $d -Hours $h -Minutes $m -Seconds $s
    if ($span -le [timespan]::Zero) { throw "Duration must be non-zero: '$Text'" }
    $span
}

function Get-MetricWindow {
    param([Parameter(Mandatory)][double]$Hours, [datetime]$Now = [datetime]::UtcNow)
    if ($Hours -le 0) { throw "hours must be positive, got $Hours" }
    $end = $Now.ToUniversalTime()
    [ordered]@{ Start = $end.AddHours(-$Hours); End = $end }
}
