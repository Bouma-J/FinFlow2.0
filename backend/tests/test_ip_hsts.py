from apps.common.https import host_is_ipv4


def test_host_is_ipv4_accepts_urls_and_ports():
    assert host_is_ipv4("203.0.113.10")
    assert host_is_ipv4("https://203.0.113.10")
    assert host_is_ipv4("https://203.0.113.10:9000/docs")
    assert host_is_ipv4("http://192.168.1.20/")


def test_host_is_ipv4_rejects_domains_and_garbage():
    assert not host_is_ipv4("https://finflow.example.tld")
    assert not host_is_ipv4("localhost")
    assert not host_is_ipv4("")
    assert not host_is_ipv4("10.0.0")
    assert not host_is_ipv4("256.1.1.1")
