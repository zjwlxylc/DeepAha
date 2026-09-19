import copy
import json


def handoff(run_key='demo-20260906-001'):
    """Synthetic fixture. example.org is not an investigated source."""
    return {
        'schema_version': 'deepaha.source-intelligence.run.v2.2',
        'run_metadata': {
            'run_key': run_key, 'prompt_version': '2.2.1',
            'generated_at': '2026-09-06T08:00:00+08:00',
            'run_mode': 'NORMAL_REFRESH', 'run_mode_reason': '合成演练样本',
            'state_inheritance': 'UNAVAILABLE', 'prior_state_ref': None,
            'prior_run_at': None, 'baseline_refs': [], 'state_scope': 'DEMO_ONLY',
            'system_feedback': 'NOT_PROVIDED', 'import_receipt_ref': None,
            'delivery_mode': 'MANUAL_EXPORT_ONLY', 'submission_status': 'NOT_SUBMITTED',
            'result_status': 'STANDALONE_RESEARCH_RESULT', 'package_complete': True,
            'limitations': ['演练样本，不是官方来源研究成果。'],
        },
        'source_candidates': [{
            'candidate_key': 'demo-source-a', 'legacy_id': None, 'system_source_id': None,
            'institution': '演练研究院', 'source_name': '演练来源 A',
            'recommended_seed': 'https://example.org/opportunities?year=2026#list',
            'source_role': 'LONG_TAIL_OFFICIAL',
            'authority_assessment': {'level': 'UNKNOWN', 'reason': '演练，不授予官方性'},
            'demand_themes': ['演练需求'], 'opportunity_types': ['科研'],
            'target_youth': ['测试用户'], 'value_assessment': {'reason': '仅演练'},
            'score_breakdown': {}, 'score_total': None, 'recommendation': 'EXPLORE',
            'recon_status': 'UNKNOWN', 'first_seen_at': '2026-09-06T08:00:00+08:00',
            'last_checked_at': '2026-09-06T08:00:00+08:00',
            'evidence_refs': ['ev-demo-a'], 'uncertainties': ['未经官方核验'],
            'proposed_operation': None, 'revision': 1, 'base_revision': None,
        }],
        'agent_acquisition_briefs': [{
            'source_ref': 'demo-source-a', 'brief_key': 'brief-demo-a',
            'revision': 1, 'base_revision': None,
            'recommended_seed': 'https://example.org/opportunities?year=2026#list',
            'source_role': 'LONG_TAIL_OFFICIAL', 'authority': 'UNKNOWN',
            'source_topology': '列表 → 详情', 'opportunity_pattern': '演练项目',
            'navigation_advice': '仅读取获准范围。', 'discovery_strategy': '检查已批准栏目新增公告。',
            'source_network': [], 'evidence_hotspots': ['详情页'], 'attachment_pattern': 'UNKNOWN',
            'change_pattern': 'UNKNOWN', 'observed_access_shape': 'UNKNOWN',
            'agent_capability_needs': ['RUNTIME_CAPABILITY_TO_VERIFY'], 'known_obstacles': [],
            'stop_escalation_rule': '出现登录或验证码即停止并报告。',
            'expected_candidate_evidence_package': ['原文', '证据定位'],
            'suggested_revisit_pattern': '待人工确认', 'scout_confidence': 'LOW',
            'recon_evidence': ['ev-demo-a'], 'last_checked_at': '2026-09-06T08:00:00+08:00',
        }],
        'research_evidence': [{
            'evidence_key': 'ev-demo-a', 'url': 'https://example.org/opportunities?year=2026#list',
            'title': '合成研究证据', 'checked_at': '2026-09-06T08:00:00+08:00',
            'observation': '这是一条合成记录。', 'locator': '演练段落',
            'observation_status': 'UNKNOWN',
        }],
        'demand_map': [{'demand_key': 'demand-demo', 'theme': '演练需求', 'status': 'PROPOSED'}],
        'demand_delta': [], 'source_graph_delta': [], 'lifecycle_delta': [], 'pattern_delta': [],
        'blind_spots': [{'description': '尚未连接正式系统'}],
        'next_exploration_queue': [], 'manual_review_manifest': [],
        'state_snapshot_ref': 'DeepAha_Scout_demo-20260906-001_State.json',
        'metrics': {'human_confirmed_import_count': None}, 'warnings': ['DEMO_ONLY'],
    }


def raw(value=None):
    return json.dumps(handoff() if value is None else value, ensure_ascii=False, indent=2).encode('utf-8')


def changed(base=None, run_key='demo-update-002'):
    data = copy.deepcopy(handoff() if base is None else base)
    data['run_metadata']['run_key'] = run_key
    data['source_candidates'][0]['source_name'] = '演练来源 A（新版）'
    data['source_candidates'][0]['revision'] = 2
    data['source_candidates'][0]['base_revision'] = 1
    return data
