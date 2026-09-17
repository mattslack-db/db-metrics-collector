BeforeAll { Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force }
Describe 'ConvertFrom-Iso8601Duration' {
    It 'parses PT1M/PT5M/PT1H/P1D' {
        (ConvertFrom-Iso8601Duration 'PT1M').TotalMinutes | Should -Be 1
        (ConvertFrom-Iso8601Duration 'PT5M').TotalMinutes | Should -Be 5
        (ConvertFrom-Iso8601Duration 'PT1H').TotalHours   | Should -Be 1
        (ConvertFrom-Iso8601Duration 'P1D').TotalDays     | Should -Be 1
    }
    It 'throws on malformed input' { { ConvertFrom-Iso8601Duration 'banana' } | Should -Throw }
    It 'throws on zero duration'   { { ConvertFrom-Iso8601Duration 'PT0S' }  | Should -Throw }
}
Describe 'Get-MetricWindow' {
    It 'spans Hours ending at Now (UTC)' {
        $now = [datetime]::new(2026,1,2,3,0,0,[System.DateTimeKind]::Utc)
        $w = Get-MetricWindow -Hours 1 -Now $now
        $w.End | Should -Be $now
        ($w.End - $w.Start).TotalHours | Should -Be 1
    }
    It 'throws on non-positive hours' { { Get-MetricWindow -Hours 0 } | Should -Throw }
}
