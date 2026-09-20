from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]

def test_sg6_user_ui_exposes_action_timeline_feedback_and_notification_controls():
    js='\n'.join((ROOT/'web/public/product'/name).read_text(encoding='utf-8') for name in ('user.js','actions-ui.js'))
    for token in ['行动时间线','本周机会摘要','截止提醒','机会变化','每周机会摘要','以前知道这个机会吗','最终结果']:
        assert token in js

def test_sg6_management_exposes_feedback_candidates_without_rule_publish_action():
    js=(ROOT/'web/public/product/workbench.js').read_text(encoding='utf-8')
    assert '反馈样本' in js
    assert '/api/manage/feedback-candidates' in js
    assert '直接修改资格规则' not in js
