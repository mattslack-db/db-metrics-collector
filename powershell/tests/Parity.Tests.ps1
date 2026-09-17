# Parity.Tests.ps1 — schema+value parity test + coverage-gap tests (Task 11)
#
# THREE sections:
#  1. $script:AssertDeepEq — recursive deep-compare helper (structural, not byte).
#     Defined in BeforeAll as a $script: scriptblock so it is accessible from
#     It blocks (Pester 5 scoping: It blocks do NOT inherit top-level functions).
#  2. "Schema+value parity" — feeds mirrored ARM/Monitor fixtures through the REAL
#     module functions (Get-FlexibleInventory, Get-MetricDefinition, Get-MetricSeries,
#     Build-Report) and asserts the result matches canonical_report.json in structure,
#     key sets, types, and values (numbers within 1e-9; collected_at key asserted
#     present but its volatile value excluded from value-compare).
#  3. Carry-forward coverage tests:
#     - Auth.ps1:         Invoke-AzToken error path (non-zero $LASTEXITCODE → throw).
#     - AzureMonitor.ps1: Get-MetricDefinition single-def → must return array of length 1.

# ── Module import + shared fixtures + helper scriptblocks ─────────────────────

BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force

    # ── Static test coordinates ───────────────────────────────────────────────
    $script:ResourceId  = '/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-server'
    $script:Token       = 'test-token'
    $script:WindowStart = [datetime]::new(2026, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc)
    $script:WindowEnd   = [datetime]::new(2026, 1, 1, 1, 0, 0, [System.DateTimeKind]::Utc)
    $script:Interval    = 'PT1M'
    $script:Granularity = [timespan]::FromMinutes(1)

    # ── ARM server fixture ────────────────────────────────────────────────────
    $script:ArmServerResp = [PSCustomObject]@{
        id       = $script:ResourceId
        name     = 'pg-server'
        location = 'eastus'
        sku      = [PSCustomObject]@{ name = 'Standard_D2s_v3'; tier = 'GeneralPurpose' }
        properties = [PSCustomObject]@{
            state                    = 'Ready'
            version                  = '16'
            minorVersion             = '2'
            fullyQualifiedDomainName = 'pg-server.postgres.database.azure.com'
            administratorLogin       = 'adminuser'
            availabilityZone         = '1'
            storage = [PSCustomObject]@{
                storageSizeGB = 32
                tier          = 'P4'
                iops          = 120
                autoGrow      = 'Disabled'
                autoIoScaling = 'Disabled'
                type          = 'Premium_LRS'
            }
            highAvailability = [PSCustomObject]@{
                mode                    = 'Disabled'
                state                   = 'NotEnabled'
                standbyAvailabilityZone = ''
            }
            backup = [PSCustomObject]@{
                backupRetentionDays = 7
                geoRedundantBackup  = 'Disabled'
                earliestRestoreDate = '2026-01-01T00:00:00Z'
            }
            network = [PSCustomObject]@{
                publicNetworkAccess         = 'Enabled'
                delegatedSubnetResourceId   = $null
                privateDnsZoneArmResourceId = $null
            }
            maintenanceWindow = [PSCustomObject]@{
                customWindow = 'Disabled'
                dayOfWeek    = 0
                startHour    = 0
                startMinute  = 0
            }
        }
    }

    # ── ARM configurations fixture ────────────────────────────────────────────
    $script:ArmConfigResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name = 'max_connections'
                properties = [PSCustomObject]@{
                    value           = '50'
                    defaultValue    = '50'
                    source          = 'system-default'
                    isDynamicConfig = $false
                    isReadOnly      = $false
                    unit            = $null
                    description     = 'Max connections'
                }
            }
        )
    }

    # ── ARM databases fixture ─────────────────────────────────────────────────
    $script:ArmDbResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{ name = 'postgres' },
            [PSCustomObject]@{ name = 'azure_sys' }
        )
    }

    # ── ARM metricDefinitions fixture ─────────────────────────────────────────
    $script:ArmDefsResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name                      = [PSCustomObject]@{ value = 'cpu_percent' }
                unit                      = 'Percent'
                supportedAggregationTypes = @('Average', 'Maximum')
                dimensions                = @([PSCustomObject]@{ value = 'DatabaseName' })
                metricAvailabilities      = @(
                    [PSCustomObject]@{ timeGrain = 'PT1M' },
                    [PSCustomObject]@{ timeGrain = 'PT5M' }
                )
            },
            [PSCustomObject]@{
                name                      = [PSCustomObject]@{ value = 'memory_percent' }
                unit                      = 'Percent'
                supportedAggregationTypes = @('Average')
                dimensions                = @()
                metricAvailabilities      = @(
                    [PSCustomObject]@{ timeGrain = 'PT1M' },
                    [PSCustomObject]@{ timeGrain = 'PT5M' }
                )
            }
        )
    }

    # ── ARM cpu_percent metrics fixture ───────────────────────────────────────
    $script:ArmCpuMetricResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name       = [PSCustomObject]@{ value = 'cpu_percent' }
                unit       = 'Percent'
                timeseries = @(
                    [PSCustomObject]@{
                        metadatavalues = @(
                            [PSCustomObject]@{
                                name  = [PSCustomObject]@{ value = 'DatabaseName' }
                                value = 'mydb'
                            }
                        )
                        data = @(
                            [PSCustomObject]@{
                                timeStamp = '2026-01-01T00:00:00Z'
                                average   = 25.5
                                maximum   = 40.0
                                # No 'count' property: after Fix 1 (PSObject.Properties),
                                # count is correctly absent from the built point.
                            }
                        )
                    }
                )
            }
        )
    }

    # ── ARM memory_percent metrics fixture ────────────────────────────────────
    $script:ArmMemMetricResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name       = [PSCustomObject]@{ value = 'memory_percent' }
                unit       = 'Percent'
                timeseries = @(
                    [PSCustomObject]@{
                        metadatavalues = @()
                        data = @(
                            [PSCustomObject]@{
                                timeStamp = '2026-01-01T00:00:00Z'
                                average   = 60.0
                                # No 'count' property: correctly absent after fix.
                            }
                        )
                    }
                )
            }
        )
    }

    # ── Assert-DeepEquivalent: helper scriptblocks ────────────────────────────
    #
    # In Pester 5, It blocks run in an isolated scope and cannot see functions
    # defined at the top level of the test file or inside BeforeAll.  Defining
    # helpers as $script: scriptblocks (called with &) is the idiomatic workaround.
    #
    # Rules:
    #   - Key sets are compared ORDER-INDEPENDENTLY at every dict level.
    #   - Numbers compared as [double] within 1e-9 absolute tolerance.
    #   - Arrays compared element-wise (same length, same order).
    #   - Booleans compared strictly as bool (not coerced to int/string).
    #   - $null on both sides → equal.  One-sided $null → mismatch.
    #   - $ExcludeKeys: keys to skip at every dict level (used to exclude
    #     the volatile 'collected_at' value from comparison while still
    #     asserting the key is PRESENT in a separate It block).

    # Returns individual key strings to the pipeline (no unary-comma wrapping) so that
    #   @(& $script:ObjKeys $Obj | Where-Object { ... })
    # filters individual key strings rather than the whole keys-array as a unit.
    $script:ObjKeys = {
        param($Obj)
        if ($null -eq $Obj) { return }
        if ($Obj -is [System.Collections.IDictionary]) {
            foreach ($k in $Obj.Keys) { $k }
        } elseif ($Obj -is [PSCustomObject]) {
            foreach ($p in $Obj.PSObject.Properties) { $p.Name }
        }
    }

    $script:ObjValue = {
        param($Obj, [string]$Key)
        if ($Obj -is [System.Collections.IDictionary]) { return $Obj[$Key] }
        if ($Obj -is [PSCustomObject]) { return $Obj.$Key }
        throw "Assert-DeepEquivalent: cannot index '$Key' into $($Obj.GetType().Name)"
    }

    # Recursive deep-compare.  Self-references $script:AssertDeepEq for recursion.
    $script:AssertDeepEq = {
        param(
            $Actual,
            $Expected,
            [string[]]$ExcludeKeys = @(),
            [string]$Path = '$'
        )

        # ── Both null → equal ──────────────────────────────────────────────
        if ($null -eq $Actual -and $null -eq $Expected) { return }
        if ($null -eq $Actual) {
            throw "Parity mismatch at ${Path}: actual is null, expected non-null"
        }
        if ($null -eq $Expected) {
            throw "Parity mismatch at ${Path}: expected is null, actual non-null"
        }

        # ── Dict-like (Hashtable, OrderedDictionary, PSCustomObject) ──────────
        $isActDict = ($Actual  -is [System.Collections.IDictionary]) -or ($Actual  -is [PSCustomObject])
        $isExpDict = ($Expected -is [System.Collections.IDictionary]) -or ($Expected -is [PSCustomObject])

        if ($isExpDict -and $isActDict) {
            $expKeys = @(& $script:ObjKeys $Expected | Where-Object { $_ -notin $ExcludeKeys })
            $actKeys = @(& $script:ObjKeys $Actual   | Where-Object { $_ -notin $ExcludeKeys })

            $missing = @($expKeys | Where-Object { $_ -notin $actKeys })
            $extra   = @($actKeys | Where-Object { $_ -notin $expKeys })

            if ($missing.Count -gt 0) {
                throw "Parity mismatch at ${Path}: keys missing in actual: $($missing -join ', ')"
            }
            if ($extra.Count -gt 0) {
                throw "Parity mismatch at ${Path}: extra keys in actual not in expected: $($extra -join ', ')"
            }

            foreach ($key in $expKeys) {
                # Access values directly (not via $script:ObjValue scriptblock) to
                # prevent array values from being unrolled by the PowerShell pipeline.
                $expVal = if ($Expected -is [System.Collections.IDictionary]) { $Expected[$key] } else { $Expected.$key }
                $actVal = if ($Actual   -is [System.Collections.IDictionary]) { $Actual[$key]   } else { $Actual.$key   }
                & $script:AssertDeepEq -Actual $actVal -Expected $expVal -ExcludeKeys $ExcludeKeys -Path "${Path}.${key}"
            }
            return
        }

        # ── Array-like ────────────────────────────────────────────────────────
        $isActArr = ($Actual  -is [array]) -or ($Actual  -is [System.Collections.IList])
        $isExpArr = ($Expected -is [array]) -or ($Expected -is [System.Collections.IList])

        if ($isExpArr -and $isActArr) {
            if ($Actual.Count -ne $Expected.Count) {
                throw "Parity mismatch at ${Path}: array length: expected $($Expected.Count), got $($Actual.Count)"
            }
            for ($i = 0; $i -lt $Expected.Count; $i++) {
                & $script:AssertDeepEq -Actual $Actual[$i] -Expected $Expected[$i] -ExcludeKeys $ExcludeKeys -Path "${Path}[$i]"
            }
            return
        }

        # ── Boolean ───────────────────────────────────────────────────────────
        if ($Expected -is [bool]) {
            if ($Actual -isnot [bool] -or ([bool]$Actual -ne [bool]$Expected)) {
                throw "Parity mismatch at ${Path}: bool: expected $Expected, got $Actual ($($Actual.GetType().Name))"
            }
            return
        }

        # ── Numeric — compared as [double] within 1e-9 ───────────────────────
        $numNames = @('Byte','SByte','Int16','UInt16','Int32','UInt32','Int64','UInt64','Single','Double','Decimal')
        $isExpNum = $numNames -contains $Expected.GetType().Name
        $isActNum = $null -ne $Actual -and ($numNames -contains $Actual.GetType().Name)

        if ($isExpNum -and $isActNum) {
            $diff = [Math]::Abs([double]$Actual - [double]$Expected)
            if ($diff -gt 1e-9) {
                throw "Parity mismatch at ${Path}: numeric: expected $Expected, got $Actual (|diff|=$diff)"
            }
            return
        }

        # ── DateTime handling ─────────────────────────────────────────────────
        # ConvertFrom-Json auto-converts ISO 8601 strings to DateTime objects.
        # The actual report stores dates as strings (from .ToString('o')).
        # Normalise by parsing the string side and comparing UTC DateTimes.
        if ($Expected -is [datetime] -or $Actual -is [datetime]) {
            $expDt = if ($Expected -is [datetime]) {
                         $Expected.ToUniversalTime()
                     } else {
                         [datetime]::Parse([string]$Expected, $null,
                             [System.Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
                     }
            $actDt = if ($Actual -is [datetime]) {
                         $Actual.ToUniversalTime()
                     } else {
                         [datetime]::Parse([string]$Actual, $null,
                             [System.Globalization.DateTimeStyles]::RoundtripKind).ToUniversalTime()
                     }
            if ($expDt -ne $actDt) {
                throw "Parity mismatch at ${Path}: datetime: expected $($expDt.ToString('o')), got $($actDt.ToString('o'))"
            }
            return
        }

        # ── String (fall-through) ─────────────────────────────────────────────
        if ([string]$Actual -ne [string]$Expected) {
            throw "Parity mismatch at ${Path}: string: expected '$Expected', got '$Actual'"
        }
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }

# ─────────────────────────────────────────────────────────────────────────────
# Section 1: Schema+value parity against canonical_report.json
# ─────────────────────────────────────────────────────────────────────────────

Describe 'Schema+value parity against canonical fixture' {

    BeforeAll {
        # Route all Invoke-AzureRest calls to the appropriate canned fixture.
        # Filters are mutually exclusive:
        #   '*metricDefinitions*' path is distinct from '*microsoft.insights/metrics*'
        #   '*databases*' vs '*configurations*' vs server-GET fallback (catch-all)
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:ArmServerResp }

        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:ArmConfigResp }

        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:ArmDbResp }

        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*metricDefinitions*' } `
            { $script:ArmDefsResp }

        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*microsoft.insights/metrics*' -and $Uri -notlike '*cpu_percent*' } `
            { $script:ArmMemMetricResp }

        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*microsoft.insights/metrics*' -and $Uri -like '*cpu_percent*' } `
            { $script:ArmCpuMetricResp }

        # ── Run the real module functions to build the actual report ───────────
        $script:Inventory = Get-FlexibleInventory `
            -ResourceId         $script:ResourceId `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL' `
            -Token              $script:Token

        $script:Definitions = Get-MetricDefinition `
            -ResourceId $script:ResourceId `
            -Token      $script:Token

        $script:MetricSeries = Get-MetricSeries `
            -ResourceId   $script:ResourceId `
            -Definitions  $script:Definitions `
            -Start        $script:WindowStart `
            -End          $script:WindowEnd `
            -Granularity  $script:Granularity `
            -Token        $script:Token

        $target = @{
            name    = 'pg-server'
            cloud   = 'azure'
            service = 'postgres-flexible'
        }
        $window = @{
            Start = $script:WindowStart
            End   = $script:WindowEnd
        }

        $script:ActualReport = Build-Report `
            -Target        $target `
            -ResourceScope $script:ResourceId `
            -Inventory     $script:Inventory `
            -Definitions   $script:Definitions `
            -Metrics       $script:MetricSeries `
            -Window        $window `
            -Interval      $script:Interval

        # Load canonical fixture as ordered hashtable for consistent type matching
        $fixturePath      = Join-Path $PSScriptRoot 'fixtures' 'canonical_report.json'
        $script:Canonical = Get-Content -Raw $fixturePath | ConvertFrom-Json -AsHashtable
    }

    It 'top-level key set equals the canonical 9 keys' {
        $expectedKeys = @('collected_at','name','cloud','service','resource_scope','window','inventory','metric_definitions','metrics')
        $actualKeys   = @($script:ActualReport.Keys)

        $missing = $expectedKeys | Where-Object { $_ -notin $actualKeys }
        $extra   = $actualKeys   | Where-Object { $_ -notin $expectedKeys }

        $missing | Should -BeNullOrEmpty
        $extra   | Should -BeNullOrEmpty
    }

    It 'collected_at key is present and non-empty' {
        $script:ActualReport.Keys | Should -Contain 'collected_at'
        $script:ActualReport['collected_at'] | Should -Not -BeNullOrEmpty
    }

    It 'report structure and values match canonical fixture (collected_at value excluded)' {
        # Call the $script: scriptblock helper directly; if it throws, $mismatch
        # captures the message and Should -BeNullOrEmpty surfaces it.
        $mismatch = $null
        try {
            & $script:AssertDeepEq `
                -Actual      $script:ActualReport `
                -Expected    $script:Canonical `
                -ExcludeKeys @('collected_at')
        } catch {
            $mismatch = "$_"
        }
        $mismatch | Should -BeNullOrEmpty -Because $mismatch
    }

    It 'metrics[].error key is present and null on success for all metrics' {
        $metrics = @($script:ActualReport['metrics'])
        $metrics.Count | Should -BeGreaterThan 0
        foreach ($m in $metrics) {
            $m.Keys | Should -Contain 'error'
            $m['error'] | Should -BeNullOrEmpty
        }
    }

    It 'Build-Summary produces correct shape: target_count, error_target_count, targets[]' {
        $summary = Build-Summary -Reports @($script:ActualReport)

        $summary.Keys | Should -Contain 'target_count'
        $summary.Keys | Should -Contain 'error_target_count'
        $summary.Keys | Should -Contain 'targets'

        $summary['target_count']       | Should -Be 1
        $summary['error_target_count'] | Should -Be 0

        $targets = @($summary['targets'])
        $targets.Count | Should -Be 1

        $t = $targets[0]
        $t.Keys | Should -Contain 'name'
        $t.Keys | Should -Contain 'cloud'
        $t.Keys | Should -Contain 'service'
        $t.Keys | Should -Contain 'metric_count'
        $t.Keys | Should -Contain 'error_count'
        $t.Keys | Should -Contain 'status'

        $t['name']         | Should -Be 'pg-server'
        $t['cloud']        | Should -Be 'azure'
        $t['service']      | Should -Be 'postgres-flexible'
        $t['metric_count'] | Should -Be 2
        $t['error_count']  | Should -Be 0
        $t['status']       | Should -Be 'ok'
    }

    It 'window values in report match the supplied start, end, and interval' {
        $w = $script:ActualReport['window']
        $w['start']    | Should -Be $script:WindowStart.ToString('o')
        $w['end']      | Should -Be $script:WindowEnd.ToString('o')
        $w['interval'] | Should -Be $script:Interval
    }

    It 'inventory resource_id matches the canonical value' {
        $script:ActualReport['inventory']['resource_id'] | Should -Be $script:ResourceId
    }

    It 'metric_definitions contains both expected definitions with correct key sets' {
        $defs = @($script:ActualReport['metric_definitions'])
        $defs.Count | Should -Be 2

        $requiredKeys = @('name', 'unit', 'aggregations', 'dimensions', 'granularities')
        foreach ($d in $defs) {
            foreach ($k in $requiredKeys) {
                $d.Keys | Should -Contain $k
            }
        }
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Section 2: Coverage gap — Auth.ps1 Invoke-AzToken error and success paths
# ─────────────────────────────────────────────────────────────────────────────
#
# Carry-forward from review: Invoke-AzToken body (lines 7-12 of Auth.ps1) was
# completely uncovered because the existing Auth test mocks Invoke-AzToken at
# the module boundary, never exercising its internal code.
#
# Strategy: use InModuleScope to shadow the external 'az' executable with a
# PowerShell function.  PowerShell resolves commands in function-first order
# (function > alias > cmdlet > external), so `& az @args 2>&1` in Invoke-AzToken
# picks up our local function.  We explicitly set $global:LASTEXITCODE to simulate
# non-zero / zero exit codes.

Describe 'Auth — Invoke-AzToken error path (carry-forward coverage)' {
    BeforeEach {
        # Ensure token cache is clean so Get-DbToken really calls Invoke-AzToken
        InModuleScope DbMetrics { $script:DbTokenCache = @{} }
    }

    It 'throws az-token-failed message when az exits with non-zero exit code' {
        InModuleScope DbMetrics {
            function az {
                $global:LASTEXITCODE = 1
                "az: ERROR: Please run 'az login'"
            }
            try {
                { Invoke-AzToken -Subscription 'sub1' -Tenant 'tenant1' } | Should -Throw '*az token failed*'
            } finally {
                $global:LASTEXITCODE = 0
            }
        }
    }

    It 'returns raw JSON output when az exits with zero exit code' {
        InModuleScope DbMetrics {
            function az {
                $global:LASTEXITCODE = 0
                '{"accessToken":"PARITY_TEST_TOKEN","tokenType":"Bearer"}'
            }
            $result = Invoke-AzToken -Subscription 'sub1'
            $result | Should -Match 'PARITY_TEST_TOKEN'
        }
    }

    It 'Get-DbToken propagates error when Invoke-AzToken throws' {
        Mock -ModuleName DbMetrics Invoke-AzToken { throw 'az token failed: login required' }
        { Get-DbToken -Subscription 'sub1' } | Should -Throw '*az token failed*'
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Section 3: Coverage gap — AzureMonitor.ps1 Get-MetricDefinition single-def
# ─────────────────────────────────────────────────────────────────────────────
#
# Carry-forward from review: the 1-element unary-comma path of Get-MetricDefinition
# (,$defs at end of function) was not explicitly exercised with a single-definition
# response.  The unary comma guard prevents a 1-element return from silently
# degrading to a scalar; this test confirms the guard holds.
#
# Note: $defs | Should -BeOfType ([array]) would be WRONG here — the pipeline
# operator unrolls the array and sends its single OrderedDictionary element to
# Should instead.  Use ($defs -is [array]) | Should -Be $true instead.

Describe 'AzureMonitor — Get-MetricDefinition single-def array safety (carry-forward coverage)' {
    It 'returns an array of length 1 when the response contains exactly one definition' {
        # Inline the fixture inside the mock body to avoid closure/module-scope
        # issues: local variables defined in It blocks are NOT accessible in
        # -ModuleName mock scriptblocks executed in the module's scope.
        Mock -ModuleName DbMetrics Invoke-AzureRest {
            [PSCustomObject]@{
                value = @(
                    [PSCustomObject]@{
                        name                      = [PSCustomObject]@{ value = 'cpu_percent' }
                        unit                      = 'Percent'
                        supportedAggregationTypes = @('Average')
                        dimensions                = @()
                        metricAvailabilities      = @([PSCustomObject]@{ timeGrain = 'PT1M' })
                    }
                )
            }
        }

        $defs = Get-MetricDefinition `
            -ResourceId '/subscriptions/s/resourceGroups/r/providers/Microsoft.DBforPostgreSQL/flexibleServers/srv' `
            -Token 'tok'

        # Must remain an array — never unwrap to a scalar OrderedDictionary.
        # Use ($defs -is [array]) to avoid pipeline unrolling the array.
        ($defs -is [array]) | Should -Be $true
        $defs.Count         | Should -Be 1
        $defs[0].name       | Should -Be 'cpu_percent'
        $defs[0].unit       | Should -Be 'Percent'
        @($defs[0].aggregations) | Should -Be @('Average')
    }
}
