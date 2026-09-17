BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force

    # ---------------------------------------------------------------------------
    # Shared fixtures
    # ---------------------------------------------------------------------------
    $script:Target = @{ name = 'test-server'; cloud = 'azure'; service = 'postgres-flexible' }
    $script:Scope  = '/subscriptions/00000000/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/test-server'
    $script:Inv    = @{
        server                 = @{
            name                = 'test-server'; location = 'eastus'
            version             = '15';          minor_version = '3'
            state               = 'Ready'
            sku                 = @{ name = 'Standard_D4s_v3'; tier = 'GeneralPurpose' }
            storage             = @{ size_gb = 128; iops = 3000; auto_grow = 'Enabled' }
            high_availability   = @{ mode = 'ZoneRedundant'; state = 'Healthy' }
        }
        parameters             = @( @{ name = 'p1'; value = '1' } )
        parameters_non_default = @()
        databases              = @( 'mydb' )
    }
    $script:Window = @{
        Start = [datetime]::new(2026, 1, 2, 2, 0, 0, [System.DateTimeKind]::Utc)
        End   = [datetime]::new(2026, 1, 2, 3, 0, 0, [System.DateTimeKind]::Utc)
    }
}

# ---------------------------------------------------------------------------
# Build-Report
# ---------------------------------------------------------------------------
Describe 'Build-Report' {

    It 'emits keys in canonical order' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        [array]$keys = $report.Keys
        $expected = @(
            'collected_at', 'name', 'cloud', 'service', 'resource_scope',
            'window', 'inventory', 'metric_definitions', 'metrics'
        )
        $keys | Should -Be $expected
    }

    It 'nests window with start, end and interval keys' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT5M'

        $report.window.Keys | Should -Contain 'start'
        $report.window.Keys | Should -Contain 'end'
        $report.window.Keys | Should -Contain 'interval'
        $report.window['interval'] | Should -Be 'PT5M'
    }

    It 'includes inventory, metric_definitions and metrics' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        $report.inventory | Should -Not -BeNullOrEmpty
        $null -ne $report.metric_definitions | Should -Be $true
        $null -ne $report.metrics | Should -Be $true
    }

    It 'keeps metrics as array with 1 element' {
        $m = [ordered]@{ name = 'cpu_percent'; unit = 'Percent'; granularity = 'PT1M'
                         timeseries = @(); error = $null }
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($m) `
            -Window $script:Window -Interval 'PT1M'

        $report.metrics.GetType().IsArray | Should -Be $true
        $report.metrics.Count | Should -Be 1
    }

    It 'keeps metric_definitions as array with 1 element' {
        $d = [ordered]@{ name = 'cpu_percent'; unit = 'Percent'
                         aggregations = @('Average'); dimensions = @(); granularities = @('PT1M') }
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @($d) -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        $report.metric_definitions.GetType().IsArray | Should -Be $true
        $report.metric_definitions.Count | Should -Be 1
    }

    It 'sets name, cloud and service from target' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        $report.name    | Should -Be 'test-server'
        $report.cloud   | Should -Be 'azure'
        $report.service | Should -Be 'postgres-flexible'
    }

    It 'sets resource_scope' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        $report.resource_scope | Should -Be $script:Scope
    }

    It 'keeps empty arrays as arrays' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        $report.metric_definitions.GetType().IsArray | Should -Be $true
        $report.metrics.GetType().IsArray | Should -Be $true
    }
}

# ---------------------------------------------------------------------------
# Build-Summary
# ---------------------------------------------------------------------------
Describe 'Build-Summary' {

    It 'status is ok when no errors' {
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'postgres-flexible'; metrics = @() }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].status  | Should -Be 'ok'
        $summary.error_target_count | Should -Be 0
    }

    It 'status is partial when a metric has a truthy error' {
        $m   = [ordered]@{ name = 'm1'; error = 'Connection refused' }
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'postgres-flexible'
                           metrics = @($m) }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].status      | Should -Be 'partial'
        $summary.targets[0].error_count | Should -Be 1
        $summary.error_target_count     | Should -Be 1
    }

    It 'status is error when report has truthy top-level error' {
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'postgres-flexible'
                           metrics = @(); error = 'Auth failed' }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].status  | Should -Be 'error'
        $summary.error_target_count | Should -Be 1
    }

    It 'top-level error takes precedence over metric errors' {
        $m   = [ordered]@{ name = 'm1'; error = 'metric error' }
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'postgres-flexible'
                           metrics = @($m); error = 'top-level error' }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].status | Should -Be 'error'
    }

    It 'targets is array even with 1 report' {
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'postgres-flexible'; metrics = @() }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets.GetType().IsArray | Should -Be $true
        $summary.targets.Count             | Should -Be 1
    }

    It 'counts error_target_count correctly with mixed statuses' {
        $rep1 = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'svc1'; metrics = @() }
        $rep2 = [ordered]@{ name = 'srv2'; cloud = 'azure'; service = 'svc2'
                            metrics = @(); error = 'oops' }
        $summary = Build-Summary -Reports @($rep1, $rep2)
        $summary.error_target_count | Should -Be 1
        $summary.target_count       | Should -Be 2
    }

    It 'falls back cloud and service to ? when absent' {
        $rep = [ordered]@{ name = 'srv1'; metrics = @() }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].cloud   | Should -Be '?'
        $summary.targets[0].service | Should -Be '?'
    }

    It 'counts metric_count and error_count correctly' {
        $m1  = [ordered]@{ name = 'm1'; error = $null }
        $m2  = [ordered]@{ name = 'm2'; error = 'err' }
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'svc'; metrics = @($m1, $m2) }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].metric_count | Should -Be 2
        $summary.targets[0].error_count  | Should -Be 1
    }

    It 'metric_count is 0 and error_count is 0 for an ERROR record with no metrics key' {
        $rep = [ordered]@{ name = 'x'; cloud = 'azure'; service = 'postgres-flexible'; error = 'boom' }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].metric_count   | Should -Be 0
        $summary.targets[0].error_count    | Should -Be 0
        $summary.targets[0].status         | Should -Be 'error'
        $summary.error_target_count        | Should -Be 1
    }

    It 'metric_count is 1 for a single-metric report (array-unroll regression)' {
        $m   = [ordered]@{ name = 'cpu_percent'; error = $null }
        $rep = [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'postgres-flexible'
                           metrics = @($m) }
        $summary = Build-Summary -Reports @($rep)
        $summary.targets[0].metric_count | Should -Be 1
    }
}

# ---------------------------------------------------------------------------
# Format-ConsoleSummary
# ---------------------------------------------------------------------------
Describe 'Format-ConsoleSummary' {

    # Helper: build a minimal report with one metric that has one timeseries
    # containing a known average summary — used as the regression trap for the
    # array-unroll bug (series[0] must be reachable, not the dict itself).
    BeforeAll {
        $script:StatSummary = [ordered]@{
            average = [ordered]@{ latest = 55.5; min = 10.0; max = 99.0; avg = 44.0; count = 3 }
        }
        $script:OneSeries = [ordered]@{
            dimensions = @{}
            points     = @()
            summary    = $script:StatSummary
        }
        $script:OneMetric = [ordered]@{
            name       = 'cpu_percent'
            unit       = 'Percent'
            granularity = 'PT1M'
            timeseries = @($script:OneSeries)
            error      = $null
        }
        $script:FullReport = Build-Report `
            -Target     $script:Target `
            -ResourceScope $script:Scope `
            -Inventory  $script:Inv `
            -Definitions @() `
            -Metrics    @($script:OneMetric) `
            -Window     $script:Window `
            -Interval   'PT1M'
    }

    It 'renders formatted float values for latest/avg/max (regression: not all dashes)' {
        $output = Format-ConsoleSummary -Report $script:FullReport
        # latest=55.5 → 55.50, avg=44.0 → 44.00, max=99.0 → 99.00
        $output | Should -Match '55\.50'
        $output | Should -Match '44\.00'
        $output | Should -Match '99\.00'
    }

    It 'renders ERROR row for a metric with truthy error' {
        $errMetric = [ordered]@{
            name       = 'cpu_percent'
            unit       = 'Percent'
            granularity = 'PT1M'
            timeseries = @()
            error      = 'Connection timed out'
        }
        $rep = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($errMetric) `
            -Window $script:Window -Interval 'PT1M'
        $output = Format-ConsoleSummary -Report $rep
        $output | Should -Match 'ERROR'
        $output | Should -Match 'Connection timed out'
    }

    It 'renders dash for a null stat' {
        $noSummaryMetric = [ordered]@{
            name       = 'disk_iops'
            unit       = 'Count'
            granularity = 'PT1M'
            timeseries = @([ordered]@{ dimensions = @{}; points = @(); summary = [ordered]@{} })
            error      = $null
        }
        $rep = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($noSummaryMetric) `
            -Window $script:Window -Interval 'PT1M'
        $output = Format-ConsoleSummary -Report $rep
        # All three stat columns should be '-' (7-wide right-aligned)
        $output | Should -Match '\s+-\s+-\s+-'
    }

    It 'formats floats N2 with thousands separators' {
        # 1234567.89 → "1,234,567.89"
        $bigSummary = [ordered]@{
            average = [ordered]@{ latest = 1234567.89; min = 0.0; max = 2000000.0; avg = 1000000.0; count = 1 }
        }
        $bigSeries = [ordered]@{ dimensions = @{}; points = @(); summary = $bigSummary }
        $bigMetric = [ordered]@{
            name = 'big_number'; unit = 'Count'; granularity = 'PT1M'
            timeseries = @($bigSeries); error = $null
        }
        $rep = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($bigMetric) `
            -Window $script:Window -Interval 'PT1M'
        $output = Format-ConsoleSummary -Report $rep
        $output | Should -Match '1,234,567\.89'
    }

    It 'sorts metrics by name' {
        $mZ = [ordered]@{ name = 'zzz'; unit = 'Count'; granularity = 'PT1M'
                          timeseries = @(); error = $null }
        $mA = [ordered]@{ name = 'aaa'; unit = 'Count'; granularity = 'PT1M'
                          timeseries = @(); error = $null }
        $rep = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($mZ, $mA) `
            -Window $script:Window -Interval 'PT1M'
        $output = Format-ConsoleSummary -Report $rep
        $posA = $output.IndexOf('aaa')
        $posZ = $output.IndexOf('zzz')
        $posA | Should -BeLessThan $posZ
    }

    It 'shows (+N dim series) suffix when metric has >1 timeseries' {
        $ts1 = [ordered]@{ dimensions = @{ engine = 'A' }; points = @(); summary = $script:StatSummary }
        $ts2 = [ordered]@{ dimensions = @{ engine = 'B' }; points = @(); summary = $script:StatSummary }
        $dimMetric = [ordered]@{
            name = 'cpu_percent'; unit = 'Percent'; granularity = 'PT1M'
            timeseries = @($ts1, $ts2); error = $null
        }
        $rep = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($dimMetric) `
            -Window $script:Window -Interval 'PT1M'
        $output = Format-ConsoleSummary -Report $rep
        $output | Should -Match '\(\+1 dim series\)'
    }

    It 'does NOT show dim series suffix for exactly 1 timeseries' {
        $output = Format-ConsoleSummary -Report $script:FullReport
        $output | Should -Not -Match 'dim series'
    }

    It 'contains === header, --- separator, cloud·service and server name' {
        $output = Format-ConsoleSummary -Report $script:FullReport
        $output | Should -Match '={70}'
        $output | Should -Match '-{70}'
        $output | Should -Match 'azure · postgres-flexible'
        $output | Should -Match 'test-server'
    }

    It 'contains inventory header lines' {
        $output = Format-ConsoleSummary -Report $script:FullReport
        $output | Should -Match 'Location\s+:'
        $output | Should -Match 'Version\s+:'
        $output | Should -Match 'SKU / tier\s+:'
        $output | Should -Match 'Storage\s+:'
        $output | Should -Match 'HA\s+:'
        $output | Should -Match 'State\s+:'
        $output | Should -Match 'Parameters\s+:'
    }

    It 'does not throw when server lacks sku/storage/ha (non-flexible inventory)' {
        $minimalInv = @{ server = @{ name = 'bare-server'; location = 'eastus'
                                     version = '14'; minor_version = '2'
                                     state = 'Ready' }
                         parameters = @(); parameters_non_default = @() }
        $rep = Build-Report -Target @{ name = 'bare'; cloud = 'azure'; service = 'sql-database' } `
            -ResourceScope '/id' -Inventory $minimalInv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'
        { Format-ConsoleSummary -Report $rep } | Should -Not -Throw
    }

    It 'contains the Metrics window line with arrow' {
        $output = Format-ConsoleSummary -Report $script:FullReport
        $output | Should -Match 'Metrics window:'
        $output | Should -Match 'PT1M'
    }
}

# ---------------------------------------------------------------------------
# Format-SummaryTable
# ---------------------------------------------------------------------------
Describe 'Format-SummaryTable' {

    It 'contains Targets: footer' {
        $summary = [ordered]@{
            targets = @(
                [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'pg'
                            metric_count = 5; error_count = 0; status = 'ok' }
            )
            target_count = 1
            error_target_count = 0
        }
        $table = Format-SummaryTable -Summary $summary
        $table | Should -Match 'Targets:'
    }

    It 'contains each target name' {
        $summary = [ordered]@{
            targets = @(
                [ordered]@{ name = 'server-alpha'; cloud = 'azure'; service = 'pg'
                            metric_count = 5; error_count = 0; status = 'ok' }
                [ordered]@{ name = 'server-beta';  cloud = 'azure'; service = 'pg'
                            metric_count = 3; error_count = 1; status = 'partial' }
            )
            target_count = 2
            error_target_count = 1
        }
        $table = Format-SummaryTable -Summary $summary
        $table | Should -Match 'server-alpha'
        $table | Should -Match 'server-beta'
    }

    It 'shows Not OK count' {
        $summary = [ordered]@{
            targets = @(
                [ordered]@{ name = 'srv1'; cloud = 'azure'; service = 'pg'
                            metric_count = 2; error_count = 0; status = 'ok' }
                [ordered]@{ name = 'srv2'; cloud = 'azure'; service = 'pg'
                            metric_count = 2; error_count = 1; status = 'partial' }
            )
            target_count = 2
            error_target_count = 1
        }
        $table = Format-SummaryTable -Summary $summary
        $table | Should -Match 'Not OK: 1'
    }
}

# ---------------------------------------------------------------------------
# Write-ReportJson
# ---------------------------------------------------------------------------
Describe 'Write-ReportJson' {

    BeforeEach {
        $script:TmpFile = [System.IO.Path]::GetTempFileName()
    }
    AfterEach {
        if (Test-Path $script:TmpFile) { Remove-Item $script:TmpFile -Force -ErrorAction SilentlyContinue }
    }

    It 'round-trips: parsed JSON has all expected top-level keys' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        Write-ReportJson -Report $report -Path $script:TmpFile
        $parsed = Get-Content -Raw $script:TmpFile | ConvertFrom-Json

        $expectedKeys = @(
            'collected_at', 'name', 'cloud', 'service', 'resource_scope',
            'window', 'inventory', 'metric_definitions', 'metrics'
        )
        foreach ($key in $expectedKeys) {
            $parsed.PSObject.Properties.Name | Should -Contain $key
        }
    }

    It 'round-trips: name, cloud, service values survive' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        Write-ReportJson -Report $report -Path $script:TmpFile
        $parsed = Get-Content -Raw $script:TmpFile | ConvertFrom-Json

        $parsed.name    | Should -Be 'test-server'
        $parsed.cloud   | Should -Be 'azure'
        $parsed.service | Should -Be 'postgres-flexible'
    }

    It 'file ends with a newline (last byte is LF 0x0A)' {
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @() `
            -Window $script:Window -Interval 'PT1M'

        Write-ReportJson -Report $report -Path $script:TmpFile
        $bytes = [System.IO.File]::ReadAllBytes($script:TmpFile)
        $bytes[-1] | Should -Be ([byte][char]"`n")
    }

    It 'serializes 1-element metrics array as a JSON array not a scalar' {
        $m = [ordered]@{ name = 'cpu_percent'; unit = 'Percent'; granularity = 'PT1M'
                         timeseries = @(); error = $null }
        $report = Build-Report -Target $script:Target -ResourceScope $script:Scope `
            -Inventory $script:Inv -Definitions @() -Metrics @($m) `
            -Window $script:Window -Interval 'PT1M'

        Write-ReportJson -Report $report -Path $script:TmpFile
        $raw    = Get-Content -Raw $script:TmpFile
        $parsed = $raw | ConvertFrom-Json
        # PSObject array property should have Count 1
        @($parsed.metrics).Count | Should -Be 1
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }
