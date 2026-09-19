"""Local encrypted credentials; production uses host-injected secrets only."""
import json
import os
import sys
import tempfile
from dataclasses import dataclass,field
from pathlib import Path
from cryptography.fernet import Fernet,InvalidToken
from .errors import Problem

@dataclass
class Settings:
    data_dir: Path=field(default_factory=lambda:Path(os.getenv('DEEPAHA_DATA_DIR',str(Path.home()/'deepaha-data'))).resolve())
    database_url: str=''
    mode: str='local'
    public_catalog: bool=False
    allow_registration: bool=False
    secure_cookie: bool=False
    allowed_hosts: list=field(default_factory=lambda:['localhost','127.0.0.1','testserver'])
    origins: list=field(default_factory=list)
    def __post_init__(self):
        self.data_dir=Path(self.data_dir).resolve()
        if not self.database_url:self.database_url='sqlite:///'+str(self.data_dir/'deepaha.db')
    @classmethod
    def from_env(cls):
        value=cls(database_url=os.getenv('DEEPAHA_DATABASE_URL',''),mode=os.getenv('DEEPAHA_MODE','local'),
          public_catalog=os.getenv('DEEPAHA_PUBLIC_CATALOG')=='1',allow_registration=os.getenv('DEEPAHA_ALLOW_REGISTRATION')=='1',
          secure_cookie=os.getenv('DEEPAHA_SECURE_COOKIE')=='1',allowed_hosts=os.getenv('DEEPAHA_ALLOWED_HOSTS','localhost,127.0.0.1').split(','),
          origins=[x for x in os.getenv('DEEPAHA_ALLOWED_ORIGINS','').split(',') if x])
        if value.mode not in ('local','production'):raise RuntimeError('DEEPAHA_MODE must be local or production')
        if value.mode=='production':
            if not value.secure_cookie or '*' in value.allowed_hosts or not value.origins:raise RuntimeError('Production requires secure cookies, explicit hosts and origins')
            if not value.database_url.startswith('postgresql'):raise RuntimeError('Production requires PostgreSQL; SQLite is for local use')
        return value

class ConnectionConfig:
    def __init__(self,directory,mode='local'):self.root=Path(directory);self.mode=mode
    def _fernet(self,create=False):
        path=self.root/'.credential-key'
        if not path.exists():
            if not create:return None
            self.root.mkdir(parents=True,exist_ok=True)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(Fernet.generate_key())
        return Fernet(path.read_bytes())
    def load(self):
        if os.getenv('DEEPAHA_WMA_API_KEY'):
            return {'api_key':os.environ['DEEPAHA_WMA_API_KEY'],'agent_id':os.getenv('DEEPAHA_WMA_AGENT_ID',''),
             'source_app':os.getenv('DEEPAHA_WMA_SOURCE_APP','deepaha-dail'),'enabled':os.getenv('DEEPAHA_WMA_ENABLED')=='1','origin':'HOST'}
        if self.mode=='production':return {}
        path=self.root/'wma-connection.enc'
        if not path.exists():return {}
        try:
            f=self._fernet()
            if not f and not path.read_bytes().startswith(b'DPAPI1\x00'):raise InvalidToken()
            encrypted=path.read_bytes()
            if encrypted.startswith(b'DPAPI1\x00'):
                from .windows_secrets import WindowsDpapiProtector
                clear=WindowsDpapiProtector().unprotect(encrypted[7:])
            else:clear=f.decrypt(encrypted)
            data=json.loads(clear)
            data['origin']='LOCAL_ENCRYPTED';return data
        except (InvalidToken,ValueError,OSError,RuntimeError):raise Problem('连接配置无法解密，请重新保存',503,'CONFIG_UNREADABLE')
    def save(self,agent_id,source_app,api_key,enabled):
        import re
        if self.mode!='local':raise Problem('此部署的密钥由宿主管理，不能通过网页修改',403)
        for v in (agent_id,source_app):
            if not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',v):raise Problem('Agent或应用标识格式不正确')
        old=self.load()
        if old.get('origin')=='HOST':raise Problem('当前连接由环境配置管理',409)
        key=api_key or old.get('api_key')
        if not isinstance(key,str) or not 8<=len(key)<=4096:raise Problem('请填写有效连接密钥')
        data={'agent_id':agent_id,'source_app':source_app,'api_key':key,'enabled':bool(enabled)}
        clear=json.dumps(data).encode()
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        if sys.platform=='win32':
            from .windows_secrets import WindowsDpapiProtector,WindowsDirectoryHardener
            try:
                WindowsDirectoryHardener().harden(self.root)
                encrypted=b'DPAPI1\x00'+WindowsDpapiProtector().protect(clear)
            except RuntimeError:raise Problem('Windows凭据保护失败，未保存密钥',503,'SECRET_PROTECTION_FAILED') from None
        else:
            os.chmod(self.root,0o700)
            encrypted=self._fernet(True).encrypt(clear)
        fd,name=tempfile.mkstemp(prefix='.wma-',dir=self.root)
        try:
            with os.fdopen(fd,'wb') as f:f.write(encrypted);f.flush();os.fsync(f.fileno())
            os.replace(name,self.root/'wma-connection.enc')
        finally:
            if os.path.exists(name):os.unlink(name)
    def public(self):
        c=self.load()
        return {'agent_id':c.get('agent_id',''),'source_app':c.get('source_app','deepaha-dail'),
          'configured':bool(c.get('api_key') and c.get('agent_id')),'enabled':bool(c.get('enabled')),
          'secret_present':bool(c.get('api_key')),'origin':c.get('origin','NONE'),'editable':self.mode=='local' and c.get('origin')!='HOST'}
    def factory(self):
        c=self.load()
        if not c.get('enabled') or not c.get('api_key') or not c.get('agent_id'):return None
        from pydantic import SecretStr
        from deepaha.investigations.wma import WmaBinding,DirectWmaClient
        return lambda:DirectWmaClient(WmaBinding(api_key=SecretStr(c['api_key']),agent_id=c['agent_id'],source_app=c['source_app'],agent_version='1.0.0'))
