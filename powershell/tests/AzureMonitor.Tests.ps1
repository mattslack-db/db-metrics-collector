BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force

    # Shared test coordinates
    $script:ResourceId  = '/subscriptions/sub1/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/myserver'
    $script:Token       = 'test-token'
    $script:Start       = [datetime]::new(2026, 1, 1, 0, 0, 0, [System.DateTimeKind]::Utc)
    $script:End         = [datetime]::new(2026, 1, 1, 1, 0, 0, [System.DateTimeKind]::Utc)
    $script:Granularity = [timespan]::FromMinutes(1)

    # ── Canned metricDefinitions response ────────────────────────────────────
    # cpu_percent: has dimensions, includes 'None' aggregation (should be stripped)
    # memory_percent: no dimensions, all aggregations are 'None' → fallback Average
    $script:MockDefsResponse = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name                      = [PSCustomObject]@{ value = 'cpu_percent' }
                unit                      = 'Percent'
                supportedAggregationTypes = @('Average', 'Maximum', 'None')
                dimensions                = @([PSCustomObject]@{ value = 'DatabaseName' })
                metricAvailabilities      = @(
                    [PSCustomObject]@{ timeGrain = 'PT1M' },
                    [PSCustomObject]@{ timeGrain = 'PT5M' }
                )
            },
            [PSCustomObject]@{
                name                      = [PSCustomObject]@{ value = 'memory_percent' }
                unit                      = 'Percent'
                supportedAggregationTypes = @('None')
                dimensions                = $null
                metricAvailabilities      = @([PSCustomObject]@{ timeGrain = 'PT5M' })
            }
        )
    }

    # ── Canned metrics response for cpu_percent (dimensioned, has total) ─────
    $script:MockCpuResponse = [PSCustomObject]@{
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
                                total     = 100.0
                            },
                            [PSCustomObject]@{
                                timeStamp = '2026-01-01T00:01:00Z'
                                average   = 30.0
                                total     = 120.0
                            }
                        )
                    }
                )
            }
        )
    }

    # ── Canned metrics response for memory_percent (no dimensions) ───────────
    $script:MockMemResponse = [PSCustomObject]@{
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
                                average   = 50.0
                            }
                        )
                    }
                )
            }
        )
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }

# ─── Get-MetricDefinition ─────────────────────────────────────────────────────

Describe 'Get-MetricDefinition' {

    It 'maps name, unit, aggregations, dimensions, and granularities from canned payload' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockDefsResponse }

        $defs = Get-MetricDefinition -ResourceId $script:ResourceId -Token $script:Token

        $defs.Count | Should -Be 2

        # cpu_percent: 'None' stripped, dimensions present, two granularities
        $cpu = $defs[0]
        $cpu.name         | Should -Be 'cpu_percent'
        $cpu.unit         | Should -Be 'Percent'
        $cpu.aggregations | Should -Not -Contain 'None'
        $cpu.aggregations | Should -Contain 'Average'
        $cpu.aggregations | Should -Contain 'Maximum'
        $cpu.dimensions   | Should -Contain 'DatabaseName'
        $cpu.granularities | Should -Contain 'PT1M'
        $cpu.granularities | Should -Contain 'PT5M'

        # memory_percent: all aggs are None → fallback to Average; no dimensions
        $mem = $defs[1]
        $mem.name         | Should -Be 'memory_percent'
        $mem.aggregations | Should -Be @('Average')
        $mem.dimensions.Count | Should -Be 0
        $mem.granularities | Should -Contain 'PT5M'
    }

    It 'calls the metricDefinitions endpoint for the given ResourceId' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockDefsResponse }

        Get-MetricDefinition -ResourceId $script:ResourceId -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest -Times 1 -Exactly `
            -ParameterFilter { $Uri -like "*${script:ResourceId}*metricDefinitions*" }
    }
}

# ─── Get-MetricSeries ─────────────────────────────────────────────────────────

Describe 'Get-MetricSeries' {

    It 'issues exactly one REST call per definition (two defs = two calls)' {
        # Two definitions: cpu (dimensioned) and memory (no dimensions)
        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average', 'Maximum')
            dimensions    = @('DatabaseName')
            granularities = @('PT1M', 'PT5M')
        }
        $defMem = [ordered]@{
            name          = 'memory_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @()
            granularities = @('PT5M')
        }

        # Separate mocks per metric name to avoid stateful call counting
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*cpu_percent*' } `
            { $script:MockCpuResponse }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            { $script:MockMemResponse }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu, $defMem) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        # Exactly one REST call per definition
        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest -Times 2 -Exactly

        $results.Count | Should -Be 2
    }

    It 'includes OData $filter in the URI for a dimensioned metric' {
        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @('DatabaseName')
            granularities = @('PT1M')
        }

        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCpuResponse }

        Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        # URI must carry the literal $filter= parameter
        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest -Times 1 `
            -ParameterFilter { $Uri -like '*$filter=*' }
    }

    It 'sets the resolved granularity string on each returned metric' {
        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @()
            granularities = @('PT1M', 'PT5M')
        }

        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCpuResponse }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        # Requested PT1M is available → granularity = PT1M
        $results[0].granularity | Should -Be 'PT1M'
    }

    It 'maps total field in data points through to summary' {
        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average', 'Total')
            dimensions    = @()
            granularities = @('PT1M')
        }

        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCpuResponse }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        $ts      = $results[0].timeseries[0]
        $summary = $ts.summary

        # Points carry total field
        $ts.points[0].total | Should -Be 100.0
        $ts.points[1].total | Should -Be 120.0

        # Summary contains a 'total' column summary
        $summary.Keys | Should -Contain 'total'
        $summary.total.min | Should -Be 100.0
        $summary.total.max | Should -Be 120.0
    }

    It 'maps timeseries dimensions from metadatavalues' {
        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @('DatabaseName')
            granularities = @('PT1M')
        }

        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCpuResponse }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        $dims = $results[0].timeseries[0].dimensions
        $dims['DatabaseName'] | Should -Be 'mydb'
    }

    It 'sets error=$null on success and error=$null key is present' {
        $defMem = [ordered]@{
            name          = 'memory_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @()
            granularities = @('PT5M')
        }

        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockMemResponse }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defMem) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        $results[0].Keys | Should -Contain 'error'
        $results[0].error | Should -BeNullOrEmpty
    }

    It 'retries without $filter when first call fails, succeeds on retry' {
        # Definition has dimensions → first URI will carry $filter
        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @('DatabaseName')
            granularities = @('PT1M')
        }

        # First call (with $filter) fails; second call (no $filter) succeeds
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*$filter=*' } `
            { throw "filter not supported" }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            { $script:MockCpuResponse }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        # Two calls total: one with filter (threw), one without (succeeded)
        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest -Times 2 -Exactly

        # Result is a valid success (no error)
        $results.Count  | Should -Be 1
        $results[0].name  | Should -Be 'cpu_percent'
        $results[0].error | Should -BeNullOrEmpty
    }

    It 'records a non-null error and empty timeseries when both calls fail, and continues to other defs' {
        # cpu_percent: all calls fail (matched by metricname)
        # memory_percent: succeeds
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*cpu_percent*' } `
            { throw "metric unavailable" }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            { $script:MockMemResponse }

        $defCpu = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @('DatabaseName')   # has dimensions → first URI has $filter
            granularities = @('PT1M')
        }
        $defMem = [ordered]@{
            name          = 'memory_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @()
            granularities = @('PT5M')
        }

        $results = Get-MetricSeries `
            -ResourceId  $script:ResourceId `
            -Definitions @($defCpu, $defMem) `
            -Start       $script:Start `
            -End         $script:End `
            -Granularity $script:Granularity `
            -Token       $script:Token

        # cpu: 2 failed calls (filter then retry); memory: 1 successful call
        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest -Times 3 -Exactly

        # Both defs produce a result (run continues after error)
        $results.Count | Should -Be 2

        # cpu_percent result carries the error, empty timeseries
        $cpuResult = $results | Where-Object { $_.name -eq 'cpu_percent' }
        $cpuResult.error         | Should -Not -BeNullOrEmpty
        $cpuResult.unit          | Should -BeNullOrEmpty
        $cpuResult.granularity   | Should -BeNullOrEmpty
        $cpuResult.timeseries.Count | Should -Be 0

        # memory_percent result is valid
        $memResult = $results | Where-Object { $_.name -eq 'memory_percent' }
        $memResult.error | Should -BeNullOrEmpty
        $memResult.timeseries.Count | Should -Be 1
    }
}

# ── Regression: PSCustomObject.count synthetic property ──────────────────────
#
# PowerShell's member access ($dp.$field) returns the synthetic .Count = 1 for
# any PSCustomObject whose 'count' property is absent.  Get-MetricSeries MUST
# use $dp.PSObject.Properties[$field] (existence check) so absent Azure Monitor
# fields are truly omitted from the point, matching Python's getattr behaviour.
#
# This test MUST FAIL before the fix (member access) and PASS after
# (PSObject.Properties access).

Describe 'Get-MetricSeries — synthetic .Count regression' {
    It 'omits count key from point when Azure response has no count property' {
        # Data point has only timeStamp + average — no real 'count' property.
        # Before fix: $dp.count = 1 (synthetic) → count added to point.
        # After fix: PSObject.Properties['count'] = $null → count omitted.
        Mock -ModuleName DbMetrics Invoke-AzureRest {
            [PSCustomObject]@{
                value = @(
                    [PSCustomObject]@{
                        name       = [PSCustomObject]@{ value = 'cpu_percent' }
                        unit       = 'Percent'
                        timeseries = @(
                            [PSCustomObject]@{
                                metadatavalues = @()
                                data           = @(
                                    [PSCustomObject]@{
                                        timeStamp = '2026-01-01T00:00:00Z'
                                        average   = 42.0
                                        # No 'count' property — absence must propagate
                                    }
                                )
                            }
                        )
                    }
                )
            }
        }

        $def = [ordered]@{
            name          = 'cpu_percent'
            unit          = 'Percent'
            aggregations  = @('Average')
            dimensions    = @()
            granularities = @('PT1M')
        }

        $results = Get-MetricSeries `
            -ResourceId   $script:ResourceId `
            -Definitions  @($def) `
            -Start        $script:Start `
            -End          $script:End `
            -Granularity  $script:Granularity `
            -Token        $script:Token

        $point = $results[0].timeseries[0].points[0]

        # average is present (real property)
        $point.Keys | Should -Contain 'average'
        $point['average'] | Should -Be 42.0

        # count MUST be absent — the Azure response carried no count aggregation
        $point.Keys | Should -Not -Contain 'count'
    }
}
