import json

from .test_actionable_granularity import approve, mutate_packet
from .test_contract import packet, svc


def test_competition_tracks_are_actionable_and_never_presented_as_jobs(svc):
    def change(data):
        data.update({
            'opportunity_name': '青年数字创意挑战赛',
            'publish_unit': '青年创新中心',
            'opportunity_type': 'COMPETITION',
            'summary': '面向高校学生的数字创意赛事。',
            'units': [],
            'announcement_level': [
                {'field': '组队要求', 'value': '每队3至5人，可跨专业组队。', 'status': 'UNKNOWN', 'evidence': []},
            ],
            'tracks': [
                {'id': 'runtime-track-1', 'source_record_key': 'track-digital-story', 'name': '数字叙事赛道', 'kind': 'TRACK',
                 'facts': [{'field': '作品要求', 'value': '提交完整作品及创作说明。', 'status': 'UNKNOWN', 'evidence': []}]},
                {'id': 'runtime-track-2', 'source_record_key': 'track-app-design', 'name': '应用设计赛道', 'kind': 'TRACK',
                 'facts': [{'field': '作品要求', 'value': '提交交互作品与演示。', 'status': 'UNKNOWN', 'evidence': []}]},
            ],
        })
    approve(svc, mutate_packet(packet('青年数字创意挑战赛'), change), 'sg2-competition')
    rows = svc.catalog(kind='COMPETITION', limit=50)['items']
    assert {x['title'] for x in rows} == {'数字叙事赛道', '应用设计赛道'}
    assert {x['target_kind'] for x in rows} == {'TRACK'}
    detail = svc.detail(rows[0]['id'])
    assert detail['issuer'] == '青年创新中心'
    assert detail['presentation']['target_label'] == '赛道'
    assert detail['presentation']['own_section_title'] == '赛道内容'
    assert detail['presentation']['common_section_title'] == '赛事共同规则'
    assert detail['presentation']['parent_label'] == '所属赛事'
    assert '岗位' not in json.dumps(detail['presentation'], ensure_ascii=False)
    assert any(x['label'] == '组队要求' for x in detail['common_fields'])
    assert not any(x['label'] == '组队要求' for x in detail['fields'])


def test_research_group_scopes_tracks_but_does_not_become_issuer(svc):
    def change(data):
        data.update({
            'opportunity_name': '先进材料本科生科研计划',
            'publish_unit': '东海先进材料研究院',
            'opportunity_type': 'RESEARCH_PROGRAM',
            'units': [{
                'id': 'runtime-lab', 'source_record_key': 'lab-functional-materials', 'name': '功能材料实验室',
                'unit_level': [{'field': '实验地点', 'value': '宁波', 'status': 'UNKNOWN', 'evidence': []}],
                'tracks': [
                    {'id': 'runtime-direction-1', 'source_record_key': 'direction-battery', 'name': '储能材料方向', 'kind': 'TRACK',
                     'facts': [{'field': '研究方向', 'value': '电池材料与界面研究', 'status': 'UNKNOWN', 'evidence': []}]},
                    {'id': 'runtime-direction-2', 'source_record_key': 'direction-sensor', 'name': '智能传感方向', 'kind': 'TRACK',
                     'facts': [{'field': '研究方向', 'value': '柔性传感材料', 'status': 'UNKNOWN', 'evidence': []}]},
                ],
            }],
            'tracks': [],
        })
    approve(svc, mutate_packet(packet('先进材料本科生科研计划'), change), 'sg2-research')
    rows = svc.catalog(kind='RESEARCH_PROGRAM', limit=50)['items']
    assert {x['title'] for x in rows} == {'储能材料方向', '智能传感方向'}
    detail = svc.detail(rows[0]['id'])
    assert detail['issuer'] == '东海先进材料研究院'
    assert detail['scope_labels'] == ['功能材料实验室']
    assert detail['presentation']['target_label'] == '研究方向'
    assert detail['presentation']['ancestor_section_title'] == '项目分组共同内容'


def test_scholarship_program_tiers_become_funding_targets_and_unknown_fields_survive(svc):
    def change(data):
        data.update({
            'opportunity_name': '青年创新奖学金',
            'publish_unit': '海岳教育基金会',
            'opportunity_type': 'SCHOLARSHIP',
            'units': [], 'tracks': [],
            'program_tiers': [
                {'id': 'tier-a', 'source_record_key': 'scholarship-a', 'name': '卓越奖', 'kind': 'PROGRAM_TIER',
                 'facts': [
                     {'field': '支持金额', 'value': '每人10000元', 'status': 'UNKNOWN', 'evidence': []},
                     {'field': '综合素质说明', 'value': '可提交公益、创新或科研经历作为补充材料。', 'status': 'UNKNOWN', 'evidence': []},
                 ]},
                {'id': 'tier-b', 'source_record_key': 'scholarship-b', 'name': '成长奖', 'kind': 'PROGRAM_TIER',
                 'facts': [{'field': '支持金额', 'value': '每人5000元', 'status': 'UNKNOWN', 'evidence': []}]},
            ],
        })
    approve(svc, mutate_packet(packet('青年创新奖学金'), change), 'sg2-scholarship')
    rows = svc.catalog(kind='SCHOLARSHIP', limit=50)['items']
    assert {x['title'] for x in rows} == {'卓越奖', '成长奖'}
    assert {x['target_kind'] for x in rows} == {'PROGRAM_TIER'}
    detail = svc.detail(next(x['id'] for x in rows if x['title'] == '卓越奖'))
    assert detail['presentation']['target_label'] == '资助档次'
    assert detail['presentation']['common_section_title'] == '资助共同条件'
    assert any(x['label'] == '综合素质说明' and '公益' in x['value'] for x in detail['fields'])
    searched = svc.catalog(q='公益', kind='SCHOLARSHIP', limit=50)
    assert searched['total'] == 1 and searched['items'][0]['title'] == '卓越奖'


def test_rolling_policy_region_variants_have_no_fake_deadline_and_need_no_application_url(svc):
    def change(data):
        data.update({
            'opportunity_name': '青年人才安居支持',
            'publish_unit': '海州市青年发展服务中心',
            'opportunity_type': 'YOUTH_POLICY_BENEFIT',
            'application_url': None,
            'units': [], 'tracks': [],
            'announcement_level': [
                {'field': '受理时间', 'value': '常年受理，额度用完即止。', 'status': 'UNKNOWN', 'evidence': []},
                {'field': '办理方式', 'value': '线下向属地服务窗口提交材料。', 'status': 'UNKNOWN', 'evidence': []},
            ],
            'region_variants': [
                {'id': 'region-north', 'source_record_key': 'policy-north', 'name': '北区青年安居支持', 'kind': 'REGION_VARIANT',
                 'region': '海州市北区', 'facts': [{'field': '支持标准', 'value': '符合条件者可申请租房支持。', 'status': 'UNKNOWN', 'evidence': []}]},
                {'id': 'region-south', 'source_record_key': 'policy-south', 'name': '南区青年安居支持', 'kind': 'REGION_VARIANT',
                 'region': '海州市南区', 'facts': [{'field': '支持标准', 'value': '符合条件者可申请人才公寓。', 'status': 'UNKNOWN', 'evidence': []}]},
            ],
        })
    approve(svc, mutate_packet(packet('青年人才安居支持'), change), 'sg2-policy')
    rows = svc.catalog(kind='YOUTH_POLICY_BENEFIT', limit=50)['items']
    assert len(rows) == 2
    assert {x['region'] for x in rows} == {'海州市北区', '海州市南区'}
    assert all(x['deadline'] is None for x in rows)
    detail = svc.detail(rows[0]['id'])
    assert detail['application_url'] is None
    assert detail['official_url']
    assert detail['presentation']['target_label'] == '地区政策'
    assert detail['presentation']['time_label'] == '受理时间'
    assert any(x['label'] == '受理时间' and '常年受理' in x['value'] for x in detail['common_fields'])


def test_postgrad_program_tiers_filter_and_present_as_program_categories(svc):
    def change(data):
        data.update({
            'opportunity_name': '未来传播暑期学校',
            'publish_unit': '东海大学传播学院',
            'opportunity_type': 'POSTGRAD_RECOMMENDATION',
            'units': [], 'tracks': [],
            'program_tiers': [
                {'id': 'summer-research', 'source_record_key': 'summer-research', 'name': '学术研究组', 'kind': 'PROGRAM_TIER',
                 'facts': [{'field': '面向对象', 'value': '相关专业本科三年级学生', 'status': 'UNKNOWN', 'evidence': []}]},
                {'id': 'summer-practice', 'source_record_key': 'summer-practice', 'name': '创新实践组', 'kind': 'PROGRAM_TIER',
                 'facts': [{'field': '面向对象', 'value': '跨专业创新实践学生', 'status': 'UNKNOWN', 'evidence': []}]},
            ],
        })
    approve(svc, mutate_packet(packet('未来传播暑期学校'), change), 'sg2-postgrad')
    rows = svc.catalog(kind='POSTGRAD_RECOMMENDATION', limit=50)['items']
    assert len(rows) == 2
    detail = svc.detail(rows[0]['id'])
    assert detail['presentation']['target_label'] == '项目类别'
    assert detail['presentation']['parent_label'] == '所属升学项目'
    assert svc.catalog(q='跨专业', kind='POSTGRAD_RECOMMENDATION', limit=50)['total'] == 1


def test_nested_actionable_units_only_emit_leaf_action_targets(svc):
    def change(data):
        data.update({
            'opportunity_name': '全国青年创意赛',
            'publish_unit': '全国青年创意赛组委会',
            'opportunity_type': 'COMPETITION',
            'units': [],
            'tracks': [{
                'id': 'track-design', 'source_record_key': 'track-design', 'name': '设计赛道', 'kind': 'TRACK',
                'children': [
                    {'id': 'tier-undergrad', 'source_record_key': 'track-design-undergrad', 'name': '本科生组', 'kind': 'PROGRAM_TIER', 'facts': []},
                    {'id': 'tier-postgrad', 'source_record_key': 'track-design-postgrad', 'name': '研究生组', 'kind': 'PROGRAM_TIER', 'facts': []},
                ],
            }],
        })
    approve(svc, mutate_packet(packet('全国青年创意赛'), change), 'sg2-frontier')
    rows = svc.catalog(kind='COMPETITION', limit=50)['items']
    assert {x['title'] for x in rows} == {'本科生组', '研究生组'}
    assert {x['target_kind'] for x in rows} == {'PROGRAM_TIER'}
    assert '设计赛道' not in {x['title'] for x in rows}
    detail = svc.detail(rows[0]['id'])
    assert detail['scope_labels'] == ['设计赛道']
    assert detail['presentation']['target_label'] == '组别 / 级别'


def test_generic_action_units_contract_supports_stable_key_kind_and_nested_parent(svc):
    def change(data):
        data.update({
            'opportunity_name': '青年跨界实践计划',
            'publish_unit': '青年发展中心',
            'opportunity_type': 'YOUTH_DEVELOPMENT_PROGRAM',
            'units': [], 'tracks': [],
            'action_units': [{
                'id': 'runtime-group', 'source_record_key': 'practice-group', 'name': '城市实践组', 'kind': 'GROUP',
                'children': [{
                    'id': 'runtime-child-v1', 'source_record_key': 'practice-content', 'name': '内容策划实践', 'kind': 'DEFAULT_SINGLETON',
                    'application_url': 'https://research.example.org/apply/practice-content',
                    'facts': [{'field': '实践内容', 'value': '参与青年传播内容策划。', 'status': 'UNKNOWN', 'evidence': []}],
                }],
            }],
        })
    blob = mutate_packet(packet('青年跨界实践计划'), change)
    approve(svc, blob, 'sg2-generic-v1')
    first = svc.catalog(kind='YOUTH_DEVELOPMENT_PROGRAM', limit=50)['items'][0]
    detail = svc.detail(first['id'])
    assert detail['scope_labels'] == ['城市实践组']
    assert detail['application_url'] == 'https://research.example.org/apply/practice-content'

    def change_runtime_only(data):
        change(data)
        data['action_units'][0]['id'] = 'runtime-group-new'
        data['action_units'][0]['children'][0]['id'] = 'runtime-child-v2'
        data['announcement_level'].append({'field': '版本说明', 'value': '仅运行时ID变化', 'status': 'UNKNOWN', 'evidence': []})
    preview = svc.ingest(svc.test_source, mutate_packet(packet('青年跨界实践计划'), change_runtime_only), actor='operator')
    svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', 'sg2-generic-v2', actor='reviewer')
    rows = svc.catalog(kind='YOUTH_DEVELOPMENT_PROGRAM', limit=50)['items']
    assert len(rows) == 1 and rows[0]['id'] == first['id']


def test_target_specific_deadline_overrides_root_when_evidence_supports_child_scope(svc):
    from .test_contract import FUTURE_DATE
    child_day = '2099-08-18'
    def change(data):
        data.update({
            'opportunity_name': '双阶段创意竞赛',
            'publish_unit': '创意竞赛组委会',
            'opportunity_type': 'COMPETITION',
            'units': [],
            'tracks': [{
                'id': 'special-track', 'source_record_key': 'special-track', 'name': '专项赛道', 'kind': 'TRACK',
                'facts': [{'field': '报名截止', 'value': child_day, 'status': 'CONFIRMED', 'evidence': [
                    {'artifact_id': 'a1', 'quote': '报名截止：'+FUTURE_DATE, 'locator': {'line': 2}}
                ]}],
            }],
        })
    # The child quote does not support child_day, so the root supported date remains the target deadline.
    approve(svc, mutate_packet(packet('双阶段创意竞赛'), change), 'sg2-child-deadline-unsupported')
    row = svc.catalog(kind='COMPETITION', limit=50)['items'][0]
    assert row['deadline'] != child_day



def test_fictional_example_pack_covers_sg2_five_type_gate(svc):
    from deepaha.product.examples import bundles
    generated = list(bundles())
    assert {name for name, _ in generated} >= {
        '01_recruitment.zip','02_competition.zip','03_policy.zip',
        '04_research.zip','05_scholarship.zip','06_postgrad.zip',
    }
    source = svc.add_source('澄川机会体验来源', 'https://institute.example.org/', actor='operator')
    types = set()
    for i, (name, blob) in enumerate(generated):
        preview = svc.ingest(source['id'], blob, actor='operator')
        assert preview['can_approve'], name
        svc.decide(preview['id'], 'APPROVE', preview['preview_hash'], '', f'sg2-example-{i}', actor='reviewer')
        types.update(x['type'] for x in svc.catalog(limit=50)['items'])
    assert {'COMPETITION','RESEARCH_PROGRAM','SCHOLARSHIP','YOUTH_POLICY_BENEFIT','POSTGRAD_RECOMMENDATION'} <= types


def test_legacy_chinese_type_aliases_map_to_multitype_core():
    from deepaha.product.adapter import category

    assert category('2027 推免夏令营') == 'POSTGRAD_RECOMMENDATION'
    assert category('保研项目') == 'POSTGRAD_RECOMMENDATION'
    assert category('青年人才补贴') == 'YOUTH_POLICY_BENEFIT'
    assert category('大学生社会实践计划') == 'YOUTH_DEVELOPMENT_PROGRAM'
