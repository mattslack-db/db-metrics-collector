if (-not (Get-Variable -Name DbTokenCache -Scope Script -ErrorAction SilentlyContinue)) {
    Set-Variable -Name DbTokenCache -Value @{} -Scope Script
}

function Invoke-AzToken {
    param([string]$Subscription, [string]$Tenant)
    $azArgs = @('account','get-access-token','--subscription',$Subscription,
                '--resource','https://management.azure.com','--output','json')
    if ($Tenant) { $azArgs += @('--tenant', $Tenant) }
    $out = & az @azArgs 2>&1
    if ($LASTEXITCODE -ne 0) { throw "az token failed: $out" }
    ($out -join "`n")
}

function Get-DbToken {
    [OutputType([string])] param([Parameter(Mandatory)][string]$Subscription, [string]$Tenant)
    $key = "$Subscription|$Tenant"
    if (-not $script:DbTokenCache.ContainsKey($key)) {
        $json = Invoke-AzToken -Subscription $Subscription -Tenant $Tenant | ConvertFrom-Json
        $script:DbTokenCache[$key] = $json.accessToken
    }
    $script:DbTokenCache[$key]
}
