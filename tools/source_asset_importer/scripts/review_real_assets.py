#!/usr/bin/env python3
"""Reproduce the supplied GPT/WB offline audit and controlled checkpoint.

No network, database, WMA or Codex calls. Explicit paths; no production approval.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import shutil
import sys
import zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from deepaha_importer.research.ingest import load_inputs
from deepaha_importer.research.audit import analyze
from deepaha_importer.research.baseline import create_controlled_baseline,verify_archive_manifest

def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
def csvwrite(path,rows):
    if not rows:return
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        # Guard spreadsheet formula execution when a CSV is opened in an office app.
        for row in rows:
            w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@','\t','\r')) else v) for k,v in row.items()})

def wb_note(s):
    codes=s['issue_codes'];name=s['name'];urls=s['seed_urls'];text=''
    cat='SCOPED_CANDIDATE'
    if s['blocking']:
        cat='DEFER_RECON';text='当前投影没有可明确识别的公开HTTP(S)入口。保留全部旧观察，不将域名模板、小程序或缺失值自动改写为可运行来源。'
    elif any('gaoxiaojob.com' in u for u in urls):
        cat='LEAD_ONLY_DEFER';text='商业高校人才聚合栏目且偏向高层次教研人员，只作为受众受限的追源线索；不因A1自评分而升为官方源，也不作普通本科生核心入口。'
    elif '登录墙' in name:
        cat='DEFER_RECON';text='原记录已说明公开区未核读且有登录墙；保留机构项目线索，未取得授权可访问入口前不安排自动采集。'
    elif 'MULTIPLE_SEEDS' in codes:
        cat='DEFER_PRIMARY_ENDPOINT';text='同一字段有多个网址，保留全部；需要人选择主入口并区分总门户、专题、详情、替代主机，不按第一个URL自动批准。'
    elif any('SIZE_CLAIM_MISMATCH' in x for x in codes):
        cat='DEFER_ATTACHMENT_RECONCILIATION';text='文件SHA找到了真实原件，但声明大小与实际字节不符；先核对附件声明/路径，不能覆盖原记录，也不将此附件直接升为正式证据。'
    elif any(u=='https://cy.ncss.cn/' for u in urls):
        cat='RELATION_REVIEW';text='与GPT候选的入口规范键相同，形成一对跨来源同Endpoint提案；保留双侧键和历次证据，官方机构/栏目身份确认后再决定映射。'
    elif '24365' in name or '就业平台' in name or '就业服务平台' in name or '国聘招聘' in name:
        text='作为就业发现/聚合网络候选保留；省级分站、平台与用人单位承担不同责任，正式条件要追原单位，不因域名相似合并为一个来源。'
    elif any(x in name for x in ['选调','公务员','考试','三支一扶','招聘','组工','党建','进人']):
        text='保留稳定路径发现候选；必须区分应届招录、在职遴选、资格考试和结果公示，按年度与对象限定范围，不能混作所有青年当前可报机会。'
    elif any(x in name for x in ['大赛','展示','展演','市场调查']):
        text='保留能力成长/赛事来源；必须拆清组别、赛道、学校推荐与团队资格，立项/结果公告不等于正在招募。'
    elif '留学' in name or '研究生招生' in name:
        text='保留升学与资助来源；入口只是项目发现，项目资格、学籍、推荐单位、年度和内部截止需要原始资料另行核验。'
    elif '驿站' in name:
        text='属于机会促成资源而非招聘岗位；公开服务入口可做候选，城市、身份、入住/补助窗口和办理限制必须分项核实。'
    else:
        text='按原记录的机构和栏目范围保留为研究候选；对外事实、当前可访问性及真实生产效用均尚未独立核验。'
    if 'SCORE_ARITHMETIC_MISMATCH' in codes:text+=' 存在评分加总矛盾，原分与重算值并列；本次不用这份分数作准入或跨模型排名。'
    if 'FIRST_SEEN_CHANGED' in codes:text+=' 首次发现时间发生变化：保留全部声明，原始首次发现不可由较晚记录覆盖。'
    if 'SEED_CHANGED_ACROSS_VERSIONS' in codes:text+=' 历史入口不同，保留为版本/关系待审，不自动改址或退役。'
    if 'REFERENCE_TEXT_NORMALIZATION_PROPOSAL' in codes:text+=' 文字包装的证据键已显式拆分并找到对应记录，原文字仍保留。'
    return {'use_category':cat,'review_note':text}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--gpt-dir',type=Path,required=True);p.add_argument('--wb-zip',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--prior-state',type=Path)
    p.add_argument('--archive-manifest',type=Path);p.add_argument('--baseline-author')
    args=p.parse_args();root=args.out;root.mkdir(parents=True,exist_ok=True)
    gfiles=sorted(args.gpt_dir.glob('*_Handoff.json'));states=sorted(args.gpt_dir.glob('*_State.json'))
    if len(gfiles)!=30 or len(states)!=30:raise SystemExit('需要指定本次完整30份Handoff与30份State；不会静默缩小分母。')
    a=analyze(load_inputs(gfiles+states+[args.wb_zip]));dump(root/'audit/Combined_Audit.json',a)
    notes_path=Path(__file__).resolve().parents[1]/'docs/v0.3.0/GPT_30_Case_Review_Notes.json'
    notes=json.loads(notes_path.read_text())['notes'];rows=[];versions=[];decisions=[]
    for s in a['sources']:
        if s['namespace']=='chatgpt-scout':
            note=notes.get(s['id']) or {'use_category':'DEFER_RECON','review_note':'不在本次人工编写的案例说明映射中，请单独检查。'}
        else:note=wb_note(s)
        decision='DEFER' if note['use_category'].startswith(('DEFER','LEAD_ONLY')) else 'PROPOSE_STAGING'
        # This is an assistant-authored opinion, not a fabricated human/system approval.
        item={'source_id':s['id'],'namespace':s['namespace'],'candidate_key':s['candidate_key'],'source_name':s['name'],
              **note,'assisted_decision':decision,'review_author':'ChatGPT辅助批审（非人工批准）','authority':'ASSISTED_OFFLINE_REVIEW_ONLY',
              'official_identity_validation':'NOT_INDEPENDENTLY_VERIFIED','system_source_id':None,'collection_enabled':None,
              'version_count':len(s['versions']),'original_seed_field':s['seed_original'],'public_seed_candidates':s['seed_urls'],
              'issues':s['issue_codes'],'latest_origin':s['current']['origin'],'latest_pointer':s['current']['pointer']}
        decisions.append(item)
        rows.append({'namespace':s['namespace'],'candidate_key':s['candidate_key'],'名称':s['name'],'版本数':len(s['versions']),
                     '用途分类':note['use_category'],'处理建议':decision,'审核意见':note['review_note'],
                     '入口候选':' | '.join(s['seed_urls']),'问题':' | '.join(s['issue_codes']),'人工批准':'未取得','系统状态':'未提交'})
        for v in s['versions']:
            versions.append({'namespace':s['namespace'],'candidate_key':s['candidate_key'],'source_id':s['id'],
                             'run_key':v['run_key'],'semantic_hash':v['semantic_hash'],'file_sha256':v['origin']['sha256'],
                             'locator':v['origin']['locator'],'pointer':v['pointer'],'is_current_projection':v==s['current']})
    dump(root/'audit/Assisted_Review_All89.json',{'scope':'48份Handoff及选定State上下文的离线辅助审核，非逐网址现状核验','rows':decisions})
    dump(root/'audit/Version_Lineage_All164.json',versions);csvwrite(root/'audit/All89_Review.csv',rows)
    csvwrite(root/'audit/GPT30_37_Review.csv',[r for r in rows if r['namespace']=='chatgpt-scout'])
    csvwrite(root/'audit/WB18_52_Review.csv',[r for r in rows if r['namespace']=='wb-scout'])
    dump(root/'audit/Endpoint_Relation_Proposals.json',a['relations'])
    dump(root/'audit/Attachment_Reconciliation.json',{'files':a['attachments'],'references':a['attachment_reconciliation'],'state_references':a['state_reference_reconciliation']})
    stats={'summary':a['summary'],'namespace_summary':a['namespace_summary'],'issue_occurrences':dict(collections.Counter(x['code'] for x in a['issues'])),
           'assisted_categories':{n:dict(collections.Counter(d['use_category'] for d in decisions if d['namespace']==n)) for n in a['namespace_summary']},
           'assisted_decisions':{n:dict(collections.Counter(d['assisted_decision'] for d in decisions if d['namespace']==n)) for n in a['namespace_summary']},
           'same_content_repeats':sum(len(s['versions'])-len({v['semantic_hash'] for v in s['versions']}) for s in a['sources']),
           'actual_attachment_unique_sha256':len({x['sha256'] for x in a['attachments']}),
           'attachment_declaration_results':dict(collections.Counter(x['status'] for x in a['attachment_reconciliation'])),
           'distinct_attachment_sha_referenced':len({x['declared_sha256'] for x in a['attachment_reconciliation'] if x['matched_files']}),
           'real_system_feedback_observed':False,'production_connections_attempted':0}
    dump(root/'audit/Stats.json',stats)
    if args.archive_manifest:
        dump(root/'baseline/Archive_Manifest_Verification.json',verify_archive_manifest(args.archive_manifest,args.gpt_dir))
    if args.baseline_author:
        if not args.prior_state:raise SystemExit('创建基线需要前一检查点原件。')
        selected=next(x for x in states if '_X30_State' in x.name)
        baseline=create_controlled_baseline(selected,states,authorizing_user=args.baseline_author,external_parent=args.prior_state)
        dump(root/'baseline/DeepAha_Scout_Controlled_Baseline_20260913_State.json',baseline)
        dump(root/'baseline/Permanent_Migration_Gaps.json',{'baseline_id':baseline['controlled_baseline']['baseline_id'],
                 'gaps':baseline['controlled_baseline']['permanent_migration_gaps'],'overlap_notice':'原始缺口描述可能重叠，不代表五类互不相交的缺失记录。',
                 'feedback_notice':'缺失旧回执仅作为截止时点缺口；后续真实系统反馈仍可以新增，不属于永久无法获得。'})
        dump(root/'baseline/State_Chain_Verification.json',baseline['controlled_baseline']['chain_verification'])
        shutil.copy2(selected,root/'baseline'/selected.name);shutil.copy2(args.prior_state,root/'baseline'/args.prior_state.name)
    print(json.dumps(stats,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
