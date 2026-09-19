from pathlib import Path

ROOT=Path('web/public/product')

def test_sg7_frontend_has_operator_lab_and_voluntary_user_lab_without_restoring_field_review():
    work=(ROOT/'workbench.js').read_text(encoding='utf-8')
    user=(ROOT/'user.js').read_text(encoding='utf-8')
    lab=(ROOT/'lab-ui.js').read_text(encoding='utf-8')
    api=Path('backend/src/deepaha/product/api.py').read_text(encoding='utf-8')
    assert "'/manage/lab'" in work and '机会实验室' in work
    assert "path==='/app/lab'" in user and '机会共创实验' in user
    assert '自愿加入共创实验' in lab and '退出共创实验' in lab
    assert '不算真人 Gold' in lab and '机会 × 数字分身评估真值' in lab
    assert '确定性标准答案判卷' in lab and '工程标准答案不等于独立人工 Gold' in lab
    assert 'V${twins.items?.[0]?.version||2}' in lab
    assert '预期推荐结论' in lab and 'expected_recommendation' in lab
    assert '/api/manage/lab/' in api and '/api/me/lab' in api
    forbidden=['确认学历字段','确认专业字段','确认年龄字段','事实晋升按钮','scope approval']
    joined='\n'.join([work,user,lab,api])
    assert not any(x in joined for x in forbidden)


def test_sg7_lab_ui_does_not_claim_model_training_or_send_profile_to_wma():
    lab=(ROOT/'lab-ui.js').read_text(encoding='utf-8')
    assert '不会把你的完整画像发给 WMA' in lab
    assert '不自动训练外部模型' in lab
    assert '不会批准正式事实' in lab
