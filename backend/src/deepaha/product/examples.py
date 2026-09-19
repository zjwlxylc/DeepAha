"""Fictional opt-in sample packages, never loaded by application startup."""
import io,json,zipfile
from datetime import date,timedelta

def bundles():
    day=(date.today()+timedelta(days=24)).isoformat()
    def make(data,lines,extra_artifacts=None):
        notice=data['official_url']
        artifacts=[{'artifact_id':'notice','local_path':'artifacts/announcement.txt','url':notice}]+(extra_artifacts or [])
        f={'opportunities.json':json.dumps(data,ensure_ascii=False,indent=2).encode(),
           'evidence.json':json.dumps({'artifacts':artifacts},ensure_ascii=False,indent=2).encode(),
           'report.md':('# '+data['opportunity_name']+'\n\n'+lines+'\n\n资料状态见返回目录。').encode(),
           'artifacts/announcement.txt':lines.encode()}
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:
            for k,v in f.items():z.writestr(k,v)
        return b.getvalue()
    def f(label,value,quote=None,status='CONFIRMED',note=''):
        return {'field':label,'value':value,'status':status,'note':note,'evidence':[{'artifact_id':'notice','quote':quote,'locator':{'section':'公告正文'}}] if quote else []}
    jobs={'opportunity_name':'城市工程研究院 · 青年人才引进','publish_unit':'澄川城市工程研究院','opportunity_type':'招聘',
          'official_url':'https://institute.example.org/notices/young-talents','work_location':'宁波',
          'summary':'面向工程研究、技术管理方向招募青年人才，包含两个岗位。',
          'announcement_level':[f('报名截止',day,'报名截止：'+day),f('最低服务期','最低服务期五年',status='UNKNOWN'),f('申请方式','按公告要求，将申请材料提交至官方指定渠道。',status='UNKNOWN')],
          'units':[{'id':'research','name':'工程研究中心','unit_level':[f('共同条件','具有良好的科研诚信与团队协作能力。')],
                    'positions':[{'id':'position-01','name':'工程研究助理','code':'A01','facts':[f('学历','硕士研究生以上'),f('专业','土木工程、环境工程或相关专业'),f('招聘人数','2人')]},
                                 {'id':'position-02','name':'技术项目管理员','code':'A02','facts':[f('学历','本科及以上'),f('岗位类别','管理'),f('招聘人数','1人')]}]}]}
    contest={'opportunity_name':'青年数字创意挑战赛','publish_unit':'澄川青年创新中心','opportunity_type':'COMPETITION',
             'official_url':'https://institute.example.org/notices/digital-creativity','work_location':'线上',
             'summary':'用数字技术回应真实生活问题，围绕创意表达和应用设计提交作品。',
             'announcement_level':[f('报名截止',day,'报名截止：'+day),f('作品提交截止',(date.today()+timedelta(days=45)).isoformat()),f('组队要求','每队3至5人，可跨专业组队。'),f('作品权利','作品著作权归作者，主办方可在赛事宣传中展示入选作品。')],
             'tracks':[{'id':'story','name':'数字叙事赛道','kind':'TRACK','facts':[f('作品要求','提交完整作品及创作说明；引用素材需注明来源。')]},
                       {'id':'application','name':'应用设计赛道','kind':'TRACK','facts':[f('提交材料','交互作品、使用演示和设计说明。')]}]}
    policy={'opportunity_name':'青年创新项目支持计划','publish_unit':'澄川青年服务中心','opportunity_type':'YOUTH_POLICY_BENEFIT',
            'official_url':'https://institute.example.org/notices/youth-policy','work_location':'浙江',
            'summary':'为符合条件的青年项目提供分阶段支持。',
            'announcement_level':[f('受理时间','滚动受理，具体批次以正式通知为准。'),f('支持标准','每年最高5万元，按经审核的实际支出给予支持。'),
               f('申请条件','在本地实施的青年创新项目，符合项目类别和申报要求。'),f('办理方式','线下提交至官方指定受理窗口。'),f('兑付限制','同一支出不得重复申领；材料审核通过不代表立即兑付。')],
            'children':[{'id':'innovation','name':'创新实践项目','kind':'PROGRAM_TIER','facts':[f('项目材料','申报书、预算明细、负责人资格材料。')]}]}

    research={'opportunity_name':'青年科研实践计划','publish_unit':'澄川先进技术研究院','opportunity_type':'RESEARCH_PROGRAM',
              'official_url':'https://institute.example.org/notices/research-practice','work_location':'宁波',
              'summary':'面向本科生开放科研实践方向，由不同实验室提供课题与指导。',
              'announcement_level':[f('申请截止',day,'申请截止：'+day),f('申请条件','面向在校本科生，具体方向要求见分项。')],
              'units':[{'id':'lab-materials','source_record_key':'lab-materials','name':'先进材料实验室','unit_level':[f('实验地点','宁波')],
                        'tracks':[{'id':'direction-energy','source_record_key':'direction-energy','name':'储能材料方向','kind':'TRACK','facts':[f('研究方向','电池材料与界面研究'),f('时间投入','每周不少于8小时')]},
                                  {'id':'direction-sensor','source_record_key':'direction-sensor','name':'智能传感方向','kind':'TRACK','facts':[f('研究方向','柔性传感材料与应用')]}]}]}
    scholarship={'opportunity_name':'青年创新奖学金','publish_unit':'澄川教育基金会','opportunity_type':'SCHOLARSHIP',
                 'official_url':'https://institute.example.org/notices/innovation-scholarship','summary':'支持具有创新实践、科研或公益经历的在校青年。',
                 'announcement_level':[f('申请截止',day,'申请截止：'+day),f('共同条件','在校学生，可提交创新、科研或公益经历。')],
                 'program_tiers':[{'id':'award-excellent','source_record_key':'award-excellent','name':'卓越奖','kind':'PROGRAM_TIER','facts':[f('支持金额','每人10000元'),f('综合素质说明','可提交公益、创新或科研经历作为补充材料。')]},
                                  {'id':'award-growth','source_record_key':'award-growth','name':'成长奖','kind':'PROGRAM_TIER','facts':[f('支持金额','每人5000元')]}]}
    postgrad={'opportunity_name':'未来传播暑期学校','publish_unit':'澄川大学传播学院','opportunity_type':'POSTGRAD_RECOMMENDATION',
              'official_url':'https://institute.example.org/notices/summer-school','summary':'面向本科生开放的暑期学术与创新实践项目。',
              'announcement_level':[f('申请截止',day,'申请截止：'+day),f('共同条件','具体年级与材料要求见各项目类别。')],
              'program_tiers':[{'id':'summer-research','source_record_key':'summer-research','name':'学术研究组','kind':'PROGRAM_TIER','facts':[f('面向对象','相关专业本科三年级学生'),f('提交材料','成绩单、个人陈述和研究兴趣说明')]},
                               {'id':'summer-practice','source_record_key':'summer-practice','name':'创新实践组','kind':'PROGRAM_TIER','facts':[f('面向对象','跨专业创新实践学生'),f('提交材料','项目作品或实践说明')]}]}
    yield '01_recruitment.zip',make(jobs,'报名截止：'+day+'\n最低服务期要求以正式附件为准。',[{'artifact_id':'attachment2','local_path':'artifacts/terms.pdf','url':'https://institute.example.org/files/terms.pdf','status':'UNREAD'}])
    yield '02_competition.zip',make(contest,'报名截止：'+day+'\n每队3至5人，可跨专业组队。')
    yield '03_policy.zip',make(policy,'滚动受理，具体批次以正式通知为准。\n每年最高5万元，按经审核的实际支出给予支持。')
    yield '04_research.zip',make(research,'申请截止：'+day+'\n不同研究方向的要求见对应分项。')
    yield '05_scholarship.zip',make(scholarship,'申请截止：'+day+'\n奖项档次与材料要求以正式说明为准。')
    yield '06_postgrad.zip',make(postgrad,'申请截止：'+day+'\n不同项目类别面向对象不同。')
