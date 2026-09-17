BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force

    # ── Minimal fake inventory that satisfies Format-ConsoleSummary ───────────────
    # All server sub-fields are present so the render loop won't null-ref.
    $script:FakeInventory = [ordered]@{
        resource_id            = '/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-server'
        server                 = [ordered]@{
            id                          = '/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.DBforPostgreSQL/flexibleServers/pg-server'
            name                        = 'pg-server'
            location                    = 'eastus'
            state                       = 'Ready'
            version                     = '14'
            minor_version               = '5'
            fully_qualified_domain_name = 'pg-server.postgres.database.azure.com'
            administrator_login         = 'pgadmin'
            availability_zone           = '1'
            sku                         = [ordered]@{ name = 'Standard_D2s_v3'; tier = 'GeneralPurpose' }
            storage                     = [ordered]@{
                size_gb         = 32
                tier            = 'P4'
                iops            = 396
                auto_grow       = 'Disabled'
                auto_io_scaling = 'Enabled'
                type            = 'Premium_LRS'
            }
            high_availability           = [ordered]@{
                mode                      = 'Disabled'
                state                     = 'NotEnabled'
                standby_availability_zone = $null
            }
            backup             = $null
            network            = $null
            maintenance_window = $null
        }
        parameters             = @()
        parameters_non_default = @()
        databases              = @('postgres')
    }

    # ── Fake metric definition — needed because Get-MetricSeries has a Mandatory
    # [array]$Definitions parameter without [AllowEmptyCollection()], so Pester's
    # mock wrapper refuses an empty collection just as the real function would.
    $script:FakeMetricDef = [ordered]@{
        name          = 'cpu_percent'
        unit          = 'Percent'
        aggregations  = @('Average')
        dimensions    = @()
        granularities = @('PT1M')
    }
}

# ── Get-TargetsFromArgs — unit tests (pure, no mocks needed) ───────────────────
# NOTE: @() wrapper is used when capturing results to prevent PowerShell's
# pipeline unrolling a single-element return.

Describe 'Get-TargetsFromArgs' {

    It 'builds a single target from Service + identifier params' {
        $p = @{
            Service       = 'postgres-flexible'
            Subscription  = 'sub-1'
            ResourceGroup = 'rg-1'
            ServerName    = 'pg-server'
        }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets | Should -HaveCount 1
        $targets[0]['name']                     | Should -Be 'pg-server'
        $targets[0]['service']                  | Should -Be 'postgres-flexible'
        $targets[0]['cloud']                    | Should -Be 'azure'
        $targets[0]['params']['subscription']   | Should -Be 'sub-1'
        $targets[0]['params']['resource_group'] | Should -Be 'rg-1'
        $targets[0]['params']['server_name']    | Should -Be 'pg-server'
    }

    It 'returns exactly one target for a single-target input (array-safety)' {
        $p = @{ Service = 'postgres-flexible' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets.Count | Should -Be 1
    }

    It 'derives name from server_name' {
        $p = @{ Service = 'postgres-flexible'; ServerName = 'myserver' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['name'] | Should -Be 'myserver'
    }

    It 'derives name from instance_name when no server_name present' {
        $p = @{ Service = 'sql-managed-instance'; InstanceName = 'my-mi' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['name'] | Should -Be 'my-mi'
    }

    It 'derives name from cluster_name when server_name and instance_name are absent' {
        $p = @{ Service = 'cosmos-postgres'; ClusterName = 'my-cluster' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['name'] | Should -Be 'my-cluster'
    }

    It 'falls back to service as name when no identifier flag provided' {
        $p = @{ Service = 'postgres-flexible' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['name'] | Should -Be 'postgres-flexible'
    }

    It 'applies default hours = 1.0 when Hours is absent' {
        $p = @{ Service = 'postgres-flexible' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['hours'] | Should -Be 1.0
    }

    It 'applies default interval = PT1M when Interval is absent' {
        $p = @{ Service = 'postgres-flexible' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['interval'] | Should -Be 'PT1M'
    }

    It 'honors explicit Hours and Interval' {
        $p = @{ Service = 'postgres-flexible'; Hours = 6.0; Interval = 'PT5M' }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets[0]['hours']    | Should -Be 6.0
        $targets[0]['interval'] | Should -Be 'PT5M'
    }

    It 'throws when -Config is combined with -Service (mutually exclusive)' {
        $cfgPath = Join-Path $TestDrive 'x.json'
        Set-Content $cfgPath '{}'
        $p = @{ Config = $cfgPath; Service = 'postgres-flexible' }
        { Get-TargetsFromArgs -BoundParams $p } | Should -Throw -ExpectedMessage '*mutually exclusive*'
    }

    It 'throws when -Config is combined with -ServerName' {
        $cfgPath = Join-Path $TestDrive 'x2.json'
        Set-Content $cfgPath '{}'
        $p = @{ Config = $cfgPath; ServerName = 'pg-server' }
        { Get-TargetsFromArgs -BoundParams $p } | Should -Throw -ExpectedMessage '*mutually exclusive*'
    }

    It 'throws when -Service is absent and -Config is not provided' {
        $p = @{ Subscription = 'sub-1' }
        { Get-TargetsFromArgs -BoundParams $p } | Should -Throw -ExpectedMessage '*-Service*'
    }

    It 'loads targets from a valid config file' {
        $cfgPath = Join-Path $TestDrive 'multi.json'
        $json = @{
            targets = @(
                @{ name = 't1'; cloud = 'azure'; service = 'postgres-flexible'; subscription = 'sub-1'; resource_group = 'rg-1'; server_name = 'pg1' },
                @{ name = 't2'; cloud = 'azure'; service = 'mysql-flexible';    subscription = 'sub-1'; resource_group = 'rg-1'; server_name = 'my1' }
            )
        } | ConvertTo-Json -Depth 5
        Set-Content $cfgPath $json
        $p = @{ Config = $cfgPath }
        $targets = @(Get-TargetsFromArgs -BoundParams $p)
        $targets.Count | Should -Be 2
        $targets[0]['name'] | Should -Be 't1'
        $targets[1]['name'] | Should -Be 't2'
    }
}

# ── Invoke-Run — integration tests (full run loop with mocked network) ─────────

Describe 'Invoke-Run' {

    # Shared mocks active for every It in this Describe.
    BeforeEach {
        # Each test gets its own isolated working directory so file counts are clean.
        $script:TestWorkDir = Join-Path $TestDrive ([guid]::NewGuid().ToString())
        New-Item -ItemType Directory -Path $script:TestWorkDir | Out-Null
        Push-Location $script:TestWorkDir
        # Sync .NET's current directory with PowerShell's so that
        # [System.IO.File]::WriteAllText (used by Write-ReportJson) writes to
        # the same location that Get-ChildItem searches.
        [System.IO.Directory]::SetCurrentDirectory($script:TestWorkDir)

        Mock -ModuleName DbMetrics Get-DbToken { return 'fake-token' }

        # Return a one-element array (non-empty) so that Get-MetricSeries — whose
        # Mandatory [array]$Definitions has no [AllowEmptyCollection()] — is
        # satisfied even through Pester's mock wrapper.
        Mock -ModuleName DbMetrics Get-MetricDefinition { , @($script:FakeMetricDef) }
        # Comma-return an empty array to mirror the real Get-MetricSeries contract:
        # callers assign directly, so a bare `@()` would collapse to $null.
        Mock -ModuleName DbMetrics Get-MetricSeries     { return ,@() }
    }

    AfterEach {
        Pop-Location
        [System.IO.Directory]::SetCurrentDirectory((Get-Location).ProviderPath)
    }

    # ── Single-target success ──────────────────────────────────────────────────

    Context 'Single-target success path' {

        It 'writes one metrics_*.json and returns exit code 0' {
            Mock -ModuleName DbMetrics Get-FlexibleInventory { return $script:FakeInventory }

            $p = @{
                Service       = 'postgres-flexible'
                Subscription  = 'sub-1'
                ResourceGroup = 'rg-1'
                ServerName    = 'pg-server'
                NoConsole     = $true
            }
            $rc = Invoke-Run -BoundParams $p
            $rc | Should -Be 0

            $files = @(Get-ChildItem -Filter 'metrics_*.json')
            $files.Count | Should -Be 1
        }

        It 'honors -Out override for single-target output path' {
            Mock -ModuleName DbMetrics Get-FlexibleInventory { return $script:FakeInventory }

            $outPath = Join-Path $script:TestWorkDir 'custom-report.json'
            $p = @{
                Service       = 'postgres-flexible'
                Subscription  = 'sub-1'
                ResourceGroup = 'rg-1'
                ServerName    = 'pg-server'
                Out           = $outPath
                NoConsole     = $true
            }
            $rc = Invoke-Run -BoundParams $p
            $rc | Should -Be 0
            Test-Path $outPath | Should -Be $true
        }

        It 'does not write a summary file for a single target' {
            Mock -ModuleName DbMetrics Get-FlexibleInventory { return $script:FakeInventory }

            $p = @{
                Service       = 'postgres-flexible'
                Subscription  = 'sub-1'
                ResourceGroup = 'rg-1'
                ServerName    = 'pg-server'
                NoConsole     = $true
            }
            Invoke-Run -BoundParams $p
            @(Get-ChildItem -Filter 'summary_*.json').Count | Should -Be 0
        }
    }

    # ── Usage errors (return 2) ────────────────────────────────────────────────

    Context 'Usage errors (exit code 2)' {

        It 'returns 2 when -Config and -Service are both present' {
            $cfgPath = Join-Path $script:TestWorkDir 'cfg.json'
            Set-Content $cfgPath '{}'
            $p = @{ Config = $cfgPath; Service = 'postgres-flexible' }
            Invoke-Run -BoundParams $p | Should -Be 2
        }

        It 'returns 2 when -Config and -ServerName are both present' {
            $cfgPath = Join-Path $script:TestWorkDir 'cfg2.json'
            Set-Content $cfgPath '{}'
            $p = @{ Config = $cfgPath; ServerName = 'pg-server' }
            Invoke-Run -BoundParams $p | Should -Be 2
        }

        It 'returns 2 when -Service is absent and -Config is not set' {
            $p = @{ Subscription = 'sub-1'; ResourceGroup = 'rg-1'; ServerName = 'pg-server' }
            Invoke-Run -BoundParams $p | Should -Be 2
        }

        It 'returns 2 when -Interval is not a valid ISO-8601 duration' {
            $p = @{
                Service       = 'postgres-flexible'
                Subscription  = 'sub-1'
                ResourceGroup = 'rg-1'
                ServerName    = 'pg-server'
                Interval      = 'not-a-duration'
                NoConsole     = $true
            }
            Invoke-Run -BoundParams $p | Should -Be 2
        }

        It 'returns 2 when Hours is zero' {
            $p = @{
                Service       = 'postgres-flexible'
                Subscription  = 'sub-1'
                ResourceGroup = 'rg-1'
                ServerName    = 'pg-server'
                Hours         = 0.0
                NoConsole     = $true
            }
            Invoke-Run -BoundParams $p | Should -Be 2
        }

        It 'returns 2 when Hours is negative' {
            $p = @{
                Service       = 'postgres-flexible'
                Subscription  = 'sub-1'
                ResourceGroup = 'rg-1'
                ServerName    = 'pg-server'
                Hours         = -2.5
                NoConsole     = $true
            }
            Invoke-Run -BoundParams $p | Should -Be 2
        }
    }

    # ── Non-fatal per-target failure ───────────────────────────────────────────

    Context 'Non-fatal per-target failure' {

        It 'records failed target as error report, processes remaining targets, and returns 1' {
            # postgres-flexible target throws during inventory; mysql-flexible succeeds.
            Mock -ModuleName DbMetrics Get-FlexibleInventory `
                -ParameterFilter { $SubEngineNamespace -like '*PostgreSQL*' } `
                { throw 'simulated inventory failure' }

            Mock -ModuleName DbMetrics Get-FlexibleInventory `
                -ParameterFilter { $SubEngineNamespace -like '*MySQL*' } `
                { return $script:FakeInventory }

            $cfgPath = Join-Path $script:TestWorkDir 'two-targets.json'
            $json = @{
                targets = @(
                    @{
                        name           = 'failing-target'
                        cloud          = 'azure'
                        service        = 'postgres-flexible'
                        subscription   = 'sub-1'
                        resource_group = 'rg-1'
                        server_name    = 'fail-server'
                    },
                    @{
                        name           = 'ok-target'
                        cloud          = 'azure'
                        service        = 'mysql-flexible'
                        subscription   = 'sub-1'
                        resource_group = 'rg-1'
                        server_name    = 'ok-server'
                    }
                )
            } | ConvertTo-Json -Depth 5
            Set-Content $cfgPath $json

            $p = @{ Config = $cfgPath; NoConsole = $true }
            $rc = Invoke-Run -BoundParams $p
            $rc | Should -Be 1

            # Only the successful target should have a metrics file.
            $metricsFiles = @(Get-ChildItem -Filter 'metrics_*.json')
            $metricsFiles.Count | Should -Be 1
            $metricsFiles[0].Name | Should -BeLike 'metrics_ok-target_*'

            # Summary file is always written for multi-target runs.
            @(Get-ChildItem -Filter 'summary_*.json').Count | Should -Be 1
        }
    }

    # ── Multi-target success path ──────────────────────────────────────────────

    Context 'Multi-target success path' {

        It 'writes 2 metrics files, 1 summary file, and returns 0' {
            Mock -ModuleName DbMetrics Get-FlexibleInventory { return $script:FakeInventory }

            $cfgPath = Join-Path $script:TestWorkDir 'multi.json'
            $json = @{
                targets = @(
                    @{ name = 'target-1'; cloud = 'azure'; service = 'postgres-flexible'; subscription = 'sub-1'; resource_group = 'rg-1'; server_name = 'pg1' },
                    @{ name = 'target-2'; cloud = 'azure'; service = 'mysql-flexible';    subscription = 'sub-1'; resource_group = 'rg-1'; server_name = 'my1' }
                )
            } | ConvertTo-Json -Depth 5
            Set-Content $cfgPath $json

            $p = @{ Config = $cfgPath; NoConsole = $true }
            $rc = Invoke-Run -BoundParams $p
            $rc | Should -Be 0

            @(Get-ChildItem -Filter 'metrics_*.json').Count | Should -Be 2
            @(Get-ChildItem -Filter 'summary_*.json').Count | Should -Be 1
        }

        It 'prints the summary table when NoConsole is not set' {
            Mock -ModuleName DbMetrics Get-FlexibleInventory { return $script:FakeInventory }

            $cfgPath = Join-Path $script:TestWorkDir 'multi2.json'
            $json = @{
                targets = @(
                    @{ name = 'target-a'; cloud = 'azure'; service = 'postgres-flexible'; subscription = 'sub-1'; resource_group = 'rg-1'; server_name = 'pga' },
                    @{ name = 'target-b'; cloud = 'azure'; service = 'mysql-flexible';    subscription = 'sub-1'; resource_group = 'rg-1'; server_name = 'myb' }
                )
            } | ConvertTo-Json -Depth 5
            Set-Content $cfgPath $json

            # NoConsole absent — Format-SummaryTable output is printed via Write-Host.
            # This test verifies it completes without error and returns 0.
            $p = @{ Config = $cfgPath }
            $rc = Invoke-Run -BoundParams $p
            $rc | Should -Be 0
        }
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }
