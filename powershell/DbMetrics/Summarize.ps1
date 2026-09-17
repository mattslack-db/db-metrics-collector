function Get-DurationString {
    <#
    .SYNOPSIS
    Render a timespan as an ISO-8601 duration (best effort).

    .DESCRIPTION
    Converts a TimeSpan to ISO 8601 duration format. Prefers larger units when possible.
    - Days: P#D
    - Hours: PT#H
    - Minutes: PT#M
    - Seconds: PT#S
    #>
    [OutputType([string])] param([Parameter(Mandatory)][timespan]$Delta)

    $seconds = [int]$Delta.TotalSeconds

    if ($seconds % 86400 -eq 0) {
        return "P$([int]($seconds / 86400))D"
    }
    if ($seconds % 3600 -eq 0) {
        return "PT$([int]($seconds / 3600))H"
    }
    if ($seconds % 60 -eq 0) {
        return "PT$([int]($seconds / 60))M"
    }
    return "PT${seconds}S"
}

function Get-ValueSummary {
    <#
    .SYNOPSIS
    Return latest/min/max/avg/count for a list of numeric values.

    .DESCRIPTION
    Summarizes an array of values, filtering out nulls. Returns $null if no values present.
    Average is rounded to 4 decimal places.
    #>
    [OutputType([ordered])] param([object[]]$Values = @())

    $nums = @($Values | Where-Object { $_ -ne $null })

    if ($nums.Count -eq 0) {
        return $null
    }

    $sum = 0
    foreach ($n in $nums) {
        $sum += $n
    }
    $avg = $sum / $nums.Count
    $rounded = [math]::Round($avg, 4)

    [ordered]@{
        latest = $nums[-1]
        min    = ($nums | Measure-Object -Minimum).Minimum
        max    = ($nums | Measure-Object -Maximum).Maximum
        avg    = $rounded
        count  = $nums.Count
    }
}

function Get-PointSummary {
    <#
    .SYNOPSIS
    Summarize a list of per-timestamp value dicts, per value field.

    .DESCRIPTION
    For each field in the order: average, minimum, maximum, total, count,
    gathers that field's non-null values across points. If any values exist
    for that field, adds Get-ValueSummary of that column under the field name.
    Returns an ordered hashtable (may be empty).
    #>
    [OutputType([ordered])] param([hashtable[]]$Points = @())

    $summary = [ordered]@{}
    $valueFields = @('average', 'minimum', 'maximum', 'total', 'count')

    foreach ($field in $valueFields) {
        $column = @(
            $Points | ForEach-Object {
                if ($_.ContainsKey($field) -and $_[$field] -ne $null) {
                    $_[$field]
                }
            }
        )

        if ($column.Count -gt 0) {
            $fieldSummary = Get-ValueSummary $column
            if ($fieldSummary) {
                $summary[$field] = $fieldSummary
            }
        }
    }

    $summary
}

function Select-Granularity {
    <#
    .SYNOPSIS
    Pick the finest supported grain that still honors the request.

    .DESCRIPTION
    Applies the following logic:
    - No availability info -> use the request as-is
    - Request supported -> use it
    - Otherwise -> smallest grain >= request (finest that Azure accepts), or the
      coarsest available if the request is finer than everything on offer
    #>
    [OutputType([timespan])] param(
        [Parameter(Mandatory)][timespan]$Requested,
        [timespan[]]$Available = @()
    )

    if ($Available.Count -eq 0) {
        return $Requested
    }

    if ($Available -contains $Requested) {
        return $Requested
    }

    $notFiner = @($Available | Where-Object { $_ -ge $Requested } | Sort-Object)

    if ($notFiner.Count -gt 0) {
        return $notFiner[0]
    }

    return ($Available | Measure-Object -Maximum).Maximum
}
