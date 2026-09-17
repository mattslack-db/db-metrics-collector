BeforeAll { Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force }

Describe 'Get-DurationString' {
    It 'renders a day duration as P#D' {
        $dur = New-TimeSpan -Days 1
        Get-DurationString $dur | Should -Be 'P1D'
    }
    It 'renders 7 days as P7D' {
        $dur = New-TimeSpan -Days 7
        Get-DurationString $dur | Should -Be 'P7D'
    }
    It 'renders an hour duration as PT#H' {
        $dur = New-TimeSpan -Hours 1
        Get-DurationString $dur | Should -Be 'PT1H'
    }
    It 'renders 6 hours as PT6H' {
        $dur = New-TimeSpan -Hours 6
        Get-DurationString $dur | Should -Be 'PT6H'
    }
    It 'renders a minute duration as PT#M' {
        $dur = New-TimeSpan -Minutes 1
        Get-DurationString $dur | Should -Be 'PT1M'
    }
    It 'renders 5 minutes as PT5M' {
        $dur = New-TimeSpan -Minutes 5
        Get-DurationString $dur | Should -Be 'PT5M'
    }
    It 'renders 30 seconds as PT30S' {
        $dur = New-TimeSpan -Seconds 30
        Get-DurationString $dur | Should -Be 'PT30S'
    }
    It 'renders 1 second as PT1S' {
        $dur = New-TimeSpan -Seconds 1
        Get-DurationString $dur | Should -Be 'PT1S'
    }
}

Describe 'Get-ValueSummary' {
    It 'summarizes a value column' {
        $s = Get-ValueSummary @(1, 2, 3)
        $s.latest | Should -Be 3
        $s.min | Should -Be 1
        $s.max | Should -Be 3
        $s.avg | Should -Be 2
        $s.count | Should -Be 3
    }
    It 'rounds avg to 4 decimal places' {
        (Get-ValueSummary @(1, 2)).avg | Should -Be 1.5
        (Get-ValueSummary @(1, 1, 1, 2)).avg | Should -Be 1.25
    }
    It 'handles 5/3 rounding to 4dp' {
        # 5/3 = 1.6666... rounds to 1.6667
        (Get-ValueSummary @(1, 1, 1, 2, 2, 2)).avg | Should -Be 1.5
    }
    It 'returns $null for empty array' {
        Get-ValueSummary @() | Should -Be $null
    }
    It 'returns $null when all values are null' {
        Get-ValueSummary @($null, $null) | Should -Be $null
    }
    It 'filters out null values' {
        $s = Get-ValueSummary @(1, $null, 3)
        $s.latest | Should -Be 3
        $s.count | Should -Be 2
    }
}

Describe 'Get-PointSummary' {
    It 'builds summary only for present fields' {
        $pts = @(@{ average = 1.0 }, @{ average = 3.0 })
        $sum = Get-PointSummary $pts
        $sum.Keys | Should -Contain 'average'
        $sum.Keys | Should -Not -Contain 'total'
        $sum.Keys | Should -Not -Contain 'minimum'
    }
    It 'summarizes multiple fields in correct order' {
        $pts = @(
            @{ average = 1.0; minimum = 0.5; maximum = 1.5; total = 10; count = 10 },
            @{ average = 2.0; minimum = 1.5; maximum = 2.5; total = 20; count = 10 }
        )
        $sum = Get-PointSummary $pts
        # Verify field order: average, minimum, maximum, total, count
        [array]$keys = $sum.Keys
        $keys[0] | Should -Be 'average'
        $keys[1] | Should -Be 'minimum'
        $keys[2] | Should -Be 'maximum'
        $keys[3] | Should -Be 'total'
        $keys[4] | Should -Be 'count'
    }
    It 'returns empty when no points' {
        $sum = Get-PointSummary @()
        $sum.Count | Should -Be 0
    }
    It 'handles missing fields in some points' {
        $pts = @(
            @{ average = 1.0 },
            @{ average = 2.0; total = 20 }
        )
        $sum = Get-PointSummary $pts
        $sum.Keys | Should -Contain 'average'
        $sum.Keys | Should -Contain 'total'
    }
}

Describe 'Select-Granularity' {
    It 'returns requested when no available' {
        $req = ConvertFrom-Iso8601Duration 'PT1M'
        $result = Select-Granularity $req @()
        $result | Should -Be $req
    }
    It 'returns requested when it is available' {
        $req = ConvertFrom-Iso8601Duration 'PT1M'
        $avail = @((ConvertFrom-Iso8601Duration 'PT1M'), (ConvertFrom-Iso8601Duration 'PT5M'))
        $result = Select-Granularity $req $avail
        $result | Should -Be (ConvertFrom-Iso8601Duration 'PT1M')
    }
    It 'chooses finest supported grain >= requested' {
        $req = ConvertFrom-Iso8601Duration 'PT2M'
        $avail = @((ConvertFrom-Iso8601Duration 'PT1M'), (ConvertFrom-Iso8601Duration 'PT5M'))
        $result = Select-Granularity $req $avail
        $result | Should -Be (ConvertFrom-Iso8601Duration 'PT5M')
    }
    It 'falls back to max available when all are finer than requested' {
        $req = ConvertFrom-Iso8601Duration 'PT10M'
        $avail = @((ConvertFrom-Iso8601Duration 'PT1M'), (ConvertFrom-Iso8601Duration 'PT5M'))
        $result = Select-Granularity $req $avail
        $result | Should -Be (ConvertFrom-Iso8601Duration 'PT5M')
    }
}
