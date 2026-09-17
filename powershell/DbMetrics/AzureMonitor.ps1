function Invoke-AzureRest {
    <#
    .SYNOPSIS
    Thin, mockable GET wrapper for Azure ARM / Monitor REST calls.

    .DESCRIPTION
    Wraps Invoke-RestMethod for Azure management-plane GET requests.
    Kept as a separate named function so unit tests can mock it with
    Mock -ModuleName DbMetrics Invoke-AzureRest without hitting the network.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory)][string]$Uri,
        [Parameter(Mandatory)][string]$Token
    )
    Invoke-RestMethod -Method GET -Uri $Uri -Headers @{ Authorization = "Bearer $Token" }
}

function Get-MetricDefinition {
    <#
    .SYNOPSIS
    Discover available metric definitions for an Azure resource.

    .DESCRIPTION
    Calls GET …/providers/microsoft.insights/metricDefinitions?api-version=2018-01-01
    and maps each item in value[] to:
        [ordered]@{ name; unit; aggregations; dimensions; granularities }

    Aggregation types equal to 'None' (any case) or $null are excluded.
    If no aggregations remain after filtering the fallback is @('Average').
    Dimensions are the .value strings of each dimension object (empty array when none).
    Granularities are the .timeGrain ISO-8601 strings from metricAvailabilities.
    #>
    [OutputType([array])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][string]$Token
    )

    $uri = "https://management.azure.com${ResourceId}/providers/microsoft.insights/metricDefinitions?api-version=2018-01-01"
    $response = Invoke-AzureRest -Uri $uri -Token $Token

    $skipAggs = @('None', 'NONE', 'none')
    $defs = @()

    foreach ($item in ($response.value ?? @())) {
        $rawAggs = @(
            $item.supportedAggregationTypes |
            Where-Object { $_ -ne $null -and $_ -notin $skipAggs }
        )
        $aggregations = if ($rawAggs.Count -gt 0) { $rawAggs } else { @('Average') }

        $dimensions = @()
        if ($item.dimensions) {
            $dimensions = @(
                $item.dimensions |
                ForEach-Object { $_.value } |
                Where-Object { $_ -ne $null -and $_ -ne '' }
            )
        }

        $granularities = @()
        if ($item.metricAvailabilities) {
            $granularities = @($item.metricAvailabilities | ForEach-Object { $_.timeGrain })
        }

        $defs += [ordered]@{
            name          = $item.name.value
            unit          = $item.unit
            aggregations  = $aggregations
            dimensions    = $dimensions
            granularities = $granularities
        }
    }

    # Comma-return preserves array-ness on direct assignment ($x = Get-...), even
    # for a single-element or empty result. Callers MUST assign directly, NOT wrap
    # in @() — @() around a comma-return double-wraps into a single-element array
    # holding the whole list (see Cli.ps1).
    ,$defs
}

function Get-MetricSeries {
    <#
    .SYNOPSIS
    Query Azure Monitor metrics, one request per metric definition.

    .DESCRIPTION
    Port of db_metrics/providers/azure/monitor.py AzureMonitorSource.query().

    For each definition:
      1. Resolve the best available granularity via Select-Granularity.
      2. Build the base URI (metricnames, aggregation, timespan, interval).
      3. Build an optional OData $filter: "<dim> eq '*'" joined with " and ".
      4. First attempt: include $filter when dimensions are present.
         On exception: retry with no $filter.
         On second exception: append an error result and continue to next definition.
      5. On success: map each metric in value[] to
             [ordered]@{ name; unit; granularity; timeseries; error=$null }
         Each timeseries element maps to
             [ordered]@{ dimensions; points; summary }
         Each point is [ordered]@{ timestamp } + non-null value fields.
    #>
    [OutputType([array])]
    param(
        [Parameter(Mandatory)][string]$ResourceId,
        [Parameter(Mandatory)][array]$Definitions,
        [Parameter(Mandatory)][datetime]$Start,
        [Parameter(Mandatory)][datetime]$End,
        [Parameter(Mandatory)][timespan]$Granularity,
        [Parameter(Mandatory)][string]$Token
    )

    $startIso = $Start.ToUniversalTime().ToString('o')
    $endIso   = $End.ToUniversalTime().ToString('o')
    $results  = @()

    foreach ($def in $Definitions) {
        # Resolve closest supported granularity
        $availGrains = @($def.granularities | ForEach-Object { ConvertFrom-Iso8601Duration $_ })
        $grain = Select-Granularity -Requested $Granularity -Available $availGrains

        # Build URI components
        $agg         = ($def.aggregations -join ',')
        $timespanEnc = [uri]::EscapeDataString("${startIso}/${endIso}")
        $intervalStr = Get-DurationString -Delta $grain

        $baseUri = "https://management.azure.com${ResourceId}/providers/microsoft.insights/metrics" +
                   "?api-version=2018-01-01" +
                   "&metricnames=$([uri]::EscapeDataString($def.name))" +
                   "&aggregation=$([uri]::EscapeDataString($agg))" +
                   "&timespan=${timespanEnc}" +
                   "&interval=$([uri]::EscapeDataString($intervalStr))"

        # Optional OData $filter built from dimension names
        $filter = if ($def.dimensions) {
            ($def.dimensions | ForEach-Object { "$_ eq '*'" }) -join ' and '
        } else { $null }

        # First-attempt URI: append $filter when present
        $uriFirst = $baseUri
        if ($filter) {
            $uriFirst = "${baseUri}&`$filter=$([uri]::EscapeDataString($filter))"
        }

        # Try / retry-without-filter / record-error  (mirrors Python AzureMonitorSource.query)
        $response = $null
        try {
            $response = Invoke-AzureRest -Uri $uriFirst -Token $Token
        }
        catch {
            try {
                $response = Invoke-AzureRest -Uri $baseUri -Token $Token
            }
            catch {
                $results += [ordered]@{
                    name        = $def.name
                    unit        = $null
                    granularity = $null
                    timeseries  = @()
                    error       = $_.Exception.Message
                }
                continue
            }
        }

        # Map each metric in the response
        foreach ($metric in ($response.value ?? @())) {
            $timeseries = @()
            foreach ($ts in ($metric.timeseries ?? @())) {
                # dimensions: metadatavalues → { name.value = value }
                $dimDict = @{}
                foreach ($mv in ($ts.metadatavalues ?? @())) {
                    $dimDict[$mv.name.value] = $mv.value
                }
                # points: data[] → [ordered]@{ timestamp; <value fields> }
                # Use PSObject.Properties[$field] rather than $dp.$field to detect
                # field EXISTENCE.  Member access ($dp.count) returns PowerShell's
                # synthetic .Count = 1 on any PSCustomObject that lacks a real 'count'
                # property, causing absent aggregation fields to appear as count=1.
                # PSObject.Properties[$field] returns $null when the property is absent,
                # matching Python's getattr(value, field, None) behaviour.
                $points = @()
                foreach ($dp in ($ts.data ?? @())) {
                    $point = [ordered]@{ timestamp = $dp.timeStamp }
                    foreach ($field in @('average', 'minimum', 'maximum', 'total', 'count')) {
                        $prop = $dp.PSObject.Properties[$field]
                        if ($prop -and $null -ne $prop.Value) {
                            $point[$field] = $prop.Value
                        }
                    }
                    $points += $point
                }
                $timeseries += [ordered]@{
                    dimensions = $dimDict
                    points     = $points
                    summary    = Get-PointSummary -Points $points
                }
            }
            $results += [ordered]@{
                name        = $metric.name.value
                unit        = $metric.unit
                granularity = Get-DurationString -Delta $grain
                timeseries  = $timeseries
                error       = $null
            }
        }
    }

    # Comma-return preserves array-ness on direct assignment (see the note in
    # Get-MetricDefinition). Callers MUST assign directly, NOT wrap in @().
    ,$results
}
