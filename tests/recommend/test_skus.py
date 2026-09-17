from db_metrics.recommend.skus import capacity_for, Capacity

def test_azure_known_sku():
    inv = {"server": {"sku": {"name": "Standard_D4ds_v5"}}}
    cap = capacity_for("azure", "postgres-flexible", inv)
    assert cap.known is True
    assert cap.vcpu == 4 and cap.ram_gb == 16

def test_azure_unknown_sku_is_graceful():
    inv = {"server": {"sku": {"name": "Standard_ZZ99_bogus"}}}
    cap = capacity_for("azure", "postgres-flexible", inv)
    assert cap.known is False
    assert cap.vcpu is None and cap.ram_gb is None
    assert "Standard_ZZ99_bogus" in cap.source_label

def test_aws_rds_class():
    inv = {"server": {"class": "db.m6i.large"}}
    cap = capacity_for("aws", "rds", inv)
    assert cap.known is True
    assert cap.vcpu == 2 and cap.ram_gb == 8

def test_aws_aurora_writer_member_class():
    inv = {"server": {"members": [
        {"identifier": "r", "is_writer": False, "class": "db.r6g.large"},
        {"identifier": "w", "is_writer": True, "class": "db.r6g.xlarge"}]}}
    cap = capacity_for("aws", "aurora", inv)
    assert cap.ram_gb == 32 and cap.vcpu == 4

def test_aws_aurora_serverless_v2_from_max_acu():
    inv = {"server": {"members": [], "serverless_v2": {"min_acu": 2, "max_acu": 16}}}
    cap = capacity_for("aws", "aurora", inv)
    assert cap.known is True and cap.ram_gb == 32

def test_unknown_cloud():
    assert capacity_for("gcp", "x", {}).known is False
