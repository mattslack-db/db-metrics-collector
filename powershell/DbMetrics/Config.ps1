# Known target fields that belong directly on the target object
$script:KnownFields = @('name', 'cloud', 'service', 'hours', 'interval')

function Import-TargetConfig {
    <#
    .SYNOPSIS
    Parses a JSON config file and returns a validated array of target hashtables.

    .PARAMETER Path
    Path to a JSON file with structure: { defaults: {...}, targets: [...] }

    .OUTPUTS
    [array] Array of target hashtables, each with keys: name, cloud, service, hours, interval, params.

    .THROWS
    ValueError-like exceptions for structural or validation problems.
    #>
    [OutputType([array])] param([Parameter(Mandatory)][string]$Path)

    # Parse JSON
    $raw = Get-Content -Path $Path -Raw | ConvertFrom-Json -AsHashtable

    $defaults = $raw['defaults'] -as [hashtable]
    if ($null -eq $defaults) { $defaults = @{} }

    $targetsRaw = $raw['targets']
    if ($null -eq $targetsRaw -or $targetsRaw.Count -eq 0) {
        throw "'targets' must be a non-empty list in the config file"
    }

    $results = @()
    for ($idx = 0; $idx -lt $targetsRaw.Count; $idx++) {
        $target = Build-DbTarget -Index $idx -TargetDict $targetsRaw[$idx] -Defaults $defaults
        $results += $target
    }

    # Return array-safe: always return an array
    , $results
}

function Build-DbTarget {
    <#
    .SYNOPSIS
    Internal helper: validates and builds a single target from a config dict and defaults.
    #>
    param(
        [int]$Index,
        [hashtable]$TargetDict,
        [hashtable]$Defaults
    )

    # Merge: target keys win over defaults
    $merged = @{}
    $Defaults.Keys | ForEach-Object { $merged[$_] = $Defaults[$_] }
    $TargetDict.Keys | ForEach-Object { $merged[$_] = $TargetDict[$_] }

    # Determine target identifier for error messages
    $targetId = if ('name' -in $merged.Keys) { $merged['name'] } else { $Index }

    # Validate required identity fields
    foreach ($field in @('name', 'cloud', 'service')) {
        if ($field -notin $merged.Keys) {
            throw "Target '$targetId': missing required field '$field'"
        }
    }

    $name = $merged['name']
    $cloud = $merged['cloud']
    $service = $merged['service']

    # Validate service is known
    $knownServices = Get-DbServiceNames
    if ($service -notin $knownServices) {
        $known = $knownServices -join ', '
        throw "Target '$name': unknown service '$service'; known: $known"
    }

    # Validate cloud matches service definition (all azure services require cloud=azure)
    if ($cloud -ne 'azure') {
        throw "Target '$name': cloud mismatch — service '$service' requires cloud 'azure', got '$cloud'"
    }

    # Split known fields from params
    $params = @{}
    $merged.Keys | Where-Object { $_ -notin $script:KnownFields } | ForEach-Object {
        $params[$_] = $merged[$_]
    }

    # Validate required params are present
    $serviceMetadata = Get-DbServiceMetadata -ServiceName $service
    $required = $serviceMetadata['RequiredParams']
    $missing = @($required | Where-Object { -not $params.ContainsKey($_) })

    if ($missing.Count -gt 0) {
        $missingStr = $missing -join ', '
        throw "Target '$name' (service '$service') missing required param(s): $missingStr"
    }

    # Build target object with known fields
    $target = [ordered]@{
        name = $name
        cloud = $cloud
        service = $service
        params = $params
    }

    # Only include hours/interval if explicitly provided
    # Use -in operator to handle both hashtable and OrderedDictionary
    if ('hours' -in $merged.Keys) {
        $target['hours'] = $merged['hours']
    }
    if ('interval' -in $merged.Keys) {
        $target['interval'] = $merged['interval']
    }

    $target
}

function Get-DbServiceMetadata {
    <#
    .SYNOPSIS
    Internal helper: retrieves service metadata from registry.
    #>
    param([Parameter(Mandatory)][string]$ServiceName)

    # DbServices is defined in Registry.ps1 and auto-loaded
    # We need to access it via Get-Variable to ensure it's available
    $dbServices = Get-Variable -Name DbServices -Scope Script -ValueOnly -ErrorAction SilentlyContinue

    if ($null -eq $dbServices) {
        throw "DbServices registry not found. Ensure Registry.ps1 is loaded."
    }

    if ($ServiceName -notin $dbServices.Keys) {
        throw "Service '$ServiceName' not found in registry"
    }

    $dbServices[$ServiceName]
}
