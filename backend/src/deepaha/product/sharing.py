"""Public sharing presentation only. Never reads profile, review or order content."""
from html import escape
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl
import hashlib
import io
import json
import re
from PIL import Image, ImageOps, UnidentifiedImageError
from .models import Meta
from .errors import Problem

KEY='share_settings_v1'
DEFAULT={'version':0,'origin':'https://deepaha.com','title':'机会星图｜找到真正属于你的机会',
         'description':'汇聚官方机会，结合你的关注方向，持续发现、筛选与跟踪值得行动的机会。',
         'cover':'default-wide.jpg','square':'default-square.jpg','wechat_enabled':False,
         'verification_name':'','verification_text':''}
ASSET=re.compile(r'^[0-9a-f]{64}\.jpg$')
VERIFY=re.compile(r'^MP_verify_[A-Za-z0-9]{1,80}\.txt$')
PUBLIC={'/','/services','/app/overview','/about','/share'}
OPP=re.compile(r'^/(?:share/opportunity|app/opportunity)/([A-Za-z0-9_-]{1,128})$')
MAX_IMAGE=5*1024*1024


def origin(value):
    try:
        p=urlsplit(value)
        if p.scheme!='https' or p.username or p.password or p.port is not None or p.path not in ('','/') or p.query or p.fragment:raise ValueError()
        host=p.hostname or ''
        if p.netloc.lower()!=host or not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,250}[a-z0-9])?',host):raise ValueError()
        if '.' not in host or host.split('.')[-1].isdigit() or host.endswith(('.local','.internal','.localhost','.test','.invalid')):raise ValueError()
        import ipaddress
        try:ipaddress.ip_address(host)
        except ValueError:pass
        else:raise ValueError()
        if any(not part or len(part)>63 or part.startswith('-') or part.endswith('-') for part in host.split('.')):raise ValueError()
        return 'https://'+host
    except ValueError:raise Problem('请填写公开HTTPS域名，不包含路径、端口、账号或查询参数',400,'INVALID_SHARE_ORIGIN') from None


def get_config(p):
    with p.db.tx(False) as s:
        record=s.get(Meta,KEY)
        return {**DEFAULT,**(json.loads(record.value) if record else {})}


def asset_file(p,static,name):
    if name in ('default-wide.jpg','default-square.jpg'):return static/'share'/name
    if not ASSET.fullmatch(name):raise Problem('封面标识不正确',400)
    base=(p.object_root/'share').resolve();f=base/name
    if f.is_symlink() or not f.is_file() or f.resolve().parent!=base:raise Problem('封面文件不存在',404)
    return f


def asset_url(c,name):return c['origin']+'/share-assets/'+name


def save_config(p,static,actor,data):
    data=dict(data);data['origin']=origin(data['origin'])
    for key,limit in [('title',80),('description',220)]:
        value=data[key].strip()
        if not value or len(value)>limit or any(ord(x)<32 for x in value):raise Problem('分享标题或描述长度/字符不正确')
        data[key]=value
    for key in ('cover','square'):
        asset_file(p,static,data[key])
        expected=(1200,630) if key=='cover' else (600,600)
        try:
            with Image.open(asset_file(p,static,data[key])) as image:
                if image.size!=expected:raise Problem('请为横版封面/方形缩略图选择对应尺寸')
        except OSError:raise Problem('封面不可读取') from None
    if data['verification_name'] or data['verification_text']:
        if not VERIFY.fullmatch(data['verification_name']) or not re.fullmatch('[A-Za-z0-9_-]{1,256}',data['verification_text']):raise Problem('域名验证文件名或内容不正确')
    with p.db.tx() as s:
        p._account(s,actor,'operator')
        old=s.get(Meta,KEY);c={**DEFAULT,**(json.loads(old.value) if old else {})}
        if data['version']!=c['version']:raise Problem('分享设置已变化，请刷新后重试',409,'STALE_VERSION')
        data['version']+=1
        encoded=json.dumps(data,ensure_ascii=False)
        if old:old.value=encoded
        else:s.add(Meta(key=KEY,value=encoded))
        p._audit(s,actor,'UPDATE_SITE_SHARING','site','修改公开分享样式；不包含任何账号密钥')
    return data


def store_cover(p,raw,kind):
    if len(raw)>MAX_IMAGE:raise Problem('图片不能超过5MB',413,'COVER_TOO_LARGE')
    try:
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('PNG','JPEG','WEBP') or source.width*source.height>16_000_000 or source.width<200 or source.height<200:
                raise ValueError()
            source.verify()
        with Image.open(io.BytesIO(raw)) as source:
            source=ImageOps.exif_transpose(source).convert('RGBA')
            base=Image.new('RGB',source.size,'white');base.paste(source,mask=source.getchannel('A'))
            base=ImageOps.fit(base,(1200,630) if kind=='wide' else (600,600),method=Image.Resampling.LANCZOS)
            out=io.BytesIO();base.save(out,'JPEG',quality=91,optimize=True)
            result=out.getvalue()
    except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombError,Image.DecompressionBombWarning):
        raise Problem('请选择有效PNG/JPEG/WEBP图片，至少200×200且不超过1600万像素',400,'INVALID_COVER') from None
    name=hashlib.sha256(result).hexdigest()+'.jpg'
    folder=p.object_root/'share';folder.mkdir(parents=True,exist_ok=True)
    f=folder/name
    if f.exists():
        if f.is_symlink() or hashlib.sha256(f.read_bytes()).hexdigest()+'.jpg'!=name:raise Problem('封面完整性检查失败',409)
    else:
        # The filename is content-addressed. Atomic replace prevents partial public reads.
        import tempfile,os
        fd,tmp=tempfile.mkstemp(prefix='.upload-',dir=folder)
        try:
            with os.fdopen(fd,'wb') as h:h.write(result);h.flush();os.fsync(h.fileno())
            os.replace(tmp,f)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return {'asset':name,'bytes':len(result),'width':base.width,'height':base.height}


def metadata(p,settings,path):
    """path is a route, not a URL. Unknown/private routes receive no OG metadata."""
    c=get_config(p);m=OPP.fullmatch(path)
    if path not in PUBLIC and not m:return None
    title,description=c['title'],c['description'];target='/app/overview';share='/share'
    if m:
        strict=path.startswith('/share/')
        if not settings.public_catalog:
            if strict:raise Problem('公开机会不存在',404,'SHARE_NOT_FOUND')
            return None
        try:detail=p.detail(m[1])
        except Problem:
            if strict:raise Problem('该机会暂不可公开分享',404,'SHARE_NOT_FOUND') from None
            return None
        if detail.get('status') not in ('CURRENT','UPDATE_PENDING'):
            if strict:raise Problem('该机会已停止公开展示',410,'SHARE_WITHDRAWN')
            return None
        parent=detail.get('parent_announcement') or {}
        parent_title=parent.get('title','') if isinstance(parent,dict) else ''
        title=(detail.get('title') or parent_title or c['title'])[:140]
        if parent_title and parent_title not in title:title=(parent_title+' · '+title)[:140]
        summary=detail.get('summary') or '查看公开条件、原始依据与申请入口。'
        description=(('资料有更新待收录，请核对详情备注。' if detail.get('status')=='UPDATE_PENDING' else '')+(str(summary).strip() or c['description']))[:220]
        target='/app/opportunity/'+m[1];share='/share/opportunity/'+m[1]
    else:
        if path=='/services':target='/services'
    return {'title':title,'description':description,'image':asset_url(c,c['cover']),
            'square':asset_url(c,c['square']),'url':c['origin']+path,
            'share_url':c['origin']+share+'?sv='+str(c['version']),
            'target':target,'version':c['version'],'wechat_enabled':c['wechat_enabled']}


def tags(value):
    if value is None:return '<meta name="robots" content="noindex,nofollow">'
    attrs={'og:type':'website','og:locale':'zh_CN','og:site_name':'DeepAha 机会星图',
           'og:title':value['title'],'og:description':value['description'],'og:url':value['url'],
           'og:image':value['image'],'og:image:secure_url':value['image'],'og:image:type':'image/jpeg',
           'og:image:width':'1200','og:image:height':'630','og:image:alt':'DeepAha 机会星图品牌封面'}
    return '<title>'+escape(value['title'])+'</title><meta name="description" content="'+escape(value['description'],quote=True)+'"><link rel="canonical" href="'+escape(value['url'],quote=True)+'">'+''.join('<meta property="'+k+'" content="'+escape(str(v),quote=True)+'">' for k,v in attrs.items())


def apply_html(html,value):
    html=re.sub(r'<title>.*?</title>','',html,flags=re.S)
    html=re.sub(r'<meta name="description"[^>]*>','',html)
    return html.replace('</head>',(tags(value) if value else '<title>机会星图 · DeepAha</title>'+tags(None))+'</head>')


def landing(value):
    e=lambda x:escape(str(x),quote=True)
    # No inline script or secret settings. All public data goes in escaped attributes.
    return f'''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">{tags(value)}<link rel="icon" href="/product/brand-logo.png"><link rel="stylesheet" href="/product/share-page.css"></head><body><main class="share-card" data-share-url="{e(value['share_url'])}" data-share-square="{e(value['square'])}" data-wechat="{str(value['wechat_enabled']).lower()}"><a class="share-brand" href="/"><img src="/product/brand-logo.png" width="42" height="42" alt="DeepAha">DeepAha <span>机会星图</span></a><img class="share-cover" src="{e(urlsplit(value['image']).path)}" width="1200" height="630" alt="机会星图品牌封面"><div class="share-copy"><p class="kicker">GO DEEP. FIND YOURS.</p><h1>{e(value['title'])}</h1><p id="share-description">{e(value['description'])}</p><a class="primary" href="{e(value['target'])}">查看机会星图 <span aria-hidden="true">↗</span></a><button id="copy-share" type="button">复制分享链接</button><p id="share-status" role="status">在微信中打开后，可通过右上角菜单发送给朋友。</p><details><summary>查看分享链接</summary><input id="share-link" value="{e(value['share_url'])}" readonly aria-label="分享链接"></details></div></main><footer>世界不缺机会，值得找到属于你的那一个。</footer><script src="/product/share-page.js" defer></script></body></html>'''


def signature_url(url,c):
    if len(url)>2048 or any(ord(x)<32 for x in url) or '\\' in url:raise Problem('签名地址不正确',400,'INVALID_SHARE_URL')
    try:p=urlsplit(url)
    except ValueError:raise Problem('签名地址不正确',400,'INVALID_SHARE_URL') from None
    base=urlsplit(c['origin'])
    if p.scheme!=base.scheme or p.netloc!=base.netloc or (p.path!='/share' and not re.fullmatch(r'/share/opportunity/[A-Za-z0-9_-]{1,128}',p.path)):
        raise Problem('只能为本站公开分享页生成配置',400,'INVALID_SHARE_URL')
    # WeChat itself can append these ordinary routing parameters. Never sign a private endpoint.
    allowed={'sv','from','isappinstalled','scene','share_source','singlemessage','wxfid','wx_header','clicktime','enterid'}
    pairs=parse_qsl(p.query,keep_blank_values=True)
    if len(pairs)>12 or any(k not in allowed or len(v)>256 for k,v in pairs):raise Problem('分享地址参数不正确',400,'INVALID_SHARE_URL')
    return urlunsplit((p.scheme,p.netloc,p.path,p.query,''))
