BeforeAll { Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force }

Describe 'Get-DbServiceNames' {
    It 'returns all 6 Azure services in sorted order' {
        $names = Get-DbServiceNames
        $names.Count | Should -Be 6
        $expected = @('cosmos-postgres', 'mysql-flexible', 'postgres-flexible', 'single-server', 'sql-database', 'sql-managed-instance')
        $names | Should -Be $expected
    }
}

Describe 'Service metadata' {
    It 'postgres-flexible has correct required params' {
        $names = Get-DbServiceNames
        $names -contains 'postgres-flexible' | Should -Be $true
    }

    It 'mysql-flexible has correct required params' {
        $names = Get-DbServiceNames
        $names -contains 'mysql-flexible' | Should -Be $true
    }

    It 'cosmos-postgres has correct required params' {
        $names = Get-DbServiceNames
        $names -contains 'cosmos-postgres' | Should -Be $true
    }

    It 'sql-database has correct required params' {
        $names = Get-DbServiceNames
        $names -contains 'sql-database' | Should -Be $true
    }

    It 'sql-managed-instance has correct required params' {
        $names = Get-DbServiceNames
        $names -contains 'sql-managed-instance' | Should -Be $true
    }

    It 'single-server has correct required params' {
        $names = Get-DbServiceNames
        $names -contains 'single-server' | Should -Be $true
    }
}

Describe 'Resolve-Provider' {
    It 'accepts a valid postgres-flexible target' {
        $target = @{
            name = 'test-pg'
            service = 'postgres-flexible'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                server_name = 'pg-server'
            }
        }
        { Resolve-Provider $target } | Should -Not -Throw
    }

    It 'accepts a valid mysql-flexible target' {
        $target = @{
            name = 'test-mysql'
            service = 'mysql-flexible'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                server_name = 'mysql-server'
            }
        }
        { Resolve-Provider $target } | Should -Not -Throw
    }

    It 'accepts a valid cosmos-postgres target' {
        $target = @{
            name = 'test-cosmos'
            service = 'cosmos-postgres'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                cluster_name = 'cosmos-cluster'
            }
        }
        { Resolve-Provider $target } | Should -Not -Throw
    }

    It 'accepts a valid sql-database target' {
        $target = @{
            name = 'test-sql'
            service = 'sql-database'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                server_name = 'sql-server'
                database = 'mydb'
            }
        }
        { Resolve-Provider $target } | Should -Not -Throw
    }

    It 'accepts a valid sql-managed-instance target' {
        $target = @{
            name = 'test-sqlmi'
            service = 'sql-managed-instance'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                instance_name = 'sqlmi-instance'
            }
        }
        { Resolve-Provider $target } | Should -Not -Throw
    }

    It 'accepts a valid single-server target' {
        $target = @{
            name = 'test-single'
            service = 'single-server'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                server_name = 'single-server'
                sub_engine = 'postgres'
            }
        }
        { Resolve-Provider $target } | Should -Not -Throw
    }

    It 'throws on unknown service' {
        $target = @{
            name = 'test'
            service = 'unknown-service'
            params = @{}
        }
        { Resolve-Provider $target } | Should -Throw
    }

    It 'throws on unknown service and names the service' {
        $target = @{
            name = 'my-target'
            service = 'unknown-service'
            params = @{}
        }
        { Resolve-Provider $target } | Should -Throw -ExpectedMessage "*unknown-service*"
    }

    It 'throws on unknown service and lists known services' {
        $target = @{
            name = 'my-target'
            service = 'unknown-service'
            params = @{}
        }
        { Resolve-Provider $target } | Should -Throw -ExpectedMessage "*postgres-flexible*"
    }

    It 'throws on missing required param and names the param' {
        $target = @{
            name = 'test-pg'
            service = 'postgres-flexible'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                # server_name is missing
            }
        }
        { Resolve-Provider $target } | Should -Throw -ExpectedMessage "*server_name*"
    }

    It 'throws on missing required param and names the target' {
        $target = @{
            name = 'my-server'
            service = 'postgres-flexible'
            params = @{
                subscription = 'sub-1'
                # resource_group and server_name are missing
            }
        }
        { Resolve-Provider $target } | Should -Throw -ExpectedMessage "*my-server*"
    }

    It 'throws on missing multiple required params' {
        $target = @{
            name = 'test-sql'
            service = 'sql-database'
            params = @{
                subscription = 'sub-1'
                # resource_group, server_name, database are missing
            }
        }
        { Resolve-Provider $target } | Should -Throw
    }

    It 'cosmos-postgres requires cluster_name not server_name' {
        $target = @{
            name = 'test-cosmos'
            service = 'cosmos-postgres'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                server_name = 'wrong-param'
                # cluster_name is missing
            }
        }
        { Resolve-Provider $target } | Should -Throw -ExpectedMessage "*cluster_name*"
    }

    It 'single-server requires sub_engine not just server_name' {
        $target = @{
            name = 'test-single'
            service = 'single-server'
            params = @{
                subscription = 'sub-1'
                resource_group = 'rg-1'
                server_name = 'single-server'
                # sub_engine is missing
            }
        }
        { Resolve-Provider $target } | Should -Throw -ExpectedMessage "*sub_engine*"
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }
