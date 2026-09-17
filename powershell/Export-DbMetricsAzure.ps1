#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Export Azure database performance metrics and configuration for one target
    (via flags) or many (via -Config).

.DESCRIPTION
    Entry script for the PowerShell Azure metrics exporter — a twin of the
    Python db-metrics-azure CLI.  Imports the DbMetrics module and delegates
    all work to Invoke-Run, which returns an exit code (0 ok / 1 error / 2 usage).

.PARAMETER Service
    Azure service, e.g. postgres-flexible, mysql-flexible, sql-database.
    Required when -Config is not specified.

.PARAMETER Subscription
    Azure subscription GUID or display name.

.PARAMETER ResourceGroup
    Azure resource group name.

.PARAMETER ServerName
    Azure server / instance name (postgres-flexible, mysql-flexible, sql-database,
    single-server).

.PARAMETER Database
    Database name (sql-database only).

.PARAMETER SubEngine
    Sub-engine for single-server: 'postgresql' or 'mysql'.

.PARAMETER ClusterName
    Cluster name (cosmos-postgres only).

.PARAMETER InstanceName
    Managed-instance name (sql-managed-instance only).

.PARAMETER Tenant
    Entra tenant ID override (default: subscription home tenant).

.PARAMETER Hours
    Look-back window in hours (default: 1).

.PARAMETER Interval
    Granularity as ISO-8601 duration (default: PT1M).

.PARAMETER Out
    Output JSON path for a single target (default: metrics_<name>_<timestamp>.json).

.PARAMETER NoConsole
    Suppress console summaries (JSON only).

.PARAMETER Config
    JSON config file describing a list of targets (mutually exclusive with
    single-target flags).
#>
param(
    [string]$Service,
    [string]$Subscription,
    [string]$ResourceGroup,
    [string]$ServerName,
    [string]$Database,
    [string]$SubEngine,
    [string]$ClusterName,
    [string]$InstanceName,
    [string]$Tenant,
    [double]$Hours,
    [string]$Interval,
    [string]$Out,
    [switch]$NoConsole,
    [string]$Config
)

Import-Module "$PSScriptRoot/DbMetrics/DbMetrics.psd1" -Force

exit (Invoke-Run -BoundParams $PSBoundParameters)
