import io,json,zipfile
from pathlib import Path
import pytest

from .test_contract import svc
from .test_eligibility import _zip, approve


def fact(label,value,quote=None,artifact='a1',locator=None):
    ev=[] if quote is None else [{'artifact_id':artifact,'quote':quote,'locator':locator or {'line':1}}]
    return {'field':label,'value':value,'status':'CONFIRMED','evidence':ev}


def packet(facts, *, artifact_name='artifacts/notice.txt', artifact_bytes=None, coverage=None, extra_artifacts=None):
    official='https://research.example.org/notices/compiler'
    root={'opportunity_name':'资格编译测试','publish_unit':'海湾研究中心','opportunity_type':'PUBLIC_INSTITUTION_JOB','official_url':official,
          'units':[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':'测试岗','code':'Q01','facts':facts}]}]}
    if coverage:root['metadata']={'qualification_coverage':coverage}
    if artifact_bytes is None:
        quotes=[]
        for f in facts:
            ev=f.get('evidence') or []
            quotes.append(str(ev[0].get('quote','')) if ev else '')
        artifact_bytes='\n'.join(quotes).encode()
    arts=[{'artifact_id':'a1','local_path':artifact_name,'url':official}]
    files={'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),'evidence.json':json.dumps({'artifacts':arts+(extra_artifacts or [])},ensure_ascii=False).encode(),'report.md':b'# compiler',artifact_name:artifact_bytes}
    return _zip(files)


def test_aliases_compile_to_same_canonical_type():
    from deepaha.product.qualification_compiler import compile_field
    zh=compile_field({'label':'学历','value':'本科及以上','state':'CONFIRMED','evidence':[]},'fields',1,[])
    en=compile_field({'label':'education','value':'本科','state':'CONFIRMED','evidence':[]},'fields',1,[])
    assert zh['type']=='EDUCATION_MIN'
    assert en['type']=='EDUCATION_MIN'
    assert en['normalized']['minimum_level']==2


def test_english_education_with_located_evidence_can_deny_junior_college(svc):
    blob=packet([fact('education','本科','education：本科')])
    oid=approve(svc,blob,'compiler-en-education')
    svc.set_profile({'education':'专科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    q=next(x for x in fit['requirements'] if x['type']=='EDUCATION_MIN')
    assert q['outcome']=='CONFLICT' and q['evidence_support']=='LOCATED'


def test_degree_nationality_political_and_experience_are_canonical_not_unsupported():
    from deepaha.product.qualification_compiler import compile_field
    cases=[
      ('学位','硕士以上','DEGREE_MIN'),('nationality','具有中华人民共和国国籍','NATIONALITY'),
      ('political_status','中共党员（含预备党员）','POLITICAL_STATUS'),('工作经历','须具有2年以上相关工作经历','EXPERIENCE_MIN_YEARS')]
    for label,value,typ in cases:
        c=compile_field({'label':label,'value':value,'state':'CONFIRMED','evidence':[]},'fields',1,[])
        assert c and c['type']==typ and c['normalization_reason']!='UNSUPPORTED_HARD_CONDITION'


def test_profile_can_compare_new_high_impact_fields(svc):
    fs=[fact('学位','硕士以上','学位：硕士以上'),fact('国籍要求','具有中华人民共和国国籍','国籍要求：具有中华人民共和国国籍'),
        fact('政治面貌','中共党员（含预备党员）','政治面貌：中共党员（含预备党员）'),fact('工作经历','须具有2年以上相关工作经历','工作经历：须具有2年以上相关工作经历')]
    oid=approve(svc,packet(fs),'compiler-profile-fields')
    svc.set_profile({'degree':'学士','nationality':'中国','political_status':'群众','work_experience_years':1},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='INELIGIBLE'
    conflicts={x['type'] for x in fit['requirements'] if x['outcome']=='CONFLICT'}
    assert {'DEGREE_MIN','POLITICAL_STATUS','EXPERIENCE_MIN_YEARS'} <= conflicts
    assert next(x for x in fit['requirements'] if x['type']=='NATIONALITY')['outcome']=='SATISFIED'


def make_docx(text):
    doc=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>'''
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('word/document.xml',doc)
    return b.getvalue()


def test_docx_quote_can_be_verified_from_immutable_original(svc):
    quote='学历要求：本科及以上'
    oid=approve(svc,packet([fact('education','本科及以上',quote,locator={'paragraph':'1'})],artifact_name='artifacts/rules.docx',artifact_bytes=make_docx(quote)),'compiler-docx')
    svc.set_profile({'education':'专科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    q=next(x for x in fit['requirements'] if x['type']=='EDUCATION_MIN')
    assert q['evidence_support']=='LOCATED'
    assert q['evidence'][0]['verification']=='DOCX_TEXT_MATCH'
    assert fit['status']=='INELIGIBLE'


def test_ocr_derived_text_must_be_bound_to_saved_image_and_same_url(svc):
    official='https://research.example.org/notices/compiler'
    root={'opportunity_name':'OCR资格测试','publish_unit':'海湾研究中心','opportunity_type':'PUBLIC_INSTITUTION_JOB','official_url':official,
          'units':[{'id':'g1','name':'测试单位','positions':[{'id':'p1','name':'图片岗','facts':[fact('学历','硕士研究生以上','学历：硕士研究生以上',artifact='img1',locator={'row':1,'column':'学历'})]}]}]}
    files={'opportunities.json':json.dumps(root,ensure_ascii=False).encode(),
           'evidence.json':json.dumps({'artifacts':[{'artifact_id':'img1','local_path':'artifacts/table.png','url':official},{'artifact_id':'ocr1','local_path':'artifacts/table_ocr.txt','url':official}]},ensure_ascii=False).encode(),
           'report.md':b'# ocr','artifacts/table.png':b'fake-png-bytes','artifacts/table_ocr.txt':'岗位1 学历：硕士研究生以上'.encode()}
    oid=approve(svc,_zip(files),'compiler-ocr')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    q=next(x for x in fit['requirements'] if x['type']=='EDUCATION_MIN')
    assert q['evidence'][0]['verification']=='DERIVED_TEXT_MATCH'
    assert q['evidence'][0]['derived_artifact_id']=='ocr1'
    assert fit['status']=='INELIGIBLE'


def test_unlocated_clear_conflict_stays_uncertain_but_reports_high_risk(svc):
    oid=approve(svc,packet([fact('education','硕士研究生以上',None)]),'compiler-risk')
    svc.set_profile({'education':'专科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['status']=='UNCERTAIN'
    assert fit['qualification_risk']['level']=='HIGH'
    assert fit['qualification_risk']['potential_conflicts']


def test_server_owned_compiler_coverage_is_partial_without_explicit_complete(svc):
    oid=approve(svc,packet([fact('education','本科及以上','education：本科及以上')]),'compiler-coverage-partial')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['coverage']['state']=='BOUNDED'  # public compatibility
    assert fit['coverage']['compiler_state']=='PARTIAL'
    assert fit['status']=='LIKELY_ELIGIBLE'


def test_explicit_complete_plus_no_unresolved_can_be_compiler_complete(svc):
    oid=approve(svc,packet([fact('education','本科及以上','education：本科及以上')],coverage='COMPLETE'),'compiler-coverage-complete')
    svc.set_profile({'education':'本科'},actor='reader')
    fit=svc.fit(oid,actor='reader')
    assert fit['coverage']['compiler_state']=='COMPLETE'
    assert fit['status']=='ELIGIBLE'


def test_no_per_field_human_qualification_approval_route_exists():
    source=Path('backend/src/deepaha/product/api.py').read_text(encoding='utf-8')
    assert '/qualification/' not in source
    assert 'field-approve' not in source
    assert 'approve-field' not in source

def test_education_specific_age_matrix_compiles_without_crashing():
    from deepaha.product.qualification_compiler import compile_field
    raw='大学本科毕业生须在2000年1月1日及以后出生；硕士研究生须在1997年1月1日及以后出生；博士研究生须在1992年1月1日及以后出生'
    c=compile_field({'label':'age_limit','value':raw,'state':'CONFIRMED','evidence':[]},'common_fields',1,[])
    assert c['type']=='BIRTH_DATE_BY_EDUCATION'
    assert c['normalized']['minimum_birth_dates']=={'2':'2000-01-01','3':'1997-01-01','4':'1992-01-01'}

def test_participant_scope_research_student_includes_master_and_doctor():
    from deepaha.product.qualification_compiler import compile_field
    raw='浙江省普通全日制高校在校研究生、本科生和高职高专学生均可参赛'
    c=compile_field({'label':'参赛对象/资格','value':raw,'state':'CONFIRMED','evidence':[]},'common_fields',1,[])
    assert c['type']=='PARTICIPANT_SCOPE'
    assert set(c['normalized']['education_levels'])=={1,2,3,4}

def test_preflight_risk_deprioritizes_deterministic_conflict_without_changing_eligibility():
    from deepaha.product.eligibility import preflight_qualification_risk
    content={'fields':[{'label':'education','value':'硕士研究生以上','state':'CONFIRMED','evidence':[]}],
             'ancestor_fields':[],'common_fields':[]}
    risk=preflight_qualification_risk(content,{'education':'专科'})
    assert risk['level']=='HIGH'
    assert risk['potential_conflicts'][0]['type']=='EDUCATION_MIN'
    assert preflight_qualification_risk({'fields':[],'ancestor_fields':[],'common_fields':[]},{'education':'专科'})['level']=='NORMAL'


def test_professional_assessment_flag_is_not_misclassified_as_major_requirement():
    from deepaha.product.qualification_compiler import compile_field
    assert compile_field({'label':'专业测评','value':'否','state':'CONFIRMED','evidence':[]},'fields',1,[]) is None


def test_service_requirement_post_hire_rotation_is_not_work_experience():
    from deepaha.product.qualification_compiler import compile_field
    raw='公开招聘的高校毕业生需到基层一线岗位锻炼，锻炼期为一年'
    assert compile_field({'label':'service_requirement','value':raw,'state':'CONFIRMED','evidence':[]},'fields',1,[]) is None


def test_recruitment_object_explicit_unrestricted_does_not_become_fresh_graduate_requirement():
    from deepaha.product.qualification_compiler import compile_field
    for raw in ('不限','应届毕业生／机关事业单位正式在编人员／招聘对象不限'):
        c=compile_field({'label':'招聘对象类别','value':raw,'state':'CONFIRMED','evidence':[]},'fields',1,[])
        assert c['type']=='GRADUATION_YEAR_SET'
        assert c['deterministic'] is True
        assert c['normalized']['no_restriction'] is True


def test_recruitment_object_alternatives_without_unrestricted_stay_nondeterministic():
    from deepaha.product.qualification_compiler import compile_field
    c=compile_field({'label':'招聘对象类别','value':'应届毕业生／机关事业单位正式在编人员','state':'CONFIRMED','evidence':[]},'fields',1,[])
    assert c['deterministic'] is False
    assert c['normalization_reason']=='EXCEPTION_OR_ALTERNATIVE_PRESENT'


def test_professional_technical_qualification_is_not_misclassified_as_major():
    from deepaha.product.qualification_compiler import compile_field
    c=compile_field({'label':'专业技术职务任职资格','value':'中级以上','state':'CONFIRMED','evidence':[]},'fields',1,[])
    assert c['type']=='TITLE_REQUIRED'
    c2=compile_field({'label':'专业技术职务任职资格','value':'全国翻译专业资格（水平）考试二级口译及以上证书','state':'CONFIRMED','evidence':[]},'fields',1,[])
    assert c2['type']=='CERTIFICATE_REQUIRED'


def test_chinese_numeral_work_experience_is_normalized_deterministically():
    from deepaha.product.qualification_compiler import compile_field
    cases=[('具有两年以上相关工作经历',2.0),('具有三年以上实际审查工作经历',3.0),('六年及以上省级专业运动队正式运动员训练经历',6.0)]
    for raw,years in cases:
        c=compile_field({'label':'工作经历','value':raw,'state':'CONFIRMED','evidence':[]},'fields',1,[])
        assert c['type']=='EXPERIENCE_MIN_YEARS'
        assert c['deterministic'] is True
        assert c['normalized']['minimum_years']==years
