BeforeAll {
    $script:ModulePath = Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1'
    Import-Module $script:ModulePath -Force
}

Describe 'Get-DbToken' {
    BeforeEach { InModuleScope DbMetrics { $script:DbTokenCache = @{} } }

    It 'returns the access token and caches per (sub,tenant)' {
        Mock -ModuleName DbMetrics Invoke-AzToken { '{"accessToken":"TOK","tokenType":"Bearer"}' }
        (Get-DbToken -Subscription s -Tenant t) | Should -Be 'TOK'
        (Get-DbToken -Subscription s -Tenant t) | Should -Be 'TOK'
        Should -Invoke -ModuleName DbMetrics Invoke-AzToken -Times 1  # cached second call
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }
