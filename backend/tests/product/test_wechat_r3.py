import json,hashlib
import httpx,pytest
from deepaha.product.wechat_share import WeChatShare,signature
from deepaha.product.errors import Problem


def test_sha1_reference_vector():
    expected=hashlib.sha1(b'jsapi_ticket=ticket&noncestr=nonce&timestamp=123&url=https://deepaha.com/share?sv=2').hexdigest()
    assert signature('ticket','nonce',123,'https://deepaha.com/share?sv=2')==expected


def test_disabled_no_network(tmp_path):
    w=WeChatShare(tmp_path,transport=httpx.MockTransport(lambda r:pytest.fail('unexpected network')))
    assert w.sign('https://deepaha.com/share','ip')['enabled'] is False
    assert not list(tmp_path.iterdir())


def test_ticket_cache_shared_rotation_rate_limit_and_no_secrets(tmp_path,monkeypatch):
    monkeypatch.setenv('DEEPAHA_WECHAT_APP_ID','wx123456789abc');monkeypatch.setenv('DEEPAHA_WECHAT_APP_SECRET','secret-first')
    calls=[]
    def handler(r):
        calls.append(r.url.path)
        if r.url.path.endswith('/stable_token'):
            assert r.method=='POST';return httpx.Response(200,json={'access_token':'private-token','expires_in':7200})
        assert r.url.host=='api.weixin.qq.com'
        return httpx.Response(200,json={'errcode':0,'ticket':'private-ticket','expires_in':7200})
    t=httpx.MockTransport(handler);w=WeChatShare(tmp_path,transport=t)
    data=w.sign('https://deepaha.com/share?sv=2','ip')
    assert data['signature']==signature('private-ticket',data['nonceStr'],data['timestamp'],'https://deepaha.com/share?sv=2')
    assert 'private' not in json.dumps(data) and 'secret-first' not in json.dumps(data)
    other=WeChatShare(tmp_path,transport=t)
    assert other.sign('https://deepaha.com/share','ip')['enabled']
    assert len(calls)==2
    monkeypatch.setenv('DEEPAHA_WECHAT_APP_SECRET','secret-second');other.sign('https://deepaha.com/share','ip')
    assert len(calls)==4
    for _ in range(29):w.sign('https://deepaha.com/share','ip')
    with pytest.raises(Problem) as e:w.sign('https://deepaha.com/share','ip')
    assert e.value.status==429
    assert all('secret-first' not in f.read_text() for f in tmp_path.glob('*.json'))


def test_errors_sanitized_and_cooldown_persists(tmp_path,monkeypatch):
    monkeypatch.setenv('DEEPAHA_WECHAT_APP_ID','wx123456789abc');monkeypatch.setenv('DEEPAHA_WECHAT_APP_SECRET','verysecret')
    calls=[]
    def handler(r):calls.append(r);return httpx.Response(200,json={'errcode':40013,'errmsg':'verysecret private-address'})
    w=WeChatShare(tmp_path,transport=httpx.MockTransport(handler))
    for _ in range(2):
        with pytest.raises(Problem) as e:w.sign('https://deepaha.com/share','ip')
        assert 'verysecret' not in str(e.value)
    assert len(calls)==1
