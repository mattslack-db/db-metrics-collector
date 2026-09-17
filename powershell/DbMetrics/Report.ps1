# Report.ps1 — report assembly, summary, console rendering, and JSON output.
# Port of db_metrics/report.py (new-path build_report, build_summary,
# render_console_summary, render_summary_table, write_json).

function Build-Report {
    <#
    .SYNOPSIS
        Assemble the full per-target report (ordered dict, canonical key order).
    .DESCRIPTION
        Port of report.py build_report (new path: target is not None).
        Keys emitted in canonical order:
          collected_at, name, cloud, service, resource_scope,
          window, inventory, metric_definitions, metrics.
    #>
    param(
        [Parameter(Mandatory)][hashtable]$Target,
        [Parameter(Mandatory)][string]$ResourceScope,
        [Parameter(Mandatory)][hashtable]$Inventory,
        [Parameter(Mandatory)][AllowEmptyCollection()][array]$Definitions,
        [Parameter(Mandatory)][AllowEmptyCollection()][array]$Metrics,
        [Parameter(Mandatory)][hashtable]$Window,
        [Parameter(Mandatory)][string]$Interval
    )

    $windowDict = [ordered]@{
        start    = $Window.Start.ToUniversalTime().ToString('o')
        end      = $Window.End.ToUniversalTime().ToString('o')
        interval = $Interval
    }

    [ordered]@{
        collected_at       = (Get-Date).ToUniversalTime().ToString('o')
        name               = $Target.name
        cloud              = $Target.cloud
        service            = $Target.service
        resource_scope     = $ResourceScope
        window             = $windowDict
        inventory          = $Inventory
        metric_definitions = [array]$Definitions
        metrics            = [array]$Metrics
    }
}

function Build-Summary {
    <#
    .SYNOPSIS
        Produce a multi-target summary dict.
    .DESCRIPTION
        Port of report.py build_summary.
        Status precedence: error (top-level error) > partial (metric error) > ok.
    #>
    param(
        [Parameter(Mandatory)][AllowEmptyCollection()][array]$Reports
    )

    $targets = @()
    foreach ($rep in $Reports) {
        if ('metrics' -in $rep.Keys -and $null -ne $rep['metrics']) {
            $metrics = @($rep['metrics'])
        } else {
            $metrics = @()
        }
        $metricCount = $metrics.Count
        $errorCount  = @($metrics | Where-Object { $_.error }).Count

        $status = if ($rep['error']) {
            'error'
        } elseif ($errorCount -gt 0) {
            'partial'
        } else {
            'ok'
        }

        $targets += [ordered]@{
            name         = $rep['name']
            cloud        = if ($rep['cloud'])   { $rep['cloud']   } else { '?' }
            service      = if ($rep['service']) { $rep['service'] } else { '?' }
            metric_count = $metricCount
            error_count  = $errorCount
            status       = $status
        }
    }

    $errorTargetCount = @($targets | Where-Object { $_.status -ne 'ok' }).Count

    [ordered]@{
        targets            = [array]$targets
        target_count       = $targets.Count
        error_target_count = $errorTargetCount
    }
}

# ---------------------------------------------------------------------------
# Internal helper — port of report.py _fmt.
# $null  → '-'
# float  → N2 with thousands separators (invariant culture)
# else   → string
# ---------------------------------------------------------------------------
function Format-DbMetricValue {
    param($Value)
    if ($null -eq $Value) { return '-' }
    if ($Value -is [double] -or $Value -is [float]) {
        return [string]::Format(
            [System.Globalization.CultureInfo]::InvariantCulture,
            '{0:N2}',
            [double]$Value
        )
    }
    return [string]$Value
}

function Format-ConsoleSummary {
    <#
    .SYNOPSIS
        Return a human-readable summary of inventory + per-metric stats.
    .DESCRIPTION
        Port of report.py render_console_summary.
        Columns: METRIC<42  UNIT<12  LATEST>7  AVG>7  MAX>7.
        Metrics sorted by name. ERROR row for errored metrics.
        (+N dim series) suffix when >1 timeseries.
    #>
    param(
        [Parameter(Mandatory)]$Report
    )

    $lines = [System.Collections.Generic.List[string]]::new()

    $inventory = if ($Report['inventory']) { $Report['inventory'] } else { @{} }
    $server    = if ($inventory['server']) { $inventory['server'] } else { @{} }

    # Derive label: prefer engine_label (legacy path) else cloud·service
    $label = if ($Report['engine_label']) {
        [string]$Report['engine_label']
    } else {
        $c = if ($Report['cloud'])   { [string]$Report['cloud']   } else { '?' }
        $s = if ($Report['service']) { [string]$Report['service'] } else { '?' }
        "$c · $s"
    }

    # Guard optional flexible-server sub-objects
    $sku     = if ($server['sku'])               { $server['sku'] }               else { @{} }
    $storage = if ($server['storage'])           { $server['storage'] }           else { @{} }
    $ha      = if ($server['high_availability']) { $server['high_availability'] } else { @{} }

    $lines.Add('=' * 70)
    $lines.Add("  $label — $($server['name'])")
    $lines.Add('=' * 70)
    $lines.Add("  Location   : $($server['location'])")
    $lines.Add("  Version    : $($server['version']) (minor $($server['minor_version']))")
    $lines.Add("  SKU / tier : $($sku['name']) / $($sku['tier'])")
    $lines.Add("  Storage    : $($storage['size_gb']) GB, $($storage['iops']) IOPS, autogrow=$($storage['auto_grow'])")
    $lines.Add("  HA         : mode=$($ha['mode']) state=$($ha['state'])")
    $lines.Add("  State      : $($server['state'])")

    $nonDefault = @($inventory['parameters_non_default'])
    $parameters = @($inventory['parameters'])
    $lines.Add("  Parameters : $($parameters.Count) total, $($nonDefault.Count) non-default")
    $lines.Add('')

    $win = $Report['window']
    $lines.Add("  Metrics window: $($win['start']) `u{2192} $($win['end']) @ $($win['interval'])")
    $lines.Add('-' * 70)
    $lines.Add(("  {0,-42}{1,-12}{2,7} {3,7} {4,7}" -f 'METRIC', 'UNIT', 'LATEST', 'AVG', 'MAX'))
    $lines.Add('-' * 70)

    $allMetrics = @($Report['metrics'])
    $sorted = $allMetrics | Sort-Object { if ($null -ne $_['name']) { $_['name'] } else { '' } }

    foreach ($metric in $sorted) {
        $mname = if ($null -ne $metric['name']) { [string]$metric['name'] } else { '?' }

        if ($metric['error']) {
            $errStr = [string]$metric['error']
            if ($errStr.Length -gt 20) { $errStr = $errStr.Substring(0, 20) }
            $lines.Add(("  {0,-42}{1,-12}{2}" -f $mname, 'ERROR', $errStr))
            continue
        }

        $unit    = if ($metric['unit']) { [string]$metric['unit'] } else { '' }
        $series  = @($metric['timeseries'])
        $summary = if ($series.Count -gt 0 -and $null -ne $series[0]['summary']) {
            $series[0]['summary']
        } else { @{} }

        # Primary summary: first present stat dict in precedence order
        $primary = $null
        foreach ($key in @('average', 'total', 'maximum', 'count', 'minimum')) {
            if ($null -ne $summary[$key]) { $primary = $summary[$key]; break }
        }
        if ($null -eq $primary) { $primary = @{} }

        $suffix = if ($series.Count -gt 1) { "  (+$($series.Count - 1) dim series)" } else { '' }

        $latest = Format-DbMetricValue $primary['latest']
        $avg    = Format-DbMetricValue $primary['avg']
        $max    = Format-DbMetricValue $primary['max']

        $lines.Add(("  {0,-42}{1,-12}{2,7} {3,7} {4,7}{5}" -f $mname, $unit, $latest, $avg, $max, $suffix))
    }

    $lines.Add('=' * 70)
    $lines -join "`n"
}

function Format-SummaryTable {
    <#
    .SYNOPSIS
        Return a human-readable table of per-target summary rows.
    .DESCRIPTION
        Port of report.py render_summary_table.
        Columns: name<30  cloud<8  service<16  metrics>8  errors>7  status<8.
        Footer: "Targets: N  |  Not OK: M".
    #>
    param(
        [Parameter(Mandatory)]$Summary
    )

    $colName    = 30
    $colCloud   = 8
    $colService = 16
    $colMetrics = 8
    $colErrors  = 7
    $colStatus  = 8

    $fmt    = "  {0,-$colName}{1,-$colCloud}{2,-$colService}{3,$colMetrics}{4,$colErrors}  {5,-$colStatus}"
    $header = $fmt -f 'NAME', 'CLOUD', 'SERVICE', 'METRICS', 'ERRORS', 'STATUS'
    $sep    = '-' * $header.Length

    $lines = [System.Collections.Generic.List[string]]::new()
    $lines.Add('')
    $lines.Add($sep)
    $lines.Add($header)
    $lines.Add($sep)

    $targets = @($Summary['targets'])
    foreach ($t in $targets) {
        $tname   = if ($t['name'])   { [string]$t['name']   } else { '(unnamed)' }
        $tcloud  = if ($t['cloud'])  { [string]$t['cloud']  } else { '?' }
        $tsvc    = if ($t['service']) { [string]$t['service'] } else { '?' }
        $tmc     = if ($null -ne $t['metric_count']) { [int]$t['metric_count'] } else { 0 }
        $tec     = if ($null -ne $t['error_count'])  { [int]$t['error_count']  } else { 0 }
        $tst     = if ($t['status']) { [string]$t['status'] } else { '?' }

        $lines.Add(($fmt -f $tname, $tcloud, $tsvc, $tmc, $tec, $tst))
    }

    $lines.Add($sep)
    $tc = if ($null -ne $Summary['target_count'])       { [int]$Summary['target_count']       } else { 0 }
    $nc = if ($null -ne $Summary['error_target_count']) { [int]$Summary['error_target_count'] } else { 0 }
    $lines.Add("  Targets: $tc  |  Not OK: $nc")
    $lines.Add('')

    $lines -join "`n"
}

function Write-ReportJson {
    <#
    .SYNOPSIS
        Serialize the report to a JSON file (UTF-8, trailing newline).
    .DESCRIPTION
        Port of report.py write_json.
        ConvertTo-Json is called directly (not via pipeline) to preserve
        1-element arrays inside the report.
    #>
    param(
        [Parameter(Mandatory)]$Report,
        [Parameter(Mandatory)][string]$Path
    )
    $json     = ConvertTo-Json $Report -Depth 32
    $encoding = [System.Text.UTF8Encoding]::new($false)   # UTF-8, no BOM
    [System.IO.File]::WriteAllText($Path, $json + "`n", $encoding)
}
