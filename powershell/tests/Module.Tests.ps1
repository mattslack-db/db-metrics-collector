BeforeAll {
    $script:ModulePath = Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1'
    Import-Module $script:ModulePath -Force
}
Describe 'DbMetrics module' {
    It 'imports without error' {
        Get-Module DbMetrics | Should -Not -BeNullOrEmpty
    }
}
AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }
