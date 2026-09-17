BeforeAll { Import-Module (Join-Path $PSScriptRoot '..' 'DbMetrics' 'DbMetrics.psd1') -Force }

Describe 'Import-TargetConfig' {
    BeforeEach {
        $testDir = [System.IO.Path]::GetTempPath()
        $testFile = Join-Path $testDir "config-test-$([guid]::NewGuid()).json"
    }

    AfterEach {
        if (Test-Path $testFile) { Remove-Item $testFile -Force }
    }

    Context 'Valid configurations' {
        It 'loads a single valid target' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result.Count | Should -Be 1
            $result[0].name | Should -Be 'my-pg'
        }

        It 'returns an array for a single-target config (array-safety)' {
            $json = @{
                targets = @(@{
                    name = 'single'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result -is [array] | Should -Be $true
            $result.Count | Should -Be 1
        }

        It 'loads multiple valid targets' {
            $json = @{
                targets = @(
                    @{
                        name = 't1'
                        cloud = 'azure'
                        service = 'postgres-flexible'
                        subscription = 'sub-1'
                        resource_group = 'rg-1'
                        server_name = 'pg-server'
                    },
                    @{
                        name = 't2'
                        cloud = 'azure'
                        service = 'mysql-flexible'
                        subscription = 'sub-1'
                        resource_group = 'rg-1'
                        server_name = 'mysql-server'
                    }
                )
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result.Count | Should -Be 2
            $result[0].name | Should -Be 't1'
            $result[1].name | Should -Be 't2'
        }

        It 'merges defaults into targets' {
            $json = @{
                defaults = @{
                    subscription = 'shared-sub'
                    resource_group = 'shared-rg'
                }
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result[0].params['subscription'] | Should -Be 'shared-sub'
            $result[0].params['resource_group'] | Should -Be 'shared-rg'
        }

        It 'target values override defaults' {
            $json = @{
                defaults = @{
                    subscription = 'default-sub'
                    hours = 6
                }
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'override-sub'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result[0].params['subscription'] | Should -Be 'override-sub'
            $result[0].hours | Should -Be 6
        }

        It 'splits known fields from params' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    hours = 2
                    interval = 'PT5M'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                    custom_field = 'custom-value'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result[0].name | Should -Be 'my-pg'
            $result[0].cloud | Should -Be 'azure'
            $result[0].service | Should -Be 'postgres-flexible'
            $result[0].hours | Should -Be 2
            $result[0].interval | Should -Be 'PT5M'
            $result[0].params['subscription'] | Should -Be 'sub-1'
            $result[0].params['custom_field'] | Should -Be 'custom-value'
        }

        It 'omits hours when not provided' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            ('hours' -in $result[0].Keys) | Should -Be $false
        }

        It 'omits interval when not provided' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            ('interval' -in $result[0].Keys) | Should -Be $false
        }
    }

    Context 'Validation: Missing required fields' {
        It 'throws when name is missing' {
            $json = @{
                targets = @(@{
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*name*"
        }

        It 'throws when cloud is missing' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*cloud*"
        }

        It 'throws when service is missing' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*service*"
        }

        It 'error names the target when missing required field' {
            $json = @{
                targets = @(@{
                    name = 'my-target'
                    cloud = 'azure'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*my-target*"
        }

        It 'error uses index when target has no name' {
            $json = @{
                targets = @(@{
                    cloud = 'azure'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*0*"
        }
    }

    Context 'Validation: Unknown service' {
        It 'throws when service is unknown' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'unknown-service'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*unknown-service*"
        }

        It 'unknown service error names the target' {
            $json = @{
                targets = @(@{
                    name = 'my-target'
                    cloud = 'azure'
                    service = 'unknown-service'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*my-target*"
        }

        It 'unknown service error lists known services' {
            $json = @{
                targets = @(@{
                    name = 'my-target'
                    cloud = 'azure'
                    service = 'nope'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*postgres-flexible*"
        }
    }

    Context 'Validation: Cloud mismatch' {
        It 'throws when cloud does not match service' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'aws'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*cloud*"
        }

        It 'cloud mismatch error names the target' {
            $json = @{
                targets = @(@{
                    name = 'my-target'
                    cloud = 'aws'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'pg-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*my-target*"
        }
    }

    Context 'Validation: Missing required params' {
        It 'throws when postgres-flexible is missing server_name' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*server_name*"
        }

        It 'throws when cosmos-postgres is missing cluster_name' {
            $json = @{
                targets = @(@{
                    name = 'my-cosmos'
                    cloud = 'azure'
                    service = 'cosmos-postgres'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*cluster_name*"
        }

        It 'throws when sql-database is missing database' {
            $json = @{
                targets = @(@{
                    name = 'my-sql'
                    cloud = 'azure'
                    service = 'sql-database'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                    server_name = 'sql-server'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*database*"
        }

        It 'missing required param error names the target' {
            $json = @{
                targets = @(@{
                    name = 'my-pg'
                    cloud = 'azure'
                    service = 'postgres-flexible'
                    subscription = 'sub-1'
                    resource_group = 'rg-1'
                })
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*my-pg*"
        }
    }

    Context 'Structural validation' {
        It 'throws when targets key is missing' {
            $json = @{
                defaults = @{}
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*targets*"
        }

        It 'throws when targets list is empty' {
            $json = @{
                targets = @()
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            { Import-TargetConfig -Path $testFile } | Should -Throw -ExpectedMessage "*targets*"
        }
    }

    Context 'Complex scenarios' {
        It 'handles all 6 Azure services' {
            $json = @{
                defaults = @{
                    subscription = 'default-sub'
                    resource_group = 'default-rg'
                }
                targets = @(
                    @{
                        name = 'postgres'
                        cloud = 'azure'
                        service = 'postgres-flexible'
                        server_name = 'pg'
                    },
                    @{
                        name = 'mysql'
                        cloud = 'azure'
                        service = 'mysql-flexible'
                        server_name = 'my'
                    },
                    @{
                        name = 'cosmos'
                        cloud = 'azure'
                        service = 'cosmos-postgres'
                        cluster_name = 'cos'
                    },
                    @{
                        name = 'sql-db'
                        cloud = 'azure'
                        service = 'sql-database'
                        server_name = 'sql'
                        database = 'db'
                    },
                    @{
                        name = 'sql-mi'
                        cloud = 'azure'
                        service = 'sql-managed-instance'
                        instance_name = 'sqlmi'
                    },
                    @{
                        name = 'single'
                        cloud = 'azure'
                        service = 'single-server'
                        server_name = 'single'
                        sub_engine = 'postgres'
                    }
                )
            } | ConvertTo-Json
            Set-Content -Path $testFile -Value $json

            $result = Import-TargetConfig -Path $testFile
            $result.Count | Should -Be 6
            $result[0].service | Should -Be 'postgres-flexible'
            $result[5].service | Should -Be 'single-server'
        }
    }
}

AfterAll { Remove-Module DbMetrics -ErrorAction SilentlyContinue }
