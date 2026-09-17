BeforeAll {
    Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force

    # ── Common test coordinates ─────────────────────────────────────────────────
    $script:Sub   = 'sub123'
    $script:Rg    = 'rg1'
    $script:Token = 'test-token'

    $script:FlexRid   = "/subscriptions/$($script:Sub)/resourceGroups/$($script:Rg)/providers/Microsoft.DBforPostgreSQL/flexibleServers/srv1"
    $script:MySQLRid  = "/subscriptions/$($script:Sub)/resourceGroups/$($script:Rg)/providers/Microsoft.DBforMySQL/flexibleServers/srv1"
    $script:SingleRid = "/subscriptions/$($script:Sub)/resourceGroups/$($script:Rg)/providers/Microsoft.DBforPostgreSQL/servers/srv1"

    # ── Canned flexible server ARM response ─────────────────────────────────────
    # Modelled on examples/example_report.json inventory.server shape
    $script:MockServerResp = [PSCustomObject]@{
        id       = $script:FlexRid
        name     = 'srv1'
        location = 'East US 2'
        sku      = [PSCustomObject]@{
            name = 'Standard_B2s'
            tier = 'Burstable'
        }
        properties = [PSCustomObject]@{
            state                    = 'Ready'
            version                  = '17'
            minorVersion             = '11'
            fullyQualifiedDomainName = 'srv1.postgres.database.azure.com'
            administratorLogin       = 'pgadmin'
            availabilityZone         = '1'
            storage                  = [PSCustomObject]@{
                storageSizeGB   = 32
                tier            = 'P4'
                iops            = 120
                autoGrow        = 'Disabled'
                autoIoScaling   = 'Enabled'
                type            = 'Premium_LRS'
            }
            highAvailability         = [PSCustomObject]@{
                mode                    = 'Disabled'
                state                   = 'NotEnabled'
                standbyAvailabilityZone = $null
            }
            backup                   = [PSCustomObject]@{
                backupRetentionDays  = 8
                geoRedundantBackup   = 'Disabled'
                earliestRestoreDate  = '2026-09-09T06:30:04.646315+00:00'
            }
            network                  = [PSCustomObject]@{
                publicNetworkAccess          = 'Enabled'
                delegatedSubnetResourceId    = $null
                privateDnsZoneArmResourceId  = $null
            }
            maintenanceWindow        = [PSCustomObject]@{
                customWindow = 'Disabled'
                dayOfWeek    = 0
                startHour    = 0
                startMinute  = 0
            }
        }
    }

    # ── Canned configurations response (non-default + default) ─────────────────
    # max_connections: value 200 != default 100  → is_non_default = true
    # work_mem: value == default                 → is_non_default = false
    $script:MockConfigsResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name       = 'max_connections'
                properties = [PSCustomObject]@{
                    value          = '200'
                    defaultValue   = '100'
                    source         = 'user-override'
                    isDynamicConfig = $true
                    isReadOnly     = $false
                    unit           = $null
                    description    = 'Maximum number of connections'
                }
            },
            [PSCustomObject]@{
                name       = 'work_mem'
                properties = [PSCustomObject]@{
                    value          = '4096'
                    defaultValue   = '4096'
                    source         = 'system-default'
                    isDynamicConfig = $true
                    isReadOnly     = $false
                    unit           = 'kB'
                    description    = 'Work memory'
                }
            }
        )
    }

    # ── Canned databases response ───────────────────────────────────────────────
    $script:MockDatabasesResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{ name = 'postgres' },
            [PSCustomObject]@{ name = 'myapp' }
        )
    }

    # ── Canned single-config response (exercises single-element array safety) ───
    $script:MockOneConfigResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name       = 'work_mem'
                properties = [PSCustomObject]@{
                    value          = '4096'
                    defaultValue   = '4096'
                    source         = 'system-default'
                    isDynamicConfig = $true
                    isReadOnly     = $false
                    unit           = 'kB'
                    description    = 'Work memory'
                }
            }
        )
    }

    # ── Canned single-server ARM response ───────────────────────────────────────
    $script:MockSingleServerResp = [PSCustomObject]@{
        id       = $script:SingleRid
        name     = 'srv1'
        location = 'East US'
        sku      = [PSCustomObject]@{
            name     = 'B_Gen5_1'
            tier     = 'Basic'
            capacity = 1
        }
        properties = [PSCustomObject]@{
            userVisibleState         = 'Ready'
            version                  = '9.6'
            fullyQualifiedDomainName = 'srv1.postgres.database.azure.com'
            administratorLogin       = 'pgadmin'
            storageProfile           = [PSCustomObject]@{
                storageMB           = 5120
                storageAutogrow     = 'Enabled'
                backupRetentionDays = 7
                geoRedundantBackup  = 'Disabled'
            }
        }
    }

    # ── Canned single-server configurations response ────────────────────────────
    $script:MockSingleConfigsResp = [PSCustomObject]@{
        value = @(
            [PSCustomObject]@{
                name       = 'max_connections'
                properties = [PSCustomObject]@{
                    value          = '50'
                    defaultValue   = '50'
                    source         = 'system-default'
                    isDynamicConfig = $true
                    isReadOnly     = $false
                    unit           = $null
                    description    = 'Maximum connections'
                }
            }
        )
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }

# ─── Get-AzureResourceId ──────────────────────────────────────────────────────

Describe 'Get-AzureResourceId' {

    It 'postgres-flexible id matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; server_name = 'srv1' }
        $rid = Get-AzureResourceId -Service 'postgres-flexible' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/flexibleServers/srv1'
    }

    It 'mysql-flexible id matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; server_name = 'srv1' }
        $rid = Get-AzureResourceId -Service 'mysql-flexible' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.DBforMySQL/flexibleServers/srv1'
    }

    It 'cosmos-postgres id matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; cluster_name = 'cls1' }
        $rid = Get-AzureResourceId -Service 'cosmos-postgres' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/serverGroupsv2/cls1'
    }

    It 'sql-database id matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; server_name = 'srv1'; database = 'db1' }
        $rid = Get-AzureResourceId -Service 'sql-database' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.Sql/servers/srv1/databases/db1'
    }

    It 'sql-managed-instance id matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; instance_name = 'mi1' }
        $rid = Get-AzureResourceId -Service 'sql-managed-instance' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.Sql/managedInstances/mi1'
    }

    It 'single-server with postgresql engine matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; server_name = 'srv1'; sub_engine = 'postgresql' }
        $rid = Get-AzureResourceId -Service 'single-server' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.DBforPostgreSQL/servers/srv1'
    }

    It 'single-server with mysql engine matches Python azure_resource_id output' {
        $p   = @{ resource_group = 'rg1'; server_name = 'srv1'; sub_engine = 'mysql' }
        $rid = Get-AzureResourceId -Service 'single-server' -SubscriptionId 'sub123' -Params $p
        $rid | Should -Be '/subscriptions/sub123/resourceGroups/rg1/providers/Microsoft.DBforMySQL/servers/srv1'
    }

    It 'throws on unknown service' {
        $p = @{ resource_group = 'rg1' }
        { Get-AzureResourceId -Service 'invalid-service' -SubscriptionId 'sub123' -Params $p } | Should -Throw
    }
}

# ─── ConvertTo-ConfigurationDict ─────────────────────────────────────────────

Describe 'ConvertTo-ConfigurationDict' {

    It 'maps all fields correctly' {
        $config = [PSCustomObject]@{
            name = 'max_connections'
            properties = [PSCustomObject]@{
                value          = '200'
                defaultValue   = '100'
                source         = 'user-override'
                isDynamicConfig = $true
                isReadOnly     = $false
                unit           = $null
                description    = 'Max connections'
            }
        }
        $d = ConvertTo-ConfigurationDict $config
        $d.name              | Should -Be 'max_connections'
        $d.value             | Should -Be '200'
        $d.default_value     | Should -Be '100'
        $d.source            | Should -Be 'user-override'
        $d.is_dynamic_config | Should -Be $true
        $d.is_read_only      | Should -Be $false
        $d.is_non_default    | Should -Be $true
        $d.unit              | Should -BeNullOrEmpty
        $d.description       | Should -Be 'Max connections'
    }

    It 'sets is_non_default true when value differs from default_value' {
        $config = [PSCustomObject]@{
            name = 'max_connections'
            properties = [PSCustomObject]@{
                value = '200'; defaultValue = '100'; source = 'user-override'
                isDynamicConfig = $true; isReadOnly = $false; unit = $null; description = ''
            }
        }
        (ConvertTo-ConfigurationDict $config).is_non_default | Should -Be $true
    }

    It 'sets is_non_default false when value equals default_value' {
        $config = [PSCustomObject]@{
            name = 'work_mem'
            properties = [PSCustomObject]@{
                value = '4096'; defaultValue = '4096'; source = 'system-default'
                isDynamicConfig = $true; isReadOnly = $false; unit = 'kB'; description = ''
            }
        }
        (ConvertTo-ConfigurationDict $config).is_non_default | Should -Be $false
    }

    It 'sets is_non_default false when value is null (even if default differs)' {
        $config = [PSCustomObject]@{
            name = 'test_param'
            properties = [PSCustomObject]@{
                value = $null; defaultValue = '100'; source = 'system-default'
                isDynamicConfig = $true; isReadOnly = $false; unit = $null; description = ''
            }
        }
        (ConvertTo-ConfigurationDict $config).is_non_default | Should -Be $false
    }

    It 'sets is_non_default false when default_value is null (even if value differs)' {
        $config = [PSCustomObject]@{
            name = 'test_param'
            properties = [PSCustomObject]@{
                value = '200'; defaultValue = $null; source = 'system-default'
                isDynamicConfig = $true; isReadOnly = $false; unit = $null; description = ''
            }
        }
        (ConvertTo-ConfigurationDict $config).is_non_default | Should -Be $false
    }
}

# ─── ConvertTo-ServerDict ────────────────────────────────────────────────────

Describe 'ConvertTo-ServerDict' {

    It 'returns $null for every sub-object when sku/storage/ha/backup/network/maintenance_window are absent' {
        # A stripped ARM response that omits all optional sub-objects.
        # Accessing a missing property on a PSCustomObject returns $null in PowerShell,
        # so the if($null -ne $x){…}else{$null} guards must produce $null for each field.
        $stripped = [PSCustomObject]@{
            id       = '/subscriptions/s/resourceGroups/rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/srv'
            name     = 'srv'
            location = 'East US 2'
            sku      = $null        # top-level sku explicitly null
            properties = [PSCustomObject]@{
                state                    = 'Ready'
                version                  = '17'
                minorVersion             = $null
                fullyQualifiedDomainName = 'srv.postgres.database.azure.com'
                administratorLogin       = 'pgadmin'
                availabilityZone         = '1'
                # storage, highAvailability, backup, network, maintenanceWindow are absent
            }
        }

        $s = ConvertTo-ServerDict $stripped

        $s.sku               | Should -BeNullOrEmpty
        $s.storage           | Should -BeNullOrEmpty
        $s.high_availability | Should -BeNullOrEmpty
        $s.backup            | Should -BeNullOrEmpty
        $s.network           | Should -BeNullOrEmpty
        $s.maintenance_window | Should -BeNullOrEmpty

        # Scalar fields should still be mapped
        $s.state   | Should -Be 'Ready'
        $s.version | Should -Be '17'
    }
}

# ─── Get-FlexibleInventory ────────────────────────────────────────────────────

Describe 'Get-FlexibleInventory' {

    It 'returns all required top-level keys' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        $inv.Keys | Should -Contain 'resource_id'
        $inv.Keys | Should -Contain 'server'
        $inv.Keys | Should -Contain 'parameters'
        $inv.Keys | Should -Contain 'parameters_non_default'
        $inv.Keys | Should -Contain 'databases'
    }

    It 'sets resource_id to the server ARM id from the response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        $inv.resource_id | Should -Be $script:FlexRid
    }

    It 'maps all server fields from the ARM response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token
        $s = $inv.server

        $s.id                          | Should -Be $script:FlexRid
        $s.name                        | Should -Be 'srv1'
        $s.location                    | Should -Be 'East US 2'
        $s.state                       | Should -Be 'Ready'
        $s.version                     | Should -Be '17'
        $s.minor_version               | Should -Be '11'
        $s.fully_qualified_domain_name | Should -Be 'srv1.postgres.database.azure.com'
        $s.administrator_login         | Should -Be 'pgadmin'
        $s.availability_zone           | Should -Be '1'

        # sku
        $s.sku.name | Should -Be 'Standard_B2s'
        $s.sku.tier | Should -Be 'Burstable'

        # storage
        $s.storage.size_gb         | Should -Be 32
        $s.storage.tier            | Should -Be 'P4'
        $s.storage.iops            | Should -Be 120
        $s.storage.auto_grow       | Should -Be 'Disabled'
        $s.storage.auto_io_scaling | Should -Be 'Enabled'
        $s.storage.type            | Should -Be 'Premium_LRS'

        # high_availability
        $s.high_availability.mode                      | Should -Be 'Disabled'
        $s.high_availability.state                     | Should -Be 'NotEnabled'
        $s.high_availability.standby_availability_zone | Should -BeNullOrEmpty

        # backup
        $s.backup.retention_days       | Should -Be 8
        $s.backup.geo_redundant_backup | Should -Be 'Disabled'
        $s.backup.earliest_restore_date | Should -Not -BeNullOrEmpty

        # network
        $s.network.public_network_access          | Should -Be 'Enabled'
        $s.network.delegated_subnet_resource_id   | Should -BeNullOrEmpty
        $s.network.private_dns_zone_resource_id   | Should -BeNullOrEmpty

        # maintenance_window
        $s.maintenance_window.custom_window | Should -Be 'Disabled'
        $s.maintenance_window.day_of_week   | Should -Be 0
        $s.maintenance_window.start_hour    | Should -Be 0
        $s.maintenance_window.start_minute  | Should -Be 0
    }

    It 'maps is_non_default: true only when value differs from default_value (both non-null)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        $maxConn = $inv.parameters | Where-Object { $_.name -eq 'max_connections' }
        $workMem = $inv.parameters | Where-Object { $_.name -eq 'work_mem' }
        $maxConn.is_non_default | Should -Be $true    # 200 != 100
        $workMem.is_non_default | Should -Be $false   # 4096 == 4096
    }

    It 'parameters_non_default contains only the non-default parameters' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        $inv.parameters_non_default.Count         | Should -Be 1
        $inv.parameters_non_default[0].name        | Should -Be 'max_connections'
    }

    It 'parameters stays an array even when only one configuration is returned' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockOneConfigResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        # @() wrapper must prevent unwrapping to scalar
        $inv.parameters.GetType().IsArray | Should -Be $true
        # Passing array directly to ConvertTo-Json (not via pipe) must produce a JSON array
        # (piping would unwrap the single element — hence we use the non-pipe form)
        (ConvertTo-Json $inv.parameters -Depth 1 -Compress).TrimStart() | Should -Match '^\['
    }

    It 'databases is an array of database name strings' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        $inv.databases | Should -Contain 'postgres'
        $inv.databases | Should -Contain 'myapp'
    }

    It 'sets databases to an error object when the databases GET throws' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { throw 'databases listing denied' }

        $inv = Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        # databases key is present but is an error object, not an array
        $inv.Keys | Should -Contain 'databases'
        $inv.databases.ContainsKey('error') | Should -Be $true
        $inv.databases.error                | Should -Not -BeNullOrEmpty
    }

    It 'uses api-version 2022-12-01 for PostgreSQL flexible namespace' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        Get-FlexibleInventory -ResourceId $script:FlexRid `
            -SubEngineNamespace 'Microsoft.DBforPostgreSQL/flexibleServers' `
            -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*2022-12-01*' }
    }

    It 'uses api-version 2023-06-30 for MySQL flexible namespace' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' -and $Uri -notlike '*/databases*' } `
            { $script:MockServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockConfigsResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/databases*' } `
            { $script:MockDatabasesResp }

        Get-FlexibleInventory -ResourceId $script:MySQLRid `
            -SubEngineNamespace 'Microsoft.DBforMySQL/flexibleServers' `
            -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*2023-06-30*' }
    }
}

# ─── Get-SingleServerInventory ────────────────────────────────────────────────

Describe 'Get-SingleServerInventory' {

    It 'returns resource_id, server, parameters, parameters_non_default — no databases key' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        $inv = Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token

        $inv.Keys | Should -Contain 'resource_id'
        $inv.Keys | Should -Contain 'server'
        $inv.Keys | Should -Contain 'parameters'
        $inv.Keys | Should -Contain 'parameters_non_default'
        $inv.Keys | Should -Not -Contain 'databases'
    }

    It 'maps state from properties.userVisibleState (not properties.state)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        $inv = Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token
        $inv.server.state | Should -Be 'Ready'
    }

    It 'maps storage fields from properties.storageProfile' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        $inv = Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token
        $s   = $inv.server

        $s.storage.storage_mb            | Should -Be 5120
        $s.storage.auto_grow             | Should -Be 'Enabled'
        $s.storage.backup_retention_days | Should -Be 7
        $s.storage.geo_redundant_backup  | Should -Be 'Disabled'
    }

    It 'maps sku including capacity field' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        $inv = Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token

        $inv.server.sku.name     | Should -Be 'B_Gen5_1'
        $inv.server.sku.tier     | Should -Be 'Basic'
        $inv.server.sku.capacity | Should -Be 1
    }

    It 'maps identity fields (id, name, location, version, fqdn, admin_login)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        $inv = Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token
        $s   = $inv.server

        $s.id                          | Should -Be $script:SingleRid
        $s.name                        | Should -Be 'srv1'
        $s.location                    | Should -Be 'East US'
        $s.version                     | Should -Be '9.6'
        $s.fully_qualified_domain_name | Should -Be 'srv1.postgres.database.azure.com'
        $s.administrator_login         | Should -Be 'pgadmin'
    }

    It 'sets resource_id to the server id from the ARM response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        $inv = Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token
        $inv.resource_id | Should -Be $script:SingleRid
    }

    It 'uses api-version 2017-12-01 for all calls' {
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -notlike '*/configurations*' } `
            { $script:MockSingleServerResp }
        Mock -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*/configurations*' } `
            { $script:MockSingleConfigsResp }

        Get-SingleServerInventory -ResourceId $script:SingleRid -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*2017-12-01*' }
    }
}

# ─── Get-CosmosPostgresInventory ─────────────────────────────────────────────

Describe 'Get-CosmosPostgresInventory' {

    BeforeAll {
        $script:CosmosRid = "/subscriptions/$($script:Sub)/resourceGroups/$($script:Rg)/providers/Microsoft.DBforPostgreSQL/serverGroupsv2/cls1"

        $script:MockCosmosResp = [PSCustomObject]@{
            id       = $script:CosmosRid
            name     = 'cls1'
            location = 'West Europe'
            properties = [PSCustomObject]@{
                state                         = 'Ready'
                postgresqlVersion             = '15'
                citusVersion                  = '12.1'
                enableHa                      = $true
                coordinatorStorageQuotaInMb   = 524288
                coordinatorVCores             = 4
                nodeCount                     = 2
                nodeVCores                    = 4
                nodeStorageQuotaInMb          = 524288
            }
        }
    }

    It 'maps all server fields from the ARM cluster response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCosmosResp }

        $inv = Get-CosmosPostgresInventory -ResourceId $script:CosmosRid -Token $script:Token
        $s   = $inv.server

        $s.id                              | Should -Be $script:CosmosRid
        $s.name                            | Should -Be 'cls1'
        $s.location                        | Should -Be 'West Europe'
        $s.state                           | Should -Be 'Ready'
        $s.postgresql_version              | Should -Be '15'
        $s.citus_version                   | Should -Be '12.1'
        $s.enable_ha                       | Should -Be $true
        $s.coordinator_storage_quota_in_mb | Should -Be 524288
        $s.coordinator_v_cores             | Should -Be 4
        $s.node_count                      | Should -Be 2
        $s.node_v_cores                    | Should -Be 4
        $s.node_storage_quota_in_mb        | Should -Be 524288
    }

    It 'parameters is an empty array (not $null, not scalar)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCosmosResp }

        $inv = Get-CosmosPostgresInventory -ResourceId $script:CosmosRid -Token $script:Token

        # @() is not $null even though it is empty — verify it's an actual array object
        $null -eq $inv.parameters         | Should -Be $false
        $inv.parameters.Count             | Should -Be 0
        $inv.parameters.GetType().IsArray | Should -Be $true
    }

    It 'parameters_non_default is an empty array' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCosmosResp }

        $inv = Get-CosmosPostgresInventory -ResourceId $script:CosmosRid -Token $script:Token

        $inv.parameters_non_default.Count        | Should -Be 0
        $inv.parameters_non_default.GetType().IsArray | Should -Be $true
    }

    It 'has no databases key' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCosmosResp }

        $inv = Get-CosmosPostgresInventory -ResourceId $script:CosmosRid -Token $script:Token

        $inv.Keys -notcontains 'databases' | Should -Be $true
    }

    It 'resource_id is $null (caller is expected to override)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCosmosResp }

        $inv = Get-CosmosPostgresInventory -ResourceId $script:CosmosRid -Token $script:Token

        $inv.resource_id | Should -BeNullOrEmpty
    }

    It 'uses api-version 2022-11-08' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockCosmosResp }

        Get-CosmosPostgresInventory -ResourceId $script:CosmosRid -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*2022-11-08*' }
    }
}

# ─── Get-SqlDatabaseInventory ─────────────────────────────────────────────────

Describe 'Get-SqlDatabaseInventory' {

    BeforeAll {
        $script:SqlDbRid = "/subscriptions/$($script:Sub)/resourceGroups/$($script:Rg)/providers/Microsoft.Sql/servers/sqlsrv1/databases/db1"

        $script:MockSqlDbResp = [PSCustomObject]@{
            id       = $script:SqlDbRid
            name     = 'db1'
            location = 'East US'
            sku      = [PSCustomObject]@{
                name     = 'Standard'
                tier     = 'Standard'
                capacity = 100
            }
            properties = [PSCustomObject]@{
                status                       = 'Online'
                maxSizeBytes                 = 268435456000
                currentServiceObjectiveName  = 'S1'
            }
        }

        $script:MockSqlDbNoSkuResp = [PSCustomObject]@{
            id       = $script:SqlDbRid
            name     = 'db1'
            location = 'East US'
            sku      = $null
            properties = [PSCustomObject]@{
                status                       = 'Online'
                maxSizeBytes                 = 268435456000
                currentServiceObjectiveName  = 'S1'
            }
        }
    }

    It 'maps all server fields from the ARM database response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token
        $s   = $inv.server

        $s.id                             | Should -Be $script:SqlDbRid
        $s.name                           | Should -Be 'db1'
        $s.location                       | Should -Be 'East US'
        $s.status                         | Should -Be 'Online'
        $s.max_size_bytes                 | Should -Be 268435456000
        $s.current_service_objective_name | Should -Be 'S1'
    }

    It 'maps sku sub-object (name, tier, capacity)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        $inv.server.sku          | Should -Not -BeNullOrEmpty
        $inv.server.sku.name     | Should -Be 'Standard'
        $inv.server.sku.tier     | Should -Be 'Standard'
        $inv.server.sku.capacity | Should -Be 100
    }

    It 'sets sku to $null when absent from the ARM response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbNoSkuResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        $inv.server.sku | Should -BeNullOrEmpty
    }

    It 'parameters is an empty array (not $null, not scalar)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        $inv.parameters.Count       | Should -Be 0
        $inv.parameters.GetType().IsArray | Should -Be $true
    }

    It 'parameters_non_default is an empty array' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        $inv.parameters_non_default.Count        | Should -Be 0
        $inv.parameters_non_default.GetType().IsArray | Should -Be $true
    }

    It 'has no databases key' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        $inv.Keys -notcontains 'databases' | Should -Be $true
    }

    It 'resource_id is $null (caller is expected to override)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        $inv = Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        $inv.resource_id | Should -BeNullOrEmpty
    }

    It 'uses api-version 2021-11-01' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlDbResp }

        Get-SqlDatabaseInventory -ResourceId $script:SqlDbRid -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*2021-11-01*' }
    }
}

# ─── Get-SqlManagedInstanceInventory ──────────────────────────────────────────

Describe 'Get-SqlManagedInstanceInventory' {

    BeforeAll {
        $script:SqlMiRid = "/subscriptions/$($script:Sub)/resourceGroups/$($script:Rg)/providers/Microsoft.Sql/managedInstances/mi1"

        $script:MockSqlMiResp = [PSCustomObject]@{
            id       = $script:SqlMiRid
            name     = 'mi1'
            location = 'North Europe'
            sku      = [PSCustomObject]@{
                name = 'GP_Gen5'
                tier = 'GeneralPurpose'
            }
            properties = [PSCustomObject]@{
                state           = 'Ready'
                vCores          = 8
                storageSizeInGB = 256
            }
        }

        $script:MockSqlMiNoSkuResp = [PSCustomObject]@{
            id       = $script:SqlMiRid
            name     = 'mi1'
            location = 'North Europe'
            sku      = $null
            properties = [PSCustomObject]@{
                state           = 'Ready'
                vCores          = 8
                storageSizeInGB = 256
            }
        }
    }

    It 'maps all server fields from the ARM managed-instance response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token
        $s   = $inv.server

        $s.id                 | Should -Be $script:SqlMiRid
        $s.name               | Should -Be 'mi1'
        $s.location           | Should -Be 'North Europe'
        $s.state              | Should -Be 'Ready'
        $s.v_cores            | Should -Be 8
        $s.storage_size_in_gb | Should -Be 256
    }

    It 'maps sku sub-object (name, tier)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        $inv.server.sku      | Should -Not -BeNullOrEmpty
        $inv.server.sku.name | Should -Be 'GP_Gen5'
        $inv.server.sku.tier | Should -Be 'GeneralPurpose'
    }

    It 'sets sku to $null when absent from the ARM response' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiNoSkuResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        $inv.server.sku | Should -BeNullOrEmpty
    }

    It 'parameters is an empty array (not $null, not scalar)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        $inv.parameters.Count       | Should -Be 0
        $inv.parameters.GetType().IsArray | Should -Be $true
    }

    It 'parameters_non_default is an empty array' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        $inv.parameters_non_default.Count        | Should -Be 0
        $inv.parameters_non_default.GetType().IsArray | Should -Be $true
    }

    It 'has no databases key' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        $inv.Keys -notcontains 'databases' | Should -Be $true
    }

    It 'resource_id is $null (caller is expected to override)' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        $inv = Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        $inv.resource_id | Should -BeNullOrEmpty
    }

    It 'uses api-version 2021-11-01' {
        Mock -ModuleName DbMetrics Invoke-AzureRest { $script:MockSqlMiResp }

        Get-SqlManagedInstanceInventory -ResourceId $script:SqlMiRid -Token $script:Token

        Should -Invoke -ModuleName DbMetrics Invoke-AzureRest `
            -ParameterFilter { $Uri -like '*2021-11-01*' }
    }
}
