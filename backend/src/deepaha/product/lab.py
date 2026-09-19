"""SG7 Opportunity Lab: isolated evaluation assets and voluntary Founding User telemetry.

This module deliberately does NOT modify production Opportunity, Publication,
VerifiedFact, Rule, Eligibility or review decisions. Synthetic twins and lab
annotations are evaluation inputs only.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from sqlalchemy import func, select

from .adapter import hash_json, text
from .errors import Problem
from .models import (
    Account, CatalogTarget, FeedbackCandidate, LabEnrollment, LabExposure, LabGoldCase,
    LabPairTruth, LabRun, LabRunResult, LabTwin, Opportunity, TargetActionEvent, TargetFeedback, now,
)

CONSENT_VERSION='sg7-opportunity-lab-v1'
TRUTH_ORIGINS={'ENGINEERING_FIXTURE','OPERATOR_ANNOTATED','INDEPENDENT_HUMAN_GOLD'}
SPLITS={'CALIBRATION','VALIDATION','LOCKED_ACCEPTANCE'}
EXPECTED={'ELIGIBLE','LIKELY_ELIGIBLE','UNCERTAIN','INELIGIBLE'}
EXPECTED_RECOMMENDATION={'FEATURE','EXPLORE','HOLD'}
RUN_KINDS={'CATALOG_SAFETY','GOLD_BENCHMARK'}
LAB_VERSION=2
TWIN_VERSION=2


def _safe_ratio(num:int,den:int):
    return round(num/den,4) if den else None


def _iso(v):
    return v.isoformat() if v else None


def _recommendation_class(priority_band:str,qualification_gate:str) -> str:
    """Coarse human-readable recommendation class for SG7 evaluation.

    SG7 deliberately evaluates broad product behavior rather than pretending
    the internal numeric rank is a stable human truth label.
    """
    if qualification_gate=='HOLD_FOR_CONFIRMATION' or priority_band=='NOT_RECOMMENDED':
        return 'HOLD'
    if priority_band in {'ACT_NOW','HIGH'}:
        return 'FEATURE'
    return 'EXPLORE'


class LabMixin:
    def _lab_twin_profiles(self):
        majors=[
            ('广告学',['写作','内容策划'],['AI产品运营','品牌传播']),
            ('计算机科学与技术',['Python','数据分析'],['人工智能','软件开发']),
            ('机械工程',['CAD','工程实践'],['新能源','先进制造']),
            ('自动化',['控制基础','Python'],['机器人','智能制造']),
            ('法学',['检索','表达'],['公共服务','合规']),
            ('汉语言文学',['写作','编辑'],['内容传播','公共文化']),
            ('金融学',['Excel','分析'],['金融科技','国企']),
            ('护理学',['沟通','健康知识'],['医疗健康','公共服务']),
            ('新闻学',['采访','写作'],['内容策略','媒体运营']),
            ('视觉传达设计',['设计','AIGC工具'],['数字创意','品牌设计']),
            ('电子信息工程',['嵌入式基础','Python'],['半导体','人工智能']),
            ('土木工程',['工程制图','项目协作'],['城市建设','国企']),
            ('材料科学与工程',['实验','数据整理'],['新能源','科研']),
            ('生物技术',['实验','文献阅读'],['生物医药','科研']),
            ('工商管理',['组织协调','Excel'],['产品运营','企业管理']),
            ('市场营销',['策划','用户洞察'],['AI产品运营','品牌传播']),
            ('英语',['英语六级','写作'],['国际项目','内容传播']),
            ('数学与应用数学',['数学建模','Python'],['数据分析','科研']),
            ('电气工程及其自动化',['电气基础','工程实践'],['国家电网','新能源']),
            ('公共事业管理',['政策阅读','组织协调'],['事业单位','公共服务']),
        ]
        cities=['杭州','宁波','上海','北京','深圳','广州','南京','武汉','成都','长沙']
        types=['STATE_OWNED_ENTERPRISE_JOB','PUBLIC_INSTITUTION_JOB','YOUTH_DEVELOPMENT_PROGRAM','COMPETITION','RESEARCH_PROGRAM','SCHOLARSHIP','POSTGRAD_RECOMMENDATION','YOUTH_POLICY_BENEFIT']
        educations=[('专科','无'),('本科','学士'),('本科','学士'),('硕士研究生','硕士')]
        statuses=['在校生','在校生','应届毕业生','非应届']
        constraints=['不接受长期异地','时间有限，优先短周期机会','希望低成本参与','家庭更偏好稳定路径','需要兼顾课程学习','']
        archetypes=['稳定落点','增长赛道','履历跃迁','升学跃迁','城市红利','探索型']
        rows=[]
        for i in range(100):
            major,skills,directions=majors[i%len(majors)]
            education,degree=educations[i%len(educations)]
            archetype=archetypes[i%len(archetypes)]
            # V2 deliberately crosses education and graduation-year axes instead
            # of deriving both from i%4. This avoids synthetic coverage artifacts
            # such as every 2027 graduate sharing the same education bucket.
            graduation=2027+((i//4)%4)
            chosen_type=types[i%len(types)]
            second_type=types[(i+3)%len(types)]
            profile={
                'display_name':'',
                'education':education,'degree':degree,'major':major,'major_code':'',
                'graduation_year':graduation,'student_status':statuses[i%len(statuses)],
                'birth_date':'','hukou_region':cities[(i+2)%len(cities)],'nationality':'中国',
                'political_status':'','work_experience_years':0.0,'certificates':[],
                'professional_title':'','language_certificates':['大学英语六级'] if i%5==0 else [],
                'team_size':3 if i%7==0 else None,
                'cities':[cities[i%len(cities)],cities[(i+1)%len(cities)]],
                'interests':directions,'goals':[f'{archetype}机会','积累真实经历'],
                'skills':skills,'career_directions':directions,
                'constraints':[constraints[i%len(constraints)]] if constraints[i%len(constraints)] else [],
                'opportunity_types':[chosen_type,second_type],
                'region_preference_mode':['FLEXIBLE','PREFERRED','STRICT'][i%3],
                'personalization_enabled':True,
            }
            rows.append((f'TWIN-{i+1:03d}',f'合成青年 {i+1:03d}',archetype,profile))
        return rows

    def lab_seed_twins(self,*,actor):
        with self.db.tx() as s:
            self._account(s,actor)
            existing={x.twin_key:x for x in s.scalars(select(LabTwin).where(LabTwin.version==TWIN_VERSION))}
            created=0;unchanged=0
            for key,label,archetype,profile in self._lab_twin_profiles():
                digest=hash_json(profile);row=existing.get(key)
                if row:
                    if row.profile_hash!=digest:
                        raise Problem('已有数字分身版本内容不一致，请新建版本而不是覆盖',409,'LAB_TWIN_DRIFT')
                    unchanged+=1;continue
                s.add(LabTwin(twin_key=key,version=TWIN_VERSION,label=label,archetype=archetype,profile=profile,profile_hash=digest,active=True));created+=1
            # Preserve prior twin versions for historical run replay, but only the
            # current version participates in new benchmarks.
            for old in s.scalars(select(LabTwin).where(LabTwin.version!=TWIN_VERSION,LabTwin.active.is_(True))):
                old.active=False
            self._audit(s,actor,'LAB_SEED_TWINS','SG7',f'生成 V{TWIN_VERSION} 合成数字分身：新增 {created}，已存在 {unchanged}；旧版本仅保留历史')
        return {'created':created,'unchanged':unchanged,'total':created+unchanged,'synthetic_only':True,'version':TWIN_VERSION}

    def lab_twins(self,*,actor,offset=0,limit=30):
        limit=min(max(int(limit),1),100);offset=max(int(offset),0)
        with self.db.tx(False) as s:
            self._account(s,actor)
            total=s.scalar(select(func.count()).select_from(LabTwin).where(LabTwin.active.is_(True))) or 0
            rows=list(s.scalars(select(LabTwin).where(LabTwin.active.is_(True)).order_by(LabTwin.twin_key).offset(offset).limit(limit)))
            return {'total':total,'items':[{'id':x.id,'key':x.twin_key,'label':x.label,'archetype':x.archetype,'version':x.version,'profile_hash':x.profile_hash,'profile':x.profile,'synthetic':True} for x in rows]}

    def _lab_current_target(self,s,public_id):
        row=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==public_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(CatalogTarget.created_at.desc(),CatalogTarget.id.desc()))
        if not row:raise Problem('当前机会不存在或已撤回',404)
        return row

    def lab_add_gold_case(self,public_id,*,actor,split='CALIBRATION',truth_origin='OPERATOR_ANNOTATED',annotation=None,attestation_ref=None,lock=False):
        split=str(split or '').upper();truth_origin=str(truth_origin or '').upper()
        if split not in SPLITS:raise Problem('实验分区不正确')
        if truth_origin not in TRUTH_ORIGINS:raise Problem('真值来源不正确')
        if truth_origin=='INDEPENDENT_HUMAN_GOLD' and not (attestation_ref and str(attestation_ref).strip()):
            raise Problem('独立人工 Gold 必须提供可核验的标注证明引用',409,'GOLD_ATTESTATION_REQUIRED')
        annotation=annotation if isinstance(annotation,dict) else {}
        with self.db.tx() as s:
            a=self._account(s,actor);target=self._lab_current_target(s,public_id);opp=s.get(Opportunity,target.opportunity_id)
            existing=s.scalar(select(LabGoldCase).where(LabGoldCase.catalog_target_id==target.id,LabGoldCase.split==split,LabGoldCase.truth_origin==truth_origin))
            if existing:
                if existing.state=='LOCKED':raise Problem('已锁定实验样本不可覆盖',409,'LAB_GOLD_LOCKED')
                row=existing
            else:
                row=LabGoldCase(catalog_target_id=target.id,target_public_id=target.public_id,opportunity_id=target.opportunity_id,
                    publication_id=target.publication_id,revision_id=target.revision_id,snapshot_hash='',snapshot={},split=split,
                    truth_origin=truth_origin,created_by=a.id)
                s.add(row)
            snapshot={'target_id':target.public_id,'catalog_target_id':target.id,'opportunity_id':target.opportunity_id,
                      'publication_id':target.publication_id,'revision_id':target.revision_id,'content':target.content,
                      'opportunity':{'public_id':opp.public_id if opp else None,'type':opp.type if opp else None,'title':opp.canonical_title if opp else None}}
            row.snapshot=snapshot;row.snapshot_hash=hash_json(snapshot);row.annotation=annotation
            row.attestation_ref=text(attestation_ref,160) or None;row.state='LOCKED' if lock else 'DRAFT';row.locked_at=now() if lock else None
            s.flush();case_id=row.id
            self._audit(s,actor,'LAB_GOLD_CASE',case_id,f'实验样本 {target.public_id} {split} {truth_origin} {row.state}；不影响正式事实')
        return self.lab_gold_case(case_id,actor=actor)

    def lab_lock_gold_case(self,case_id,*,actor):
        with self.db.tx() as s:
            self._account(s,actor);row=s.get(LabGoldCase,case_id)
            if not row or row.state=='RETIRED':raise Problem('实验样本不存在',404)
            if row.state=='LOCKED':return {'id':row.id,'state':'LOCKED','already_locked':True}
            if row.truth_origin=='INDEPENDENT_HUMAN_GOLD' and not row.attestation_ref:raise Problem('独立人工 Gold 缺少证明引用',409,'GOLD_ATTESTATION_REQUIRED')
            # Recompute declared snapshot hash rather than silently changing the snapshot.
            if hash_json(row.snapshot)!=row.snapshot_hash:raise Problem('实验样本快照完整性不一致',409,'LAB_SNAPSHOT_DRIFT')
            row.state='LOCKED';row.locked_at=now();self._audit(s,actor,'LAB_GOLD_LOCK',row.id,'锁定实验样本；仅用于 SG7 评估')
        return self.lab_gold_case(case_id,actor=actor)

    def lab_retire_gold_case(self,case_id,*,actor):
        with self.db.tx() as s:
            self._account(s,actor);row=s.get(LabGoldCase,case_id)
            if not row:raise Problem('实验样本不存在',404)
            row.state='RETIRED';row.retired_at=now();self._audit(s,actor,'LAB_GOLD_RETIRE',row.id,'退役 SG7 实验样本，不改变正式机会')
        return {'id':case_id,'state':'RETIRED'}

    def lab_gold_case(self,case_id,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor);x=s.get(LabGoldCase,case_id)
            if not x:raise Problem('实验样本不存在',404)
            return self._lab_gold_public(x)

    def _lab_gold_public(self,x):
        return {'id':x.id,'target_id':x.target_public_id,'catalog_target_id':x.catalog_target_id,'split':x.split,'truth_origin':x.truth_origin,
                'annotation':x.annotation,'attestation_ref':x.attestation_ref,'state':x.state,
                'snapshot_hash':x.snapshot_hash,'created_at':_iso(x.created_at),'locked_at':_iso(x.locked_at),'retired_at':_iso(x.retired_at),
                'counts_as_real_gold':x.state=='LOCKED' and x.truth_origin=='INDEPENDENT_HUMAN_GOLD' and bool(x.attestation_ref)}

    def lab_gold_cases(self,*,actor,offset=0,limit=30):
        limit=min(max(int(limit),1),100);offset=max(int(offset),0)
        with self.db.tx(False) as s:
            self._account(s,actor)
            total=s.scalar(select(func.count()).select_from(LabGoldCase).where(LabGoldCase.state!='RETIRED')) or 0
            rows=list(s.scalars(select(LabGoldCase).where(LabGoldCase.state!='RETIRED').order_by(LabGoldCase.created_at.desc()).offset(offset).limit(limit)))
            return {'total':total,'items':[self._lab_gold_public(x) for x in rows]}

    def lab_catalog_candidates(self,*,actor,q='',limit=30):
        limit=min(max(int(limit),1),100);needle=str(q or '').strip().casefold()
        with self.db.tx(False) as s:
            self._account(s,actor)
            rows=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(CatalogTarget.created_at.desc()).limit(300)))
            out=[]
            for t in rows:
                c=t.content if isinstance(t.content,dict) else {};hay=' '.join(str(c.get(k) or '') for k in ('title','issuer','summary')).casefold()
                if needle and needle not in hay and needle not in t.public_id.casefold():continue
                out.append({'id':t.public_id,'catalog_target_id':t.id,'title':c.get('title') or t.public_id,'issuer':c.get('issuer') or '',
                            'type':c.get('type') or 'YOUTH_DEVELOPMENT_PROGRAM','status':t.status,'publication_id':t.publication_id})
                if len(out)>=limit:break
            return out

    def lab_pair_truths(self,case_id,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor);case=s.get(LabGoldCase,case_id)
            if not case:raise Problem('实验样本不存在',404)
            rows=list(s.scalars(select(LabPairTruth).where(LabPairTruth.gold_case_id==case_id,LabPairTruth.state=='LOCKED').order_by(LabPairTruth.created_at)))
            twins={x.id:x for x in s.scalars(select(LabTwin).where(LabTwin.id.in_([r.twin_id for r in rows]))) } if rows else {}
            return [{'id':r.id,'case_id':r.gold_case_id,'twin_id':r.twin_id,'twin_key':twins.get(r.twin_id).twin_key if twins.get(r.twin_id) else None,
                     'expected_eligibility':r.expected_eligibility,'expected_recommendation':r.expected_recommendation,
                     'truth_origin':r.truth_origin,'attestation_ref':r.attestation_ref,
                     'counts_as_real_gold':r.truth_origin=='INDEPENDENT_HUMAN_GOLD' and bool(r.attestation_ref),'note':r.note,'created_at':_iso(r.created_at)} for r in rows]

    def lab_set_pair_truth(self,case_id,twin_key,expected_eligibility=None,*,actor,expected_recommendation=None,truth_origin='OPERATOR_ANNOTATED',attestation_ref=None,note=''):
        expected=str(expected_eligibility or '').upper() or None
        expected_recommendation=str(expected_recommendation or '').upper() or None
        origin=str(truth_origin or '').upper()
        if expected is None and expected_recommendation is None:raise Problem('资格或推荐真值至少填写一项')
        if expected is not None and expected not in EXPECTED:raise Problem('资格配对真值不正确')
        if expected_recommendation is not None and expected_recommendation not in EXPECTED_RECOMMENDATION:raise Problem('推荐配对真值不正确')
        if origin not in TRUTH_ORIGINS:raise Problem('真值来源不正确')
        if origin=='INDEPENDENT_HUMAN_GOLD' and not (attestation_ref and str(attestation_ref).strip()):raise Problem('独立人工 Gold 配对必须提供证明引用',409,'GOLD_ATTESTATION_REQUIRED')
        with self.db.tx() as s:
            a=self._account(s,actor);case=s.get(LabGoldCase,case_id)
            if not case or case.state!='LOCKED':raise Problem('请先锁定机会实验样本',409,'LAB_CASE_NOT_LOCKED')
            twin=s.scalar(select(LabTwin).where(LabTwin.twin_key==twin_key,LabTwin.active.is_(True)).order_by(LabTwin.version.desc()))
            if not twin:raise Problem('数字分身不存在',404)
            row=s.scalar(select(LabPairTruth).where(LabPairTruth.gold_case_id==case_id,LabPairTruth.twin_id==twin.id))
            if row and row.state=='LOCKED':raise Problem('已锁定的资格配对真值不可覆盖',409,'LAB_PAIR_TRUTH_LOCKED')
            if not row:
                row=LabPairTruth(gold_case_id=case_id,twin_id=twin.id,expected_eligibility=expected,expected_recommendation=expected_recommendation,truth_origin=origin,
                    attestation_ref=text(attestation_ref,160) or None,note=text(note,1000),state='LOCKED',created_by=a.id);s.add(row)
            else:
                row.expected_eligibility=expected;row.expected_recommendation=expected_recommendation;row.truth_origin=origin;row.attestation_ref=text(attestation_ref,160) or None;row.note=text(note,1000);row.state='LOCKED'
            s.flush();truth_id=row.id;self._audit(s,actor,'LAB_PAIR_TRUTH',truth_id,f'{case.target_public_id} × {twin.twin_key} → eligibility={expected or "—"}, recommendation={expected_recommendation or "—"}; {origin}')
        return next(x for x in self.lab_pair_truths(case_id,actor=actor) if x['id']==truth_id)

    def _lab_run_targets(self,s,kind,max_targets):
        if kind=='GOLD_BENCHMARK':
            cases=list(s.scalars(select(LabGoldCase).where(LabGoldCase.state=='LOCKED').order_by(LabGoldCase.created_at).limit(max_targets)))
            return [(s.get(CatalogTarget,c.catalog_target_id),c) for c in cases if s.get(CatalogTarget,c.catalog_target_id)]
        rows=list(s.scalars(select(CatalogTarget).where(CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(CatalogTarget.created_at.desc()).limit(max_targets)))
        return [(x,None) for x in rows]

    def lab_run_benchmark(self,*,actor,kind='CATALOG_SAFETY',max_targets=50,label=''):
        from .eligibility import evaluate
        from .value import assess, _region_match
        kind=str(kind or '').upper();max_targets=min(max(int(max_targets),1),200)
        if kind not in RUN_KINDS:raise Problem('实验运行类型不正确')
        with self.db.tx(False) as s:
            account=self._account(s,actor);twins=list(s.scalars(select(LabTwin).where(LabTwin.active.is_(True)).order_by(LabTwin.twin_key).limit(100)))
            targets=self._lab_run_targets(s,kind,max_targets)
            case_ids=[case.id for _,case in targets if case]
            truths=list(s.scalars(select(LabPairTruth).where(LabPairTruth.gold_case_id.in_(case_ids),LabPairTruth.state=='LOCKED'))) if case_ids else []
            pair_truth={(x.gold_case_id,x.twin_id):x for x in truths}
        if not twins:raise Problem('请先生成 100 个合成数字分身',409,'LAB_TWINS_REQUIRED')
        if not targets:raise Problem('当前没有可运行的实验机会样本',409,'LAB_CASES_REQUIRED')
        with self.db.tx() as s:
            a=self._account(s,actor);run=LabRun(kind=kind,label=text(label,200),status='RUNNING',created_by=a.id,
                manifest={'lab_version':LAB_VERSION,'twin_version':TWIN_VERSION,'synthetic_twins':len(twins),'target_count':len(targets),'max_targets':max_targets,
                          'production_mutation_allowed':False,'truth_scope':'LOCKED_LAB_CASES_ONLY' if kind=='GOLD_BENCHMARK' else 'NONE'})
            s.add(run);s.flush();run_id=run.id
        statuses=Counter();bands=Counter();gates=Counter();truth=Counter();unsafe=[]
        correct=0;truth_count=0;recommendation_correct=0;recommendation_truth_count=0;recommendation_truth=Counter()
        results=[]
        for twin in twins:
            for target,case in targets:
                with self.db.tx(False) as s:
                    live=s.get(CatalogTarget,target.id);opp=s.get(Opportunity,target.opportunity_id)
                if live is None or opp is None:continue
                eligibility=evaluate(self,live,opp,twin.profile)
                content=self._target(live,opp)
                status=eligibility.get('status') or 'UNCERTAIN'
                # Gold Benchmark must mirror the production candidate gates before
                # calling SG5 value assessment. Otherwise the lab can score an
                # opportunity as FEATURE even though recommendations() would never
                # surface it for this profile.
                selected=set(twin.profile.get('opportunity_types') or [])
                retrieval_excluded=None
                if selected and content.get('type') not in selected:
                    retrieval_excluded='EXPLICIT_TYPE_FILTER'
                elif twin.profile.get('region_preference_mode','FLEXIBLE')=='STRICT' and twin.profile.get('cities') and content.get('region'):
                    if not _region_match(content.get('region',''),twin.profile.get('cities')):
                        retrieval_excluded='STRICT_REGION_FILTER'
                if retrieval_excluded:
                    gate='NORMAL';band='NOT_RECOMMENDED';actual_recommendation='HOLD'
                    value={'qualification_gate':gate,'priority_band':band}
                else:
                    value=assess(content,twin.profile,eligibility)
                    gate=value.get('qualification_gate') or 'NORMAL';band=value.get('priority_band') or 'EXPLORE'
                    actual_recommendation=_recommendation_class(band,gate)
                pair=pair_truth.get((case.id,twin.id)) if case else None
                expected=pair.expected_eligibility if pair else None;is_correct=(status==expected) if expected else None
                expected_recommendation=pair.expected_recommendation if pair else None
                is_recommendation_correct=(actual_recommendation==expected_recommendation) if expected_recommendation else None
                statuses[status]+=1;bands[band]+=1;gates[gate]+=1
                if expected:
                    truth_count+=1;correct+=int(bool(is_correct));truth[pair.truth_origin]+=1
                if expected_recommendation:
                    recommendation_truth_count+=1;recommendation_correct+=int(bool(is_recommendation_correct));recommendation_truth[pair.truth_origin]+=1
                is_unsafe=(status=='INELIGIBLE' and band!='NOT_RECOMMENDED') or ((eligibility.get('qualification_risk') or {}).get('level')=='HIGH' and gate!='HOLD_FOR_CONFIRMATION' and band!='NOT_RECOMMENDED')
                if is_unsafe and len(unsafe)<50:unsafe.append({'twin':twin.twin_key,'target':target.public_id,'status':status,'gate':gate,'band':band})
                results.append((twin,live,case,status,gate,band,expected,expected_recommendation,is_correct,is_recommendation_correct,{
                    'qualification_risk':(eligibility.get('qualification_risk') or {}).get('level') or 'NORMAL',
                    'recommendation_class':actual_recommendation,'retrieval_excluded_reason':retrieval_excluded,
                    'requirement_count':len(eligibility.get('requirements') or []),'reason_count':len(eligibility.get('review_reasons') or []),
                }))
        metrics={'pairs':len(results),'twins':len(twins),'targets':len(targets),'eligibility':dict(statuses),'priority_bands':dict(bands),
                 'qualification_gates':dict(gates),'unsafe_recommendations':len(unsafe),'unsafe_examples':unsafe,
                 'truth_pairs':truth_count,'truth_accuracy':_safe_ratio(correct,truth_count),'truth_origin_pairs':dict(truth),
                 'real_gold_pairs':truth.get('INDEPENDENT_HUMAN_GOLD',0),'engineering_or_operator_pairs':truth_count-truth.get('INDEPENDENT_HUMAN_GOLD',0),
                 'recommendation_truth_pairs':recommendation_truth_count,'recommendation_accuracy':_safe_ratio(recommendation_correct,recommendation_truth_count),
                 'recommendation_truth_origin_pairs':dict(recommendation_truth),'real_recommendation_gold_pairs':recommendation_truth.get('INDEPENDENT_HUMAN_GOLD',0),
                 'llm_used':False,'production_mutated':False}
        with self.db.tx() as s:
            run=s.get(LabRun,run_id)
            for twin,target,case,status,gate,band,expected,expected_recommendation,is_correct,is_recommendation_correct,detail in results:
                pair=pair_truth.get((case.id,twin.id)) if case else None
                s.add(LabRunResult(run_id=run_id,twin_id=twin.id,gold_case_id=case.id if case else None,catalog_target_id=target.id,
                    target_public_id=target.public_id,eligibility_status=status,qualification_gate=gate,priority_band=band,
                    expected_eligibility=expected,expected_recommendation=expected_recommendation,truth_origin=pair.truth_origin if pair else None,
                    correct=is_correct,recommendation_correct=is_recommendation_correct,detail=detail))
            run.status='COMPLETED';run.metrics=metrics;run.finished_at=now()
            self._audit(s,actor,'LAB_BENCHMARK',run_id,f'{kind}: {len(results)} pairs, unsafe={len(unsafe)}, production_mutated=false')
        return self.lab_run(run_id,actor=actor)

    def lab_run(self,run_id,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor);r=s.get(LabRun,run_id)
            if not r:raise Problem('实验运行不存在',404)
            return {'id':r.id,'kind':r.kind,'status':r.status,'label':r.label,'manifest':r.manifest,'metrics':r.metrics,
                    'created_at':_iso(r.created_at),'finished_at':_iso(r.finished_at)}

    def lab_runs(self,*,actor,limit=20):
        limit=min(max(int(limit),1),100)
        with self.db.tx(False) as s:
            self._account(s,actor);rows=list(s.scalars(select(LabRun).order_by(LabRun.created_at.desc()).limit(limit)))
            return [{'id':r.id,'kind':r.kind,'status':r.status,'label':r.label,'metrics':r.metrics,'created_at':_iso(r.created_at),'finished_at':_iso(r.finished_at)} for r in rows]

    def lab_join(self,*,actor):
        with self.db.tx() as s:
            a=self._account(s,actor);row=s.get(LabEnrollment,a.id)
            if row:
                row.status='ACTIVE';row.consent_version=CONSENT_VERSION;row.joined_at=now();row.withdrawn_at=None
            else:s.add(LabEnrollment(account_id=a.id,status='ACTIVE',cohort='FOUNDING_USER_V1',consent_version=CONSENT_VERSION))
            self._audit(s,actor,'LAB_JOIN',a.id,'自愿加入 SG7 共创实验；不改变资格结果，不向 WMA 发送个人画像')
        return self.lab_me(actor=actor)

    def lab_leave(self,*,actor):
        with self.db.tx() as s:
            a=self._account(s,actor);row=s.get(LabEnrollment,a.id)
            if row:row.status='WITHDRAWN';row.withdrawn_at=now()
            self._audit(s,actor,'LAB_LEAVE',a.id,'退出 SG7 共创实验；后续不再进入实验聚合')
        return self.lab_me(actor=actor)

    def _lab_account_counts(self,s,account_id,joined_at):
        exposures=s.scalar(select(func.count()).select_from(LabExposure).where(LabExposure.account_id==account_id,LabExposure.first_seen_at>=joined_at)) or 0
        feedback=s.scalar(select(func.count()).select_from(TargetFeedback).where(TargetFeedback.account_id==account_id,TargetFeedback.created_at>=joined_at)) or 0
        actions=s.scalar(select(func.count()).select_from(TargetActionEvent).where(TargetActionEvent.account_id==account_id,TargetActionEvent.created_at>=joined_at)) or 0
        return exposures,feedback,actions

    def lab_me(self,*,actor):
        with self.db.tx(False) as s:
            a=self._account(s,actor);row=s.get(LabEnrollment,a.id)
            if not row:return {'status':'NOT_JOINED','consent_version':CONSENT_VERSION,'voluntary':True,'data_scope':['机会星图首次呈现','收藏与行动状态变化','结构化反馈'],'external_model':False}
            counts=self._lab_account_counts(s,a.id,row.joined_at)
            return {'status':row.status,'cohort':row.cohort,'consent_version':row.consent_version,'joined_at':_iso(row.joined_at),'withdrawn_at':_iso(row.withdrawn_at),
                    'voluntary':True,'external_model':False,'summary':{'opportunities_observed':counts[0],'feedback_events':counts[1],'action_events':counts[2]}}

    def lab_record_exposures(self,*,actor,items):
        ids=[x.get('id') for x in (items or []) if isinstance(x,dict) and x.get('id')]
        if not ids:return 0
        with self.db.tx() as s:
            a=self._account(s,actor);en=s.get(LabEnrollment,a.id)
            if not en or en.status!='ACTIVE':return 0
            created=0
            for public_id in list(dict.fromkeys(ids))[:50]:
                target=s.scalar(select(CatalogTarget).where(CatalogTarget.public_id==public_id,CatalogTarget.status.in_(['CURRENT','UPDATE_PENDING'])).order_by(CatalogTarget.created_at.desc()))
                if not target:continue
                existing=s.scalar(select(LabExposure).where(LabExposure.account_id==a.id,LabExposure.target_public_id==public_id,LabExposure.publication_id==target.publication_id))
                if not existing:s.add(LabExposure(account_id=a.id,target_public_id=public_id,publication_id=target.publication_id,catalog_target_id=target.id));created+=1
            return created

    def lab_founding_metrics(self,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor)
            active=list(s.scalars(select(LabEnrollment).where(LabEnrollment.status=='ACTIVE')))
            active_ids=[x.account_id for x in active]
            if not active_ids:
                return {'active_participants':0,'exposures':0,'feedback_events':0,'action_events':0,'previously_unknown_rate':None,'useful_rate':None,'action_conversion_rate':None,'privacy':'AGGREGATE_ONLY'}
            joined={x.account_id:x.joined_at for x in active}
            exposures=list(s.scalars(select(LabExposure).where(LabExposure.account_id.in_(active_ids))))
            feedback=list(s.scalars(select(TargetFeedback).where(TargetFeedback.account_id.in_(active_ids))))
            events=list(s.scalars(select(TargetActionEvent).where(TargetActionEvent.account_id.in_(active_ids))))
            exposures=[x for x in exposures if x.first_seen_at>=joined[x.account_id]]
            feedback=[x for x in feedback if x.created_at>=joined[x.account_id]]
            events=[x for x in events if x.created_at>=joined[x.account_id]]
            known=[x for x in feedback if isinstance((x.data or {}).get('previously_known'),bool)]
            useful=[x for x in feedback if isinstance((x.data or {}).get('useful'),bool)]
            unknown=sum(1 for x in known if (x.data or {}).get('previously_known') is False)
            useful_yes=sum(1 for x in useful if (x.data or {}).get('useful') is True)
            exposed={(x.account_id,x.target_public_id) for x in exposures}
            acted={(x.account_id,x.target_public_id) for x in events if x.to_status in {'SAVED','PREPARING','APPLIED','WAITING','COMPLETED'}}
            acted_from_exposed=len(exposed & acted)
            return {'active_participants':len(active),'exposures':len(exposures),'feedback_events':len(feedback),'action_events':len(events),
                    'previously_unknown_count':unknown,'previously_unknown_denominator':len(known),'previously_unknown_rate':_safe_ratio(unknown,len(known)),
                    'useful_count':useful_yes,'useful_denominator':len(useful),'useful_rate':_safe_ratio(useful_yes,len(useful)),
                    'action_from_exposure_count':acted_from_exposed,'action_conversion_denominator':len(exposed),'action_conversion_rate':_safe_ratio(acted_from_exposed,len(exposed)),
                    'privacy':'AGGREGATE_ONLY','free_text_returned':False}

    def lab_summary(self,*,actor):
        with self.db.tx(False) as s:
            self._account(s,actor)
            twins=s.scalar(select(func.count()).select_from(LabTwin).where(LabTwin.active.is_(True))) or 0
            cases=list(s.scalars(select(LabGoldCase).where(LabGoldCase.state=='LOCKED')))
            real=sum(1 for x in cases if x.truth_origin=='INDEPENDENT_HUMAN_GOLD' and x.attestation_ref)
            experimental=len(cases)-real
            pair_rows=list(s.scalars(select(LabPairTruth).where(LabPairTruth.state=='LOCKED')))
            real_pairs=sum(1 for x in pair_rows if x.truth_origin=='INDEPENDENT_HUMAN_GOLD' and x.attestation_ref)
            active=s.scalar(select(func.count()).select_from(LabEnrollment).where(LabEnrollment.status=='ACTIVE')) or 0
            latest=s.scalar(select(LabRun).order_by(LabRun.created_at.desc()).limit(1))
        return {'lab_version':1,'synthetic_twins':twins,'locked_cases':len(cases),'real_gold':real,'engineering_or_operator_cases':experimental,
                'qualification_pair_truths':len(pair_rows),'real_qualification_pairs':real_pairs,'active_founding_users':active,
                'latest_run':({'id':latest.id,'kind':latest.kind,'status':latest.status,'metrics':latest.metrics,'created_at':_iso(latest.created_at)} if latest else None),
                'production_authority':'UNCHANGED','model_training':'NONE'}
