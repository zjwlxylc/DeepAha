import json
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import select
from .models import Source, SourceProfile, Audit, Task, Account, ImportRecord, Meta, Opportunity, Identity, now, uid
from .adapter import safe_url, text, hash_json
from .auth import aware
from .errors import Problem

class SourcesMixin:
    def _source(self,s,id):
        row=s.get(Source,id)
        if not row:raise Problem('来源不存在',404)
        p=s.get(SourceProfile,id)
        if not p:
            # Legacy metadata remains read-only until explicitly adopted through CLI.
            return {'id':str(row.source_id),'name':row.authority_name,'url':row.canonical_url,'active':row.active,'tier':row.tier,
             'enabled':False,'allowed_hosts':[urlsplit(row.canonical_url).hostname], 'brief':'','policy_version':0,
             'interval_hours':0,'last_success':None,'last_failure':None,'legacy':True}
        return {'id':str(row.source_id),'name':row.authority_name,'url':row.canonical_url,'active':row.active,'tier':row.tier,
         'enabled':p.scheduling_enabled,'allowed_hosts':p.allowed_hosts,'brief':p.brief,'policy_version':p.policy_version,
         'interval_hours':p.interval_hours,'last_success':p.last_success.isoformat() if p.last_success else None,
         'last_failure':p.last_failure.isoformat() if p.last_failure else None,'legacy':False,
         'intelligence':p.research_asset if isinstance(p.research_asset,dict) and p.research_asset.get('candidate_revision_id') else None}
    def add_source(self,name,url,*,actor,brief='',allowed_hosts=None,tier='OFFICIAL_PRIMARY'):
        url=safe_url(url)
        if not url or not text(name,300).strip():raise Problem('请填写机构名称和有效公开网址')
        if tier not in ('OFFICIAL_PRIMARY','OFFICIAL_AGGREGATOR','TRUSTED_SECONDARY','COMMUNITY_SIGNAL'):raise Problem('来源类型不正确')
        host=urlsplit(url).hostname
        hosts=list(dict.fromkeys([host]+(allowed_hosts or [])))
        for h in hosts:
            u=safe_url('https://'+str(h))
            if not u or urlsplit(u).hostname!=h or urlsplit(u).path not in ('','/'):raise Problem('允许域名格式不正确')
        with self.db.tx() as s:
            self._account(s,actor,'operator')
            row=s.scalar(select(Source).where(Source.canonical_url==url))
            if row:
                p=s.get(SourceProfile,row.source_id)
                if p:return self._source(s,row.source_id)
                # Explicit adoption; does not alter original identity or trust tier.
            else:
                id=uid();row=Source(source_id=id,public_id='src_'+id.replace('-',''),canonical_url=url,authority_name=text(name,300),tier=tier)
                s.add(row);s.flush()
            s.add(SourceProfile(source_id=row.source_id,allowed_hosts=hosts,brief=text(brief,20000)))
            self._audit(s,actor,'ADOPT_SOURCE',str(row.source_id),'登记来源及调查建议');s.flush()
            return self._source(s,row.source_id)
    def list_sources(self,*,actor,offset=0,limit=50):
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            rows=s.scalars(select(Source).order_by(Source.authority_name,Source.source_id).offset(offset).limit(min(limit,50)))
            return [self._source(s,r.source_id) for r in rows]
    def source_status(self,id,enabled,reason,*,actor,expected_version=None):
        if not text(reason,1000).strip():raise Problem('请填写操作原因')
        with self.db.tx() as s:
            self._account(s,actor,'operator');self._source(s,id)
            p=s.get(SourceProfile,id)
            if not p:raise Problem('此来源尚未接入当前调查路线',409)
            if expected_version is not None and expected_version!=p.policy_version:raise Problem('来源配置已变化，请刷新',409)
            changed=p.scheduling_enabled!=bool(enabled)
            p.scheduling_enabled=bool(enabled)
            if changed:
                p.policy_version+=1
                self._scout_source_event(s,id,bool(enabled))
            self._audit(s,actor,'SOURCE_RESUME' if enabled else 'SOURCE_PAUSE',id,text(reason,1000))
            s.flush();return self._source(s,id)
    def schedule_source(self,id,hours,*,actor):
        if hours!=0 and not 6<=hours<=720:raise Problem('检查间隔应为6至720小时；0表示不自动检查')
        with self.db.tx() as s:
            self._account(s,actor,'operator')
            p=s.get(SourceProfile,id)
            if not p:raise Problem('来源未接入',404)
            p.interval_hours=hours;p.next_due=now()+timedelta(hours=hours) if hours else None
            key='source_schedule:'+str(id)
            binding=s.get(Meta,key)
            if binding:binding.value=actor
            else:s.add(Meta(key=key,value=actor))
            self._audit(s,actor,'SOURCE_SCHEDULE',id,str(hours))
        return {'interval_hours':hours}
    def import_sources(self,asset,*,actor):
        if not isinstance(asset,dict):raise Problem('资产包须为JSON对象')
        if str(asset.get('schema_version','')).startswith('deepaha.'):
            raise Problem('请在来源资产入口上传研究文件，研究建议不能由旧入口直接登记为来源',409,'USE_SCOUT_INTAKE')
        if len(json.dumps(asset,ensure_ascii=False))>2_000_000:raise Problem('来源资产包过大',413)
        d=hash_json(asset)
        with self.db.tx(False) as s:
            self._account(s,actor,'operator')
            old=s.get(ImportRecord,d)
            if old:return old.receipt
        if 'sources' not in asset and 'source_candidates' not in asset:
            raise Problem('未找到 sources 或 source_candidates 来源数组；原研究文件未导入')
        values=asset.get('sources',asset.get('source_candidates',[]))
        if not isinstance(values,list) or len(values)>1000:raise Problem('来源清单格式不正确')
        imported=[];skipped=[]
        # Each source has its own transaction. The final receipt records partial results;
        # repeat imports are idempotent by canonical URL, never an auto investigation.
        for i,v in enumerate(values):
            if not isinstance(v,dict):skipped.append({'index':i,'reason':'条目不是对象'});continue
            url=v.get('seed_url') or v.get('url') or v.get('canonical_url') or v.get('recommended_seed')
            name=v.get('name') or v.get('source_name') or v.get('institution')
            try:
                with self.db.tx(False) as before:
                    existed=before.scalar(select(Source).where(Source.canonical_url==url)) is not None
                r=self.add_source(name or '',url,actor=actor,brief=text(v.get('brief') or v.get('acquisition_brief') or '',20000))
                with self.db.tx() as s:
                    p=s.get(SourceProfile,r['id']);p.research_asset=v
                    if not existed:p.scheduling_enabled=False
                imported.append({'index':i,'source_id':r['id'],'name':r['name']})
            except Problem as e:skipped.append({'index':i,'reason':e.message})
        receipt={'digest':d,'imported':imported,'skipped':skipped,'tasks_created':0,'status':'PARTIAL' if skipped else ('IMPORTED' if imported else 'NO_CHANGES')}
        with self.db.tx() as s:
            if not s.get(ImportRecord,d):s.add(ImportRecord(digest=d,actor=actor,asset=asset,receipt=receipt))
            self._audit(s,actor,'IMPORT_SOURCE_ASSET',d,f'{len(imported)}个来源；未创建调查任务')
        return receipt

    def adopt_identity(self,source_id,notice_url,public_id,*,actor,source_record_key=None):
        """Controlled migration mapping only. No publication or review is implied."""
        url=safe_url(notice_url)
        if not url:raise Problem('请提供原公告的准确公开网址')
        with self.db.tx() as s:
            self._account(s,actor,'operator');source=self._source(s,source_id)
            if urlsplit(url).hostname not in source['allowed_hosts']:raise Problem('原公告不在来源允许范围')
            if url.rstrip('/')==source['url'].rstrip('/'):raise Problem('不能用来源首页代替明确的原公告身份')
            opp=s.scalar(select(Opportunity).where(Opportunity.public_id==public_id))
            if not opp:raise Problem('原机会标识不存在',404)
            key=hash_json([source_id,url,text(source_record_key,256)]) if source_record_key else hash_json([source_id,url])
            existing=s.scalar(select(Identity).where(Identity.source_id==source_id,Identity.source_key==key))
            if existing and existing.opportunity_id!=opp.opportunity_id:raise Problem('来源身份已关联其他机会，拒绝覆盖',409)
            if not existing:s.add(Identity(source_id=source_id,source_key=key,opportunity_id=opp.opportunity_id))
            self._audit(s,actor,'ADOPT_EXISTING_IDENTITY',public_id,'受控迁移关联；不批准任何内容')
        return {'public_id':public_id,'source_key':key,'published':False}
