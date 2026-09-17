# Azure service registry: maps service name to required parameters
$script:DbServices = @{
    'postgres-flexible' = @{
        RequiredParams = @('subscription', 'resource_group', 'server_name')
    }
    'mysql-flexible' = @{
        RequiredParams = @('subscription', 'resource_group', 'server_name')
    }
    'cosmos-postgres' = @{
        RequiredParams = @('subscription', 'resource_group', 'cluster_name')
    }
    'sql-database' = @{
        RequiredParams = @('subscription', 'resource_group', 'server_name', 'database')
    }
    'sql-managed-instance' = @{
        RequiredParams = @('subscription', 'resource_group', 'instance_name')
    }
    'single-server' = @{
        RequiredParams = @('subscription', 'resource_group', 'server_name', 'sub_engine')
    }
}

function Get-DbServiceNames {
    <#
    .SYNOPSIS
    Returns the sorted list of registered service names.

    .OUTPUTS
    [string[]] Sorted service names.
    #>
    [OutputType([string[]])] param()
    $script:DbServices.Keys | Sort-Object
}

function Resolve-Provider {
    <#
    .SYNOPSIS
    Validates that a target has a known service and all required parameters.

    .PARAMETER Target
    A hashtable with keys: name, service, params (which is itself a hashtable).

    .THROWS
    ValueError-like exception if service is unknown or required params are missing.
    #>
    [OutputType([void])] param([Parameter(Mandatory)][hashtable]$Target)

    $serviceName = $Target['service']
    $targetName = $Target['name']
    $params = $Target['params']

    # Validate service is known
    if ($serviceName -notin $script:DbServices.Keys) {
        $known = @($script:DbServices.Keys | Sort-Object) -join ', '
        throw "Target '$targetName': unknown service '$serviceName'. Known services: $known"
    }

    # Validate required params are present
    $required = $script:DbServices[$serviceName]['RequiredParams']
    $missing = @($required | Where-Object { -not $params.ContainsKey($_) })

    if ($missing.Count -gt 0) {
        $missingStr = $missing -join ', '
        throw "Target '$targetName' (service '$serviceName') missing required param(s): $missingStr"
    }
}
