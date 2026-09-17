# AzureInventory.ps1
# Port of db_metrics/providers/azure/inventory.py
# Task 6: flexible + single-server + resource-id
# Task 7: cosmos-postgres, sql-database, sql-managed-instance

# ── API-version constants ──────────────────────────────────────────────────────
Set-Variable -Name AzInvFlexPGApiVersion    -Value '2022-12-01'  -Scope Script -Option Constant -ErrorAction SilentlyContinue
Set-Variable -Name AzInvFlexMySQLApiVersion -Value '2023-06-30'  -Scope Script -Option Constant -ErrorAction SilentlyContinue
Set-Variable -Name AzInvSingleServerApiVer  -Value '2017-12-01'  -Scope Script -Option Constant -ErrorAction SilentlyContinue
Set-Variable -Name AzInvCosmosPostgresApiVer -Value '2022-11-08' -Scope Script -Option Constant -ErrorAction SilentlyContinue
Set-Variable -Name AzInvSqlApiVersion       -Value '2021-11-01'  -Scope Script -Option Constant -ErrorAction SilentlyContinue

# ── Get-AzureResourceId ────────────────────────────────────────────────────────

function Get-AzureResourceId {
    <#
    .SYNOPSIS
    Build the ARM resource id for a given Azure DB service target.

    .DESCRIPTION
    Port of inventory.py:azure_resource_id.  Produces strings identical to the
    Python implementation for all six supported services.

    Supported services:
      postgres-flexible    — Microsoft.DBforPostgreSQL/flexibleServers
      mysql-flexible       — Microsoft.DBforMySQL/flexibleServers
      cosmos-postgres      — Microsoft.DBforPostgreSQL/serverGroupsv2
      sql-database         — Microsoft.Sql/servers/{s}/databases/{db}
      sql-managed-instance — Microsoft.Sql/managedInstances
      single-server        — Microsoft.DBforPostgreSQL|DBforMySQL/servers (sub_engine)

    Throws on unknown service.
    #>
    [OutputType([string])]
    param(
        [Parameter(Mandatory)][string]   $Service,
        [Parameter(Mandatory)][string]   $SubscriptionId,
        [Parameter(Mandatory)][hashtable]$Params
    )

    $sub = $SubscriptionId
    $rg  = $Params['resource_group']

    switch ($Service) {
        'postgres-flexible' {
            return "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.DBforPostgreSQL/flexibleServers/$($Params['server_name'])"
        }
        'mysql-flexible' {
            return "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.DBforMySQL/flexibleServers/$($Params['server_name'])"
        }
        'cosmos-postgres' {
            return "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.DBforPostgreSQL/serverGroupsv2/$($Params['cluster_name'])"
        }
        'sql-database' {
            return "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.Sql/servers/$($Params['server_name'])/databases/$($Params['database'])"
        }
        'sql-managed-instance' {
            return "/subscriptions/$sub/resourceGroups/$rg/providers/Microsoft.Sql/managedInstances/$($Params['instance_name'])"
        }
        'single-server' {
            $engine = $Params['sub_engine']
            $ns = if ($engine -eq 'postgresql') { 'Microsoft.DBforPostgreSQL' } else { 'Microsoft.DBforMySQL' }
            return "/subscriptions/$sub/resourceGroups/$rg/providers/$ns/servers/$($Params['server_name'])"
        }
        default {
            throw "Get-AzureResourceId: unknown service '$Service'"
        }
    }
}

# ── ConvertTo-ServerDict ───────────────────────────────────────────────────────

function ConvertTo-ServerDict {
    <#
    .SYNOPSIS
    Flatten a flexible-server ARM GET response into the canonical server dict.

    .DESCRIPTION
    Port of inventory.py:server_to_dict.  Maps from the ARM JSON property bag
    (camelCase) to the snake_case output keys defined in the field-mapping table.
    Sub-objects (sku, storage, high_availability, backup, network,
    maintenance_window) are $null when absent from the response, mirroring
    Python's "if sku else None" guards.
    #>
    param([Parameter(Mandatory)]$Server)

    $sku     = $Server.sku
    $storage = $Server.properties.storage
    $ha      = $Server.properties.highAvailability
    $backup  = $Server.properties.backup
    $network = $Server.properties.network
    $maint   = $Server.properties.maintenanceWindow

    [ordered]@{
        id                          = $Server.id
        name                        = $Server.name
        location                    = $Server.location
        state                       = $Server.properties.state
        version                     = $Server.properties.version
        minor_version               = $Server.properties.minorVersion
        fully_qualified_domain_name = $Server.properties.fullyQualifiedDomainName
        administrator_login         = $Server.properties.administratorLogin
        availability_zone           = $Server.properties.availabilityZone
        sku                         = if ($null -ne $sku) {
            [ordered]@{
                name = $sku.name
                tier = $sku.tier
            }
        } else { $null }
        storage                     = if ($null -ne $storage) {
            [ordered]@{
                size_gb         = $storage.storageSizeGB
                tier            = $storage.tier
                iops            = $storage.iops
                auto_grow       = $storage.autoGrow
                auto_io_scaling = $storage.autoIoScaling
                type            = $storage.type
            }
        } else { $null }
        high_availability           = if ($null -ne $ha) {
            [ordered]@{
                mode                      = $ha.mode
                state                     = $ha.state
                standby_availability_zone = $ha.standbyAvailabilityZone
            }
        } else { $null }
        backup                      = if ($null -ne $backup) {
            [ordered]@{
                retention_days         = $backup.backupRetentionDays
                geo_redundant_backup   = $backup.geoRedundantBackup
                earliest_restore_date  = $backup.earliestRestoreDate
            }
        } else { $null }
        network                     = if ($null -ne $network) {
            [ordered]@{
                public_network_access          = $network.publicNetworkAccess
                delegated_subnet_resource_id   = $network.delegatedSubnetResourceId
                private_dns_zone_resource_id   = $network.privateDnsZoneArmResourceId
            }
        } else { $null }
        maintenance_window          = if ($null -ne $maint) {
            [ordered]@{
                custom_window = $maint.customWindow
                day_of_week   = $maint.dayOfWeek
                start_hour    = $maint.startHour
                start_minute  = $maint.startMinute
            }
        } else { $null }
    }
}

# ── ConvertTo-ConfigurationDict ───────────────────────────────────────────────

function ConvertTo-ConfigurationDict {
    <#
    .SYNOPSIS
    Flatten a server-parameter (Configuration) ARM response item into a dict.

    .DESCRIPTION
    Port of inventory.py:configuration_to_dict.

    is_non_default = true only when BOTH value and default_value are non-null
    AND they differ — matches Python's
        value is not None and default is not None and value != default
    #>
    param([Parameter(Mandatory)]$Config)

    $value   = $Config.properties.value
    $default = $Config.properties.defaultValue

    [ordered]@{
        name              = $Config.name
        value             = $value
        default_value     = $default
        source            = $Config.properties.source
        is_dynamic_config = $Config.properties.isDynamicConfig
        is_read_only      = $Config.properties.isReadOnly
        is_non_default    = ($null -ne $value -and $null -ne $default -and $value -ne $default)
        unit              = $Config.properties.unit
        description       = $Config.properties.description
    }
}

# ── Get-FlexibleInventory ──────────────────────────────────────────────────────

function Get-FlexibleInventory {
    <#
    .SYNOPSIS
    Collect ARM inventory for a PostgreSQL or MySQL Flexible Server.

    .DESCRIPTION
    Port of inventory.py:collect_inventory for the ARM REST path.

    Makes three ARM GET calls:
      1. Server:         GET {ResourceId}?api-version=<ver>
      2. Configurations: GET {ResourceId}/configurations?api-version=<ver>
      3. Databases:      GET {ResourceId}/databases?api-version=<ver>
         → on failure: databases = @{ error = <message> }  (mirrors Python)

    API versions:
      PostgreSQL flexible: 2022-12-01
      MySQL flexible:      2023-06-30  (determined from SubEngineNamespace)

    Returns [ordered]@{
        resource_id            (= server.id)
        server                 (ConvertTo-ServerDict)
        parameters             (array of ConvertTo-ConfigurationDict results)
        parameters_non_default (filtered subset where is_non_default)
        databases              (array of name strings, or @{ error = ... })
    }

    ARRAY SAFETY: parameters and databases are wrapped with @(...) so a
    single-element result is never silently unwrapped to a scalar.
    #>
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][string]$SubEngineNamespace,
        [Parameter(Mandatory)][string]$Token
    )

    # Choose api-version from the namespace string
    $apiVersion = if ($SubEngineNamespace -like '*PostgreSQL*') {
        $script:AzInvFlexPGApiVersion
    } else {
        $script:AzInvFlexMySQLApiVersion
    }

    # 1. Server
    $serverUri  = "https://management.azure.com${ResourceId}?api-version=${apiVersion}"
    $serverData = Invoke-AzureRest -Uri $serverUri -Token $Token
    $server     = ConvertTo-ServerDict $serverData

    # 2. Configurations — @() forces array even for a single item
    $configUri  = "https://management.azure.com${ResourceId}/configurations?api-version=${apiVersion}"
    $configResp = Invoke-AzureRest -Uri $configUri -Token $Token
    $parameters = @($configResp.value | ForEach-Object { ConvertTo-ConfigurationDict $_ })

    # 3. Databases — failure becomes an error object (mirrors Python's except block)
    $databases = $null
    try {
        $dbUri     = "https://management.azure.com${ResourceId}/databases?api-version=${apiVersion}"
        $dbResp    = Invoke-AzureRest -Uri $dbUri -Token $Token
        $databases = @($dbResp.value | ForEach-Object { $_.name })
    } catch {
        $databases = @{ error = $_.Exception.Message }
    }

    [ordered]@{
        resource_id            = $server.id
        server                 = $server
        parameters             = $parameters
        parameters_non_default = @($parameters | Where-Object { $_.is_non_default })
        databases              = $databases
    }
}

# ── Get-SingleServerInventory ─────────────────────────────────────────────────

function Get-SingleServerInventory {
    <#
    .SYNOPSIS
    Collect ARM inventory for an Azure Database for PostgreSQL/MySQL single server.

    .DESCRIPTION
    Port of inventory.py:_single_server_to_dict + _collect_single_server.

    Makes two ARM GET calls (api-version 2017-12-01):
      1. Server:         GET {ResourceId}?api-version=2017-12-01
      2. Configurations: GET {ResourceId}/configurations?api-version=2017-12-01

    No databases call is made (Python's _collect_single_server has no databases
    key — single-server lacks the databases list endpoint).

    Returns [ordered]@{
        resource_id            (= server.id)
        server{id,name,location,state←userVisibleState,version,
               fully_qualified_domain_name,administrator_login,
               sku{name,tier,capacity},
               storage{storage_mb,auto_grow,backup_retention_days,geo_redundant_backup}}
        parameters
        parameters_non_default
    }
    #>
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][string]$Token
    )

    $apiVersion = $script:AzInvSingleServerApiVer

    # 1. Server
    $serverUri  = "https://management.azure.com${ResourceId}?api-version=${apiVersion}"
    $serverData = Invoke-AzureRest -Uri $serverUri -Token $Token

    $sku     = $serverData.sku
    $storage = $serverData.properties.storageProfile

    $server = [ordered]@{
        id                          = $serverData.id
        name                        = $serverData.name
        location                    = $serverData.location
        state                       = $serverData.properties.userVisibleState
        version                     = $serverData.properties.version
        fully_qualified_domain_name = $serverData.properties.fullyQualifiedDomainName
        administrator_login         = $serverData.properties.administratorLogin
        sku                         = if ($null -ne $sku) {
            [ordered]@{
                name     = $sku.name
                tier     = $sku.tier
                capacity = $sku.capacity
            }
        } else { $null }
        storage                     = if ($null -ne $storage) {
            [ordered]@{
                storage_mb            = $storage.storageMB
                auto_grow             = $storage.storageAutogrow
                backup_retention_days = $storage.backupRetentionDays
                geo_redundant_backup  = $storage.geoRedundantBackup
            }
        } else { $null }
    }

    # 2. Configurations — @() forces array even for a single item
    $configUri  = "https://management.azure.com${ResourceId}/configurations?api-version=${apiVersion}"
    $configResp = Invoke-AzureRest -Uri $configUri -Token $Token
    $parameters = @($configResp.value | ForEach-Object { ConvertTo-ConfigurationDict $_ })

    [ordered]@{
        resource_id            = $server.id
        server                 = $server
        parameters             = $parameters
        parameters_non_default = @($parameters | Where-Object { $_.is_non_default })
    }
}

# ── Get-CosmosPostgresInventory ───────────────────────────────────────────────

function Get-CosmosPostgresInventory {
    <#
    .SYNOPSIS
    Collect ARM inventory for a Cosmos DB for PostgreSQL cluster.

    .DESCRIPTION
    Port of inventory.py:_collect_cosmos_postgres.

    Makes a single ARM GET call (api-version 2022-11-08):
      GET {ResourceId}?api-version=2022-11-08

    Server fields mapped from the ARM cluster response:
      id, name, location, state,
      postgresql_version  ← .properties.postgresqlVersion
      citus_version       ← .properties.citusVersion
      enable_ha           ← .properties.enableHa
      coordinator_storage_quota_in_mb ← .properties.coordinatorStorageQuotaInMb
      coordinator_v_cores ← .properties.coordinatorVCores
      node_count          ← .properties.nodeCount
      node_v_cores        ← .properties.nodeVCores
      node_storage_quota_in_mb ← .properties.nodeStorageQuotaInMb

    Returns [ordered]@{
        resource_id  = $null  (caller overrides with Get-AzureResourceId)
        server       (fields above)
        parameters             = @()
        parameters_non_default = @()
    }

    NOTE: No 'databases' key — cosmos-postgres has no databases list,
    matching Python's _collect_cosmos_postgres which omits the key.
    #>
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][string]$Token
    )

    $apiVersion = $script:AzInvCosmosPostgresApiVer
    $uri        = "https://management.azure.com${ResourceId}?api-version=${apiVersion}"
    $cluster    = Invoke-AzureRest -Uri $uri -Token $Token

    $server = [ordered]@{
        id                              = $cluster.id
        name                            = $cluster.name
        location                        = $cluster.location
        state                           = $cluster.properties.state
        postgresql_version              = $cluster.properties.postgresqlVersion
        citus_version                   = $cluster.properties.citusVersion
        enable_ha                       = $cluster.properties.enableHa
        coordinator_storage_quota_in_mb = $cluster.properties.coordinatorStorageQuotaInMb
        coordinator_v_cores             = $cluster.properties.coordinatorVCores
        node_count                      = $cluster.properties.nodeCount
        node_v_cores                    = $cluster.properties.nodeVCores
        node_storage_quota_in_mb        = $cluster.properties.nodeStorageQuotaInMb
    }

    [ordered]@{
        resource_id            = $null
        server                 = $server
        parameters             = @()
        parameters_non_default = @()
    }
}

# ── Get-SqlDatabaseInventory ──────────────────────────────────────────────────

function Get-SqlDatabaseInventory {
    <#
    .SYNOPSIS
    Collect ARM inventory for an Azure SQL Database.

    .DESCRIPTION
    Port of inventory.py:_collect_sql_database.

    Makes a single ARM GET call (api-version 2021-11-01):
      GET {ResourceId}?api-version=2021-11-01

    Server fields mapped from the ARM database response:
      id, name, location,
      status                       ← .properties.status
      max_size_bytes               ← .properties.maxSizeBytes
      current_service_objective_name ← .properties.currentServiceObjectiveName
      sku{ name, tier, capacity }  (or $null if .sku is absent)

    Returns [ordered]@{
        resource_id  = $null  (caller overrides with Get-AzureResourceId)
        server       (fields above)
        parameters             = @()
        parameters_non_default = @()
    }

    NOTE: No 'databases' key — sql-database has no sub-databases list,
    matching Python's _collect_sql_database which omits the key.
    #>
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][string]$Token
    )

    $apiVersion = $script:AzInvSqlApiVersion
    $uri        = "https://management.azure.com${ResourceId}?api-version=${apiVersion}"
    $db         = Invoke-AzureRest -Uri $uri -Token $Token

    $sku = $db.sku

    $server = [ordered]@{
        id                             = $db.id
        name                           = $db.name
        location                       = $db.location
        status                         = $db.properties.status
        max_size_bytes                 = $db.properties.maxSizeBytes
        current_service_objective_name = $db.properties.currentServiceObjectiveName
        sku                            = if ($null -ne $sku) {
            [ordered]@{
                name     = $sku.name
                tier     = $sku.tier
                capacity = $sku.capacity
            }
        } else { $null }
    }

    [ordered]@{
        resource_id            = $null
        server                 = $server
        parameters             = @()
        parameters_non_default = @()
    }
}

# ── Get-SqlManagedInstanceInventory ──────────────────────────────────────────

function Get-SqlManagedInstanceInventory {
    <#
    .SYNOPSIS
    Collect ARM inventory for an Azure SQL Managed Instance.

    .DESCRIPTION
    Port of inventory.py:_collect_sql_managed_instance.

    Makes a single ARM GET call (api-version 2021-11-01):
      GET {ResourceId}?api-version=2021-11-01

    Server fields mapped from the ARM managed-instance response:
      id, name, location,
      state            ← .properties.state
      v_cores          ← .properties.vCores
      storage_size_in_gb ← .properties.storageSizeInGB
      sku{ name, tier } (or $null if .sku is absent)

    Returns [ordered]@{
        resource_id  = $null  (caller overrides with Get-AzureResourceId)
        server       (fields above)
        parameters             = @()
        parameters_non_default = @()
    }

    NOTE: No 'databases' key — sql-managed-instance has no sub-databases list,
    matching Python's _collect_sql_managed_instance which omits the key.
    #>
    [OutputType([System.Collections.Specialized.OrderedDictionary])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][string]$Token
    )

    $apiVersion = $script:AzInvSqlApiVersion
    $uri        = "https://management.azure.com${ResourceId}?api-version=${apiVersion}"
    $mi         = Invoke-AzureRest -Uri $uri -Token $Token

    $sku = $mi.sku

    $server = [ordered]@{
        id                 = $mi.id
        name               = $mi.name
        location           = $mi.location
        state              = $mi.properties.state
        v_cores            = $mi.properties.vCores
        storage_size_in_gb = $mi.properties.storageSizeInGB
        sku                = if ($null -ne $sku) {
            [ordered]@{
                name = $sku.name
                tier = $sku.tier
            }
        } else { $null }
    }

    [ordered]@{
        resource_id            = $null
        server                 = $server
        parameters             = @()
        parameters_non_default = @()
    }
}
