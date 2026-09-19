from pathlib import Path

USER = Path('web/public/product/user.js')


def test_profile_exposes_optional_compiler_fields_without_manual_review_controls():
    source=USER.read_text(encoding='utf-8')
    for name in (
        'degree','student_status','nationality','political_status','work_experience_years',
        'certificates','professional_title','language_certificates','team_size',
    ):
        assert f'name="{name}"' in source
    assert '更多资格信息' in source
    assert '逐字段审核' not in source
    assert 'approve-field' not in source
    assert 'qualification-approve' not in source


def test_fit_ui_surfaces_compiler_coverage_and_high_risk_without_changing_status():
    source=USER.read_text(encoding='utf-8')
    assert 'compiler_state' in source
    assert 'unresolved_conditions' in source
    assert 'qualification_risk' in source
    assert '存在明显资格冲突线索' in source


def test_star_ui_explains_hold_for_confirmation_as_ranking_gate_not_ineligible():
    source=USER.read_text(encoding='utf-8')
    assert 'HOLD_FOR_CONFIRMATION' in source
    assert '资格待核对' in source
