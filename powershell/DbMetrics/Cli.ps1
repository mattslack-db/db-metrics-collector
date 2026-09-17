# Cli.ps1 — argument parsing, target building, and the main run loop.
# Port of db_metrics/cli_core.py (run, targets_from_args, _validate_windows,
# _collect_target) and db_metrics/cli_azure.py (single-target param shape).
# Azure-only (no --engine legacy mapping, no AWS cloud).

Set-Variable -Name CliExitOk    -Value 0 -Scope Script -Option Constant -ErrorAction SilentlyContinue
Set-Variable -Name CliExitError -Value 1 -Scope Script -Option Constant -ErrorAction SilentlyContinue
Set-Variable -Name CliExitUsage -Value 2 -Scope Script -Option Constant -ErrorAction SilentlyContinue

# Flags that make up a "single-target" specification (mutually exclusive with -Config).
# These map from PascalCase CLI param names to the snake_case param keys stored
# inside target.params.
$script:SingleTargetParamMap = [ordered]@{
    Subscription  = 'subscription'
    ResourceGroup = 'resource_group'
    ServerName    = 'server_name'
    Database      = 'database'
    SubEngine     = 'sub_engine'
    ClusterName   = 'cluster_name'
    InstanceName  = 'instance_name'
}

# Flags that are mutually exclusive with -Config (includes Service).
$script:ConfigMutexFlags = @('Service') + @($script:SingleTargetParamMap.Keys)

# ---------------------------------------------------------------------------
# Get-TargetsFromArgs — pure target-list builder (port of targets_from_args).
# ---------------------------------------------------------------------------

function Get-TargetsFromArgs {
    <#
    .SYNOPSIS
        Build the target list from the caller's bound parameters.

    .DESCRIPTION
        Port of cli_core.targets_from_args (azure branch, no engine_map).
        - If -Config is present: load via Import-TargetConfig; throw if any
          single-target flag is ALSO present (mutually exclusive).
        - Otherwise: require -Service (throw if absent); build one target
          from -Service + identifier params + -Hours / -Interval; derive
          name = server_name ?? instance_name ?? cluster_name ?? database ?? service.

        ARRAY SAFETY: uses the comma trick (,$arr) to return the array as a
        single item so the pipeline never unrolls it — matches Import-TargetConfig.

    .PARAMETER BoundParams
        The $PSBoundParameters hashtable from the entry script (PascalCase keys).

    .OUTPUTS
        [array] of target hashtables.

    .THROWS
        System.Exception on invalid flag combinations or missing -Service.
    #>
    [OutputType([array])]
    param([Parameter(Mandatory)][hashtable]$BoundParams)

    if ($BoundParams.ContainsKey('Config') -and $null -ne $BoundParams['Config']) {

        # Check mutual exclusivity with single-target flags.
        $conflicting = @($script:ConfigMutexFlags | Where-Object { $BoundParams.ContainsKey($_) })
        if ($conflicting.Count -gt 0) {
            $flagList = ($conflicting | ForEach-Object { "-$_" }) -join ', '
            throw "-Config is mutually exclusive with single-target flags: $flagList"
        }

        # Return directly: callers must wrap with @() to collect into an array.
        $loaded = Import-TargetConfig -Path $BoundParams['Config']
        return $loaded
    }

    # Single-target path: -Service is required.
    if (-not $BoundParams.ContainsKey('Service') -or $null -eq $BoundParams['Service']) {
        throw "-Service is required when -Config is not specified."
    }

    $service  = $BoundParams['Service']
    $hours    = if ($BoundParams.ContainsKey('Hours') -and $null -ne $BoundParams['Hours']) {
                    [double]$BoundParams['Hours']
                } else { 1.0 }
    $interval = if ($BoundParams.ContainsKey('Interval') -and $null -ne $BoundParams['Interval']) {
                    $BoundParams['Interval']
                } else { 'PT1M' }

    # Build snake_case params from PascalCase BoundParams.
    $params = @{}
    foreach ($pascalKey in $script:SingleTargetParamMap.Keys) {
        if ($BoundParams.ContainsKey($pascalKey) -and $null -ne $BoundParams[$pascalKey]) {
            $snakeKey = $script:SingleTargetParamMap[$pascalKey]
            $params[$snakeKey] = $BoundParams[$pascalKey]
        }
    }

    # Derive name: server_name ?? instance_name ?? cluster_name ?? database ?? service.
    $name = $params['server_name'] ??
            $params['instance_name'] ??
            $params['cluster_name'] ??
            $params['database'] ??
            $service

    $target = [ordered]@{
        name     = $name
        cloud    = 'azure'
        service  = $service
        hours    = $hours
        interval = $interval
        params   = $params
    }

    # Emit the single target. Callers wrap with @() to collect into an array,
    # matching the task-brief guidance: "Use DIRECT @($x) for any collection."
    $target
}

# ---------------------------------------------------------------------------
# Invoke-InventoryForTarget — internal inventory dispatch (by service).
# ---------------------------------------------------------------------------

function Invoke-InventoryForTarget {
    <#
    .SYNOPSIS
        Dispatch to the right Get-*Inventory function for the target's service,
        then override resource_id with the ARM resource ID built by
        Get-AzureResourceId (mirrors the Python adapter's collect + resource_id
        override pattern).

    .PARAMETER Target
        Target ordered-dict (keys: name, cloud, service, params, ...).

    .PARAMETER Token
        Azure bearer token.

    .OUTPUTS
        [ordered] inventory hashtable with resource_id set to the ARM resource id.
    #>
    param(
        [Parameter(Mandatory)]$Target,
        [Parameter(Mandatory)][string]$Token
    )

    $service      = $Target['service']
    $params       = $Target['params']
    $subscription = $params['subscription']

    $resourceId = Get-AzureResourceId -Service $service -SubscriptionId $subscription -Params $params

    $inventory = switch ($service) {
        'postgres-flexible'    {
            Get-FlexibleInventory -ResourceId $resourceId -SubEngineNamespace 'Microsoft.DBforPostgreSQL' -Token $Token
        }
        'mysql-flexible'       {
            Get-FlexibleInventory -ResourceId $resourceId -SubEngineNamespace 'Microsoft.DBforMySQL' -Token $Token
        }
        'cosmos-postgres'      { Get-CosmosPostgresInventory    -ResourceId $resourceId -Token $Token }
        'sql-database'         { Get-SqlDatabaseInventory        -ResourceId $resourceId -Token $Token }
        'sql-managed-instance' { Get-SqlManagedInstanceInventory -ResourceId $resourceId -Token $Token }
        'single-server'        { Get-SingleServerInventory       -ResourceId $resourceId -Token $Token }
        default                { throw "Invoke-InventoryForTarget: unknown service '$service'" }
    }

    # Build a shallow clone with resource_id overridden — never mutate the object
    # returned by the inventory function (immutability rule; also prevents test bleed
    # when a mock returns a shared reference).
    $result = [ordered]@{}
    foreach ($k in $inventory.Keys) { $result[$k] = $inventory[$k] }
    $result['resource_id'] = $resourceId
    $result
}

# ---------------------------------------------------------------------------
# Invoke-Run — the main run loop (port of cli_core.run).
# ---------------------------------------------------------------------------

function Invoke-Run {
    <#
    .SYNOPSIS
        Parse targets, validate, collect metrics, write reports.

    .DESCRIPTION
        Port of cli_core.run (azure variant: cloud='azure', no engine_map).

        Exit codes:
          0 — all targets succeeded
          1 — at least one target failed (non-fatal per-target error)
          2 — usage / validation error (bad flags, bad interval, etc.)

    .PARAMETER BoundParams
        The $PSBoundParameters hashtable from the entry script.

    .OUTPUTS
        [int] exit code.
    #>
    [OutputType([int])]
    param([Parameter(Mandatory)][hashtable]$BoundParams)

    # --- 1. Build target list ------------------------------------------------
    # @() wrapper ensures we always get an [array], even when Get-TargetsFromArgs
    # emits a single target (PowerShell's pipeline enumerates single items).
    try {
        $targets = @(Get-TargetsFromArgs -BoundParams $BoundParams)
    } catch {
        Write-Host "Error: $_" -ForegroundColor Red
        return $script:CliExitUsage
    }

    # --- 2. Validate windows for every target (mirrors _validate_windows) -----
    # NOTE: targets are [ordered]@{} (OrderedDictionary); use '-in $t.Keys'
    # rather than '.ContainsKey()' — OrderedDictionary has .Contains(), not
    # .ContainsKey(), and the -in operator works for both types.
    foreach ($target in $targets) {
        $interval = if ('interval' -in $target.Keys -and $null -ne $target['interval']) {
                        $target['interval']
                    } else { 'PT1M' }
        try {
            $null = ConvertFrom-Iso8601Duration -Text $interval
        } catch {
            Write-Host "Error: Target '$($target['name'])': $_" -ForegroundColor Red
            return $script:CliExitUsage
        }
        $hours = if ('hours' -in $target.Keys -and $null -ne $target['hours']) {
                     [double]$target['hours']
                 } else { 1.0 }
        if ($hours -le 0) {
            Write-Host "Error: Target '$($target['name'])': hours must be positive, got $hours" -ForegroundColor Red
            return $script:CliExitUsage
        }
    }

    # --- 3. Per-target collection --------------------------------------------
    $single   = $targets.Count -eq 1
    $results  = @()
    $hadError = $false

    $tenant = if ($BoundParams.ContainsKey('Tenant') -and $null -ne $BoundParams['Tenant']) {
                  $BoundParams['Tenant']
              } else { '' }

    foreach ($target in $targets) {
        try {
            # Validate service + required params.
            Resolve-Provider -Target $target

            # Acquire token (cached per subscription+tenant).
            $subscription = $target['params']['subscription']
            $token = Get-DbToken -Subscription $subscription -Tenant $tenant

            # Collect inventory via service dispatch.
            $inventory  = Invoke-InventoryForTarget -Target $target -Token $token
            $resourceId = $inventory['resource_id']

            # Discover metric definitions. Assign directly: Get-MetricDefinition
            # comma-returns, so this is already an array (even for 0/1 items).
            # Do NOT wrap in @() — that double-wraps the comma-return into a
            # single-element array holding the whole list, which would make
            # Get-MetricSeries send every metric name in one request → HTTP 400.
            $defs = Get-MetricDefinition -ResourceId $resourceId -Token $token

            # Build time window.
            $hours    = if ('hours' -in $target.Keys -and $null -ne $target['hours']) {
                            [double]$target['hours']
                        } else { 1.0 }
            $window   = Get-MetricWindow -Hours $hours

            # Resolve grain.
            $interval = if ('interval' -in $target.Keys -and $null -ne $target['interval']) {
                            $target['interval']
                        } else { 'PT1M' }
            $grain    = ConvertFrom-Iso8601Duration -Text $interval

            # Query metrics. Assign directly (Get-MetricSeries comma-returns);
            # wrapping in @() would double-wrap as above.
            $metrics = Get-MetricSeries -ResourceId $resourceId -Definitions $defs `
                            -Start $window.Start -End $window.End `
                            -Granularity $grain -Token $token

            # Assemble per-target report.
            $rep = Build-Report -Target $target -ResourceScope $resourceId `
                      -Inventory $inventory -Definitions $defs `
                      -Metrics $metrics -Window $window -Interval $interval

            # Determine output path.
            $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss')
            $path  = if ($single -and $BoundParams.ContainsKey('Out') -and $null -ne $BoundParams['Out']) {
                         $BoundParams['Out']
                     } else {
                         "metrics_$($target['name'])_${stamp}.json"
                     }
            Write-ReportJson -Report $rep -Path $path
            Write-Host "Report written to: $path" -ForegroundColor Cyan

            $results += $rep

            if (-not ($BoundParams.ContainsKey('NoConsole') -and $BoundParams['NoConsole'])) {
                Format-ConsoleSummary -Report $rep | Write-Host
            }

        } catch {
            # Per-target failure is non-fatal: record and continue.
            $hadError = $true
            $errMsg = $_.Exception.Message
            $results += [ordered]@{
                name    = $target['name']
                cloud   = $target['cloud']
                service = $target['service']
                error   = $errMsg
            }
            Write-Host "Target '$($target['name'])' failed: $errMsg" -ForegroundColor Red
        }
    }

    # --- 4. Multi-target summary (only when >1 target) -----------------------
    if ($targets.Count -gt 1) {
        $summary = Build-Summary -Reports $results
        $stamp = (Get-Date).ToUniversalTime().ToString('yyyyMMdd_HHmmss')
        $summaryPath = "summary_${stamp}.json"
        Write-ReportJson -Report $summary -Path $summaryPath
        Write-Host "Summary written to: $summaryPath" -ForegroundColor Cyan

        if (-not ($BoundParams.ContainsKey('NoConsole') -and $BoundParams['NoConsole'])) {
            Format-SummaryTable -Summary $summary | Write-Host
        }
    }

    return $(if ($hadError) { $script:CliExitError } else { $script:CliExitOk })
}
