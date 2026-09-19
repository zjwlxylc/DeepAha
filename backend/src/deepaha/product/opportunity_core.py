"""Multi-type Opportunity presentation contract.

This module controls *presentation semantics only*. It does not promote facts,
compile eligibility rules, or reinterpret evidence. The same stored facts remain
available regardless of opportunity category.
"""
from __future__ import annotations

JOB_TYPES = {
    'PUBLIC_INSTITUTION_JOB',
    'STATE_OWNED_ENTERPRISE_JOB',
    'CIVIL_SERVICE',
    'GRASSROOTS_PROGRAM',
}

TYPE_LABELS = {
    'PUBLIC_INSTITUTION_JOB': '事业单位',
    'STATE_OWNED_ENTERPRISE_JOB': '国央企',
    'CIVIL_SERVICE': '考公',
    'GRASSROOTS_PROGRAM': '基层项目',
    'YOUTH_POLICY_BENEFIT': '人才政策',
    'POSTGRAD_RECOMMENDATION': '升学',
    'ADMISSION_CHANGE': '招生信息',
    'COMPETITION': '竞赛',
    'RESEARCH_PROGRAM': '科研',
    'SCHOLARSHIP': '奖学金',
    'YOUTH_DEVELOPMENT_PROGRAM': '成长与实践',
}


def _job(kind: str) -> str:
    return {
        'POSITION': '岗位', 'TRACK': '岗位方向', 'PROGRAM_TIER': '岗位类别',
        'REGION_VARIANT': '地区岗位', 'DEFAULT_SINGLETON': '单项机会',
    }.get(kind, '具体机会')


def _competition(kind: str) -> str:
    return {
        'TRACK': '赛道', 'PROGRAM_TIER': '组别 / 级别', 'REGION_VARIANT': '赛区',
        'POSITION': '参赛分项', 'DEFAULT_SINGLETON': '赛事',
    }.get(kind, '参赛分项')


def _research(kind: str) -> str:
    return {
        'TRACK': '研究方向', 'PROGRAM_TIER': '项目分项', 'REGION_VARIANT': '地区项目',
        'POSITION': '研究岗位', 'DEFAULT_SINGLETON': '科研项目',
    }.get(kind, '科研分项')


def _scholarship(kind: str) -> str:
    return {
        'PROGRAM_TIER': '资助档次', 'TRACK': '资助类别', 'REGION_VARIANT': '地区资助',
        'POSITION': '资助分项', 'DEFAULT_SINGLETON': '奖学金',
    }.get(kind, '资助分项')


def _policy(kind: str) -> str:
    return {
        'REGION_VARIANT': '地区政策', 'PROGRAM_TIER': '支持档次', 'TRACK': '政策类别',
        'POSITION': '支持分项', 'DEFAULT_SINGLETON': '政策 / 补贴',
    }.get(kind, '政策分项')


def _postgrad(kind: str) -> str:
    return {
        'TRACK': '项目方向', 'PROGRAM_TIER': '项目类别', 'REGION_VARIANT': '地区 / 校区',
        'POSITION': '招生分项', 'DEFAULT_SINGLETON': '升学项目',
    }.get(kind, '项目分项')


def _development(kind: str, raw_type: str) -> str:
    internship = '实习' in (raw_type or '')
    return {
        'POSITION': '实习岗位' if internship else '实践岗位',
        'TRACK': '项目方向', 'PROGRAM_TIER': '项目类别', 'REGION_VARIANT': '地区分项',
        'DEFAULT_SINGLETON': '实习' if internship else '成长 / 实践项目',
    }.get(kind, '具体分项')


def presentation_for(type_code: str, target_kind: str, raw_type: str = '') -> dict:
    """Return stable UI vocabulary for one target without changing facts."""
    if type_code in JOB_TYPES:
        label = _job(target_kind)
        return {
            'type_label': TYPE_LABELS.get(type_code, '招聘'), 'target_label': label,
            'own_section_title': f'{label}内容', 'ancestor_section_title': '单位 / 分组共同内容',
            'common_section_title': '公告共同条件', 'parent_label': '所属公告',
            'time_label': '报名时间', 'action_label': '查看报名方式', 'unknown_time_label': '时间见详情',
            'sibling_title': '同公告其他具体机会', 'group_as_issuer': True,
        }
    if type_code == 'COMPETITION':
        label = _competition(target_kind)
        return {
            'type_label': '竞赛', 'target_label': label, 'own_section_title': f'{label}内容',
            'ancestor_section_title': '赛事分组共同内容', 'common_section_title': '赛事共同规则',
            'parent_label': '所属赛事', 'time_label': '报名 / 提交时间', 'action_label': '查看参赛入口',
            'unknown_time_label': '赛程见详情', 'sibling_title': '同赛事其他分项', 'group_as_issuer': False,
        }
    if type_code == 'RESEARCH_PROGRAM':
        label = _research(target_kind)
        return {
            'type_label': '科研', 'target_label': label, 'own_section_title': f'{label}内容',
            'ancestor_section_title': '项目分组共同内容', 'common_section_title': '项目共同要求',
            'parent_label': '所属科研项目', 'time_label': '申请时间', 'action_label': '查看申请方式',
            'unknown_time_label': '申请时间见详情', 'sibling_title': '同项目其他分项', 'group_as_issuer': False,
        }
    if type_code == 'SCHOLARSHIP':
        label = _scholarship(target_kind)
        return {
            'type_label': '奖学金', 'target_label': label, 'own_section_title': f'{label}内容',
            'ancestor_section_title': '资助分组共同内容', 'common_section_title': '资助共同条件',
            'parent_label': '所属奖学金 / 资助计划', 'time_label': '申请时间', 'action_label': '查看申请方式',
            'unknown_time_label': '申请时间见详情', 'sibling_title': '同计划其他资助分项', 'group_as_issuer': False,
        }
    if type_code == 'YOUTH_POLICY_BENEFIT':
        label = _policy(target_kind)
        return {
            'type_label': '人才政策', 'target_label': label, 'own_section_title': f'{label}内容',
            'ancestor_section_title': '政策分组共同内容', 'common_section_title': '政策共同条件',
            'parent_label': '所属政策', 'time_label': '受理时间', 'action_label': '查看办理方式',
            'unknown_time_label': '受理时间见详情', 'sibling_title': '同政策其他分项', 'group_as_issuer': False,
        }
    if type_code in {'POSTGRAD_RECOMMENDATION', 'ADMISSION_CHANGE'}:
        label = _postgrad(target_kind)
        return {
            'type_label': TYPE_LABELS.get(type_code, '升学'), 'target_label': label,
            'own_section_title': f'{label}内容', 'ancestor_section_title': '项目分组共同内容',
            'common_section_title': '项目共同条件', 'parent_label': '所属升学项目',
            'time_label': '申请时间', 'action_label': '查看申请方式', 'unknown_time_label': '申请时间见详情',
            'sibling_title': '同项目其他分项', 'group_as_issuer': False,
        }
    label = _development(target_kind, raw_type)
    group_as_issuer = '实习' in (raw_type or '') and target_kind == 'POSITION'
    return {
        'type_label': '实习' if '实习' in (raw_type or '') else TYPE_LABELS.get(type_code, '成长与实践'),
        'target_label': label, 'own_section_title': f'{label}内容', 'ancestor_section_title': '项目分组共同内容',
        'common_section_title': '项目共同条件', 'parent_label': '所属项目',
        'time_label': '报名 / 申请时间', 'action_label': '查看参与方式', 'unknown_time_label': '时间见详情',
        'sibling_title': '同项目其他分项', 'group_as_issuer': group_as_issuer,
    }


def summary_labels(type_code: str) -> tuple[str, ...]:
    return {
        'COMPETITION': ('赛道说明', '参赛内容', '作品要求', '项目要求'),
        'RESEARCH_PROGRAM': ('研究方向', '项目描述', '研究内容', '课题内容'),
        'SCHOLARSHIP': ('资助内容', '支持内容', '奖项说明'),
        'YOUTH_POLICY_BENEFIT': ('支持内容', '政策说明', '补贴内容'),
        'POSTGRAD_RECOMMENDATION': ('项目介绍', '培养方向', '项目方向'),
        'ADMISSION_CHANGE': ('项目介绍', '招生说明', '培养方向'),
        'YOUTH_DEVELOPMENT_PROGRAM': ('实践内容', '项目描述', '培养内容', '岗位描述'),
    }.get(type_code, ('岗位描述', '职责', '工作内容', '项目描述'))
